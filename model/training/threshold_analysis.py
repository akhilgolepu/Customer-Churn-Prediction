"""Cost-based decision-threshold analysis on calibrated probabilities.

Method (the test split is only reported on, never used to choose):
  1. Score the validation split with the shipped model (train.py) and calibrate
     it out-of-fold: each validation row is calibrated by a calibrator fitted on
     the other validation folds, with the method train.py selected.
  2. For each cost scenario, pick the grid threshold with the highest expected
     net benefit on those validation scores ("empirical" threshold).
  3. Next to it, report the closed-form break-even threshold. With a calibrated
     probability p, contacting a customer is worth it when
         p * save_rate * value - offer_cost > 0   <=>   p > offer_cost / (save_rate * value).
  4. Report both, the old default 0.62 and 0.50 once on the held-out test split.

Economics are ASSUMPTIONS (params.yaml -> threshold). The value of a saved
customer uses the mean monthly charge of churners in train+validation only.

Usage:
    python model/training/threshold_analysis.py            # writes docs/threshold_analysis.json
    python model/training/threshold_analysis.py --no-write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, load_dataset, load_params, three_way_split  # noqa: E402

from model.calibration import Calibrator, cross_fit  # noqa: E402

OUT_PATH = REPO_ROOT / "docs" / "threshold_analysis.json"
OLD_DEFAULT = 0.62


def net_benefit(y, p, thr, value, offer_cost, save_rate) -> float:
    """Total expected net benefit of contacting everyone with p >= thr."""
    flagged = p >= thr
    tp = int((flagged & (y == 1)).sum())
    fp = int((flagged & (y == 0)).sum())
    return tp * (save_rate * value - offer_cost) - fp * offer_cost


def per_1000(total: float, n: int) -> float:
    return total / n * 1000


def operating_point(y, p, thr, value, offer_cost, save_rate) -> dict:
    flagged = p >= thr
    tp = int((flagged & (y == 1)).sum())
    return {
        "threshold": round(float(thr), 4),
        "flagged_pct": float(flagged.mean()),
        "precision": float(tp / flagged.sum()) if flagged.sum() else None,
        "recall": float(tp / (y == 1).sum()),
        "net_benefit_per_1000": per_1000(net_benefit(y, p, thr, value, offer_cost, save_rate), len(y)),
    }


def best_on_grid(y, p, grid, value, offer_cost, save_rate) -> float:
    scores = [net_benefit(y, p, t, value, offer_cost, save_rate) for t in grid]
    return float(grid[int(np.argmax(scores))])


def bootstrap_gain(y, p, thr_a, thr_b, value, offer_cost, save_rate, n, seed) -> list[float]:
    """95% interval of net benefit(thr_a) - net benefit(thr_b) per 1,000, rows resampled jointly."""
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        yb, pb = y[idx], p[idx]
        diffs.append(per_1000(
            net_benefit(yb, pb, thr_a, value, offer_cost, save_rate)
            - net_benefit(yb, pb, thr_b, value, offer_cost, save_rate), len(y)))
    return [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]


def main(write: bool) -> None:
    from catboost import CatBoostClassifier

    params = load_params()
    tcfg, ccfg, boot = params["threshold"], params["calibration"], params["bootstrap"]
    ds = load_dataset(params)
    split = three_way_split(ds.y, params)

    model = CatBoostClassifier()
    model.load_model(str(REPO_ROOT / params["output"]["model_path"]))
    calibrator = Calibrator.load(REPO_ROOT / params["output"]["calibration_path"])

    y_val = ds.y.iloc[split.val].to_numpy()
    raw_val = model.predict_proba(ds.x.iloc[split.val])[:, 1]
    p_val = cross_fit(calibrator.method, raw_val, y_val, folds=ccfg["folds"], seed=ccfg["seed"])

    y_te = ds.y.iloc[split.test].to_numpy()
    p_te = calibrator.transform(model.predict_proba(ds.x.iloc[split.test])[:, 1])

    dev = split.dev
    churner_monthly = float(ds.raw["MonthlyCharges"].iloc[dev][ds.y.iloc[dev] == 1].mean())
    grid = np.round(np.arange(tcfg["grid_start"], tcfg["grid_stop"] + 1e-9, tcfg["grid_step"]), 4)

    def scenario(offer_cost, save_rate, margin):
        value = churner_monthly * tcfg["horizon_months"] * margin
        empirical = best_on_grid(y_val, p_val, grid, value, offer_cost, save_rate)
        closed_form = offer_cost / (save_rate * value)
        val_nb = lambda t: per_1000(net_benefit(y_val, p_val, t, value, offer_cost, save_rate), len(y_val))  # noqa: E731
        test_points = {
            "contact_nobody": {"net_benefit_per_1000": 0.0},
            "contact_everyone": operating_point(y_te, p_te, 0.0, value, offer_cost, save_rate),
            "threshold_0.50": operating_point(y_te, p_te, 0.50, value, offer_cost, save_rate),
            "old_default_0.62": operating_point(y_te, p_te, OLD_DEFAULT, value, offer_cost, save_rate),
            "empirical_from_validation": operating_point(y_te, p_te, empirical, value, offer_cost, save_rate),
            "closed_form": operating_point(y_te, p_te, closed_form, value, offer_cost, save_rate),
        }
        return {
            "offer_cost": offer_cost,
            "save_rate": save_rate,
            "margin": margin,
            "value_per_retained_customer": round(value, 2),
            "empirical_threshold_validation": empirical,
            "closed_form_threshold": round(closed_form, 4),
            "validation_net_benefit_per_1000": {
                "at_empirical": val_nb(empirical),
                "at_closed_form": val_nb(closed_form),
                "at_old_default_0.62": val_nb(OLD_DEFAULT),
            },
            "test": test_points,
        }

    scenarios = {name: scenario(**cfg) for name, cfg in tcfg["scenarios"].items()}
    primary = tcfg["primary_scenario"]
    prim_cfg = tcfg["scenarios"][primary]
    value_p = churner_monthly * tcfg["horizon_months"] * prim_cfg["margin"]
    s_p = scenarios[primary]

    gains = {
        # Headline baseline: the untuned 0.50 cut-off. 0.62 was tuned on the old
        # class-weighted model's scores, so a gain over it would be overstated.
        "empirical_minus_0.50_test": bootstrap_gain(
            y_te, p_te, s_p["empirical_threshold_validation"], 0.50, value_p,
            prim_cfg["offer_cost"], prim_cfg["save_rate"], boot["n_resamples"], boot["seed"]),
        "empirical_minus_old_default_0.62_test": bootstrap_gain(
            y_te, p_te, s_p["empirical_threshold_validation"], OLD_DEFAULT, value_p,
            prim_cfg["offer_cost"], prim_cfg["save_rate"], boot["n_resamples"], boot["seed"]),
        "closed_form_minus_empirical_test": bootstrap_gain(
            y_te, p_te, s_p["closed_form_threshold"], s_p["empirical_threshold_validation"], value_p,
            prim_cfg["offer_cost"], prim_cfg["save_rate"], boot["n_resamples"], boot["seed"]),
    }

    sens = []
    for oc in tcfg["sensitivity_offer_cost"]:
        for sr in tcfg["sensitivity_save_rate"]:
            t_emp = best_on_grid(y_val, p_val, grid, value_p, oc, sr)
            t_cf = oc / (sr * value_p)
            sens.append({
                "offer_cost": oc,
                "save_rate": sr,
                "empirical_threshold_validation": t_emp,
                "closed_form_threshold": round(t_cf, 4),
                "test_net_benefit_per_1000_empirical": per_1000(net_benefit(y_te, p_te, t_emp, value_p, oc, sr), len(y_te)),
                "test_net_benefit_per_1000_closed_form": per_1000(net_benefit(y_te, p_te, t_cf, value_p, oc, sr), len(y_te)),
                "test_net_benefit_per_1000_contact_everyone": per_1000(net_benefit(y_te, p_te, 0.0, value_p, oc, sr), len(y_te)),
            })

    curve = [
        {
            "threshold": float(t),
            "validation_net_benefit_per_1000": per_1000(net_benefit(y_val, p_val, t, value_p, prim_cfg["offer_cost"], prim_cfg["save_rate"]), len(y_val)),
            "test_net_benefit_per_1000": per_1000(net_benefit(y_te, p_te, t, value_p, prim_cfg["offer_cost"], prim_cfg["save_rate"]), len(y_te)),
        }
        for t in np.round(np.arange(0.10, 0.91, 0.05), 2)
    ]

    result = {
        "calibration_method": calibrator.method,
        "selection_data": "validation split, calibrated out-of-fold",
        "split": {"validation_rows": int(len(y_val)), "test_rows": int(len(y_te))},
        "horizon_months": tcfg["horizon_months"],
        "mean_monthly_charge_of_churners_train_val": round(churner_monthly, 2),
        "primary_scenario": primary,
        "scenarios": scenarios,
        "primary_bootstrap_95ci_per_1000": gains,
        "primary_curve": curve,
        "sensitivity_primary_value": sens,
    }
    print(json.dumps({k: result[k] for k in ("calibration_method", "mean_monthly_charge_of_churners_train_val",
                                             "scenarios", "primary_bootstrap_95ci_per_1000")}, indent=2))
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nWrote {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true")
    main(write=not parser.parse_args().no_write)
