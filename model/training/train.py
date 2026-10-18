"""Train and calibrate the served churn model.

  1. 60/20/20 stratified train / validation / test split (params.yaml).
  2. CatBoost (no class weight) fit on train, early-stopped on validation.
  3. Calibration method chosen by cross-fitting on validation (identity vs
     Platt vs isotonic, lowest mean log loss), then refit on all of validation.
  4. Writes the model, its calibration file and training metadata.
  5. Same split and calibration rule for the logistic-regression challenger,
     exported as JSON (model/linear_model.py) for the API's shadow slot.

The test split is not read here. evaluate.py reports on it once.

Usage:
    python model/training/train.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    REPO_ROOT,
    fit_catboost,
    fit_logistic_regression,
    ids_fingerprint,
    load_dataset,
    load_params,
    predict,
    prob_metrics,
    three_way_split,
)

import numpy as np  # noqa: E402

from model.calibration import Calibrator, calibration_path_for, cross_fit  # noqa: E402
from model.linear_model import LinearChurnModel  # noqa: E402


def select_calibration(raw_val, y_val, ccfg: dict) -> tuple[str, dict]:
    table = {}
    for method in ccfg["methods"]:
        oof = cross_fit(method, raw_val, y_val, folds=ccfg["folds"], seed=ccfg["seed"])
        table[method] = prob_metrics(y_val, oof)
    metric = ccfg["selection_metric"]
    best = min(table, key=lambda m: table[m][metric])
    return best, table


def train_challenger(ds, split, params) -> dict:
    """Logistic regression on train, calibration chosen on validation, exported as JSON."""
    x_tr, y_tr = ds.x.iloc[split.train], ds.y.iloc[split.train]
    x_va, y_va = ds.x.iloc[split.val], ds.y.iloc[split.val].to_numpy()
    lr = fit_logistic_regression(x_tr, y_tr, ds.cat_cols, params["models"]["logistic_regression"])
    raw_val = predict(lr, x_va)
    method, table = select_calibration(raw_val, y_va, params["calibration"])
    calibrator = Calibrator.fit(method, raw_val, y_va)
    val = prob_metrics(y_va, calibrator.transform(raw_val))
    linear = LinearChurnModel.from_sklearn(
        lr, x_tr, metrics={f"val_{k}": round(v, 4) for k, v in val.items()}
    )
    max_diff = float(np.abs(linear.predict_proba(x_va) - raw_val).max())
    if max_diff > 1e-9:
        raise SystemExit(f"JSON export does not reproduce scikit-learn (max diff {max_diff})")
    path = REPO_ROOT / params["output"]["challenger_path"]
    linear.save(path)
    calibrator.save(calibration_path_for(path))
    return {
        "model": "logistic_regression",
        "artifact": params["output"]["challenger_path"],
        "export_max_abs_diff_vs_sklearn": max_diff,
        "calibration": {"selected": method, "cross_fitted_on_validation": table},
        "validation_calibrated_in_sample": val,
    }


def main() -> None:
    params = load_params()
    ds = load_dataset(params)
    split = three_way_split(ds.y, params)
    x, y = ds.x, ds.y

    cb_cfg = params["models"]["catboost"]
    if cb_cfg.get("class_weight") is not None:
        raise SystemExit("Served model is trained without class weights; see docs/model_comparison.md")

    model = fit_catboost(
        x.iloc[split.train], y.iloc[split.train], x.iloc[split.val], y.iloc[split.val], ds.cat_cols, cb_cfg
    )
    raw_val = model.predict_proba(x.iloc[split.val])[:, 1]
    y_val = y.iloc[split.val].to_numpy()

    method, cal_table = select_calibration(raw_val, y_val, params["calibration"])
    calibrator = Calibrator.fit(method, raw_val, y_val)

    out = params["output"]
    model_path = REPO_ROOT / out["model_path"]
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    calibrator.save(REPO_ROOT / out["calibration_path"])

    ids = ds.raw["customerID"]
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "model": "catboost",
        "class_weight": None,
        "params": cb_cfg,
        "best_iteration": int(model.get_best_iteration()),
        "tree_count": int(model.tree_count_),
        "split": {
            "train_rows": int(len(split.train)),
            "val_rows": int(len(split.val)),
            "test_rows": int(len(split.test)),
            "train_positive_rate": float(y.iloc[split.train].mean()),
            "val_positive_rate": float(y_val.mean()),
            "test_positive_rate": float(y.iloc[split.test].mean()),
            "test_ids_fingerprint": ids_fingerprint(ids.iloc[split.test]),
        },
        "calibration": {
            "selected": method,
            "selection_metric": params["calibration"]["selection_metric"],
            "cross_fitted_on_validation": cal_table,
            # For reference: a = 1, b = 0 would mean Platt scaling is a no-op.
            "platt_fit_on_validation": Calibrator.fit("platt", raw_val, y_val).params,
        },
        "validation_raw": prob_metrics(y_val, raw_val),
        "validation_calibrated_in_sample": prob_metrics(y_val, calibrator.transform(raw_val)),
        "challenger": train_challenger(ds, split, params),
    }
    meta_path = REPO_ROOT / out["training_metadata_path"]
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(json.dumps({k: metadata[k] for k in ("best_iteration", "tree_count", "split", "calibration", "challenger")}, indent=2))
    print(f"Wrote {model_path.relative_to(REPO_ROOT)}, {out['calibration_path']}, {out['training_metadata_path']}")


if __name__ == "__main__":
    main()
