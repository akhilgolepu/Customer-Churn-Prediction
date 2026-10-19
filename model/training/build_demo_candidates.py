"""Build two demo candidate models for the shadow -> canary -> rollback demo.

  healthy_candidate.cbm   Same recipe as production (train.py), different random
                          seed. Behaves like a routine retrain: ranks customers
                          almost the same way, so canary disagreement stays low.
  degraded_candidate.cbm  Same recipe, but trained (and calibrated) on labels that
                          were randomly permuted. Simulates a retrain whose label
                          join went wrong. It learns nothing about churn, but
                          it is still a random function of strongly predictive
                          features, so its AUC against the TRUE labels is not
                          pinned at 0.5 and moves a lot with the permutation
                          seed (a Platt fit on the permuted labels can even
                          flip its sign). It is far below the healthy model
                          either way.

Both use the production split (fit on train, early stopping and calibration on
validation) and get a calibration file chosen the same way as in train.py. They
are written to model/artifacts/demo/ with their *measured* held-out metrics in
demo_candidates.json. Nothing here touches the production model.

Usage:  python model/training/build_demo_candidates.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, fit_catboost, load_dataset, load_params, prob_metrics, three_way_split  # noqa: E402
from train import select_calibration  # noqa: E402

from model.calibration import Calibrator, calibration_path_for  # noqa: E402

OUT_DIR = REPO_ROOT / "model" / "artifacts" / "demo"


def build(ds, split, params, seed: int, permute_labels: bool):
    cfg = {**params["models"]["catboost"], "seed": seed}
    y = ds.y.copy()
    if permute_labels:
        rng = np.random.default_rng(123)
        y = y.iloc[rng.permutation(len(y))].set_axis(y.index)
    x_tr, y_tr = ds.x.iloc[split.train], y.iloc[split.train]
    x_va, y_va = ds.x.iloc[split.val], y.iloc[split.val]
    model = fit_catboost(x_tr, y_tr, x_va, y_va, ds.cat_cols, cfg)
    raw_val = model.predict_proba(x_va)[:, 1]
    method, _ = select_calibration(raw_val, y_va.to_numpy(), params["calibration"])
    return model, Calibrator.fit(method, raw_val, y_va.to_numpy())


def main() -> None:
    params = load_params()
    ds = load_dataset(params)
    split = three_way_split(ds.y, params)
    x_te, y_te = ds.x.iloc[split.test], ds.y.iloc[split.test].to_numpy()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {}
    for name, seed, permute in (("healthy_candidate", 7, False), ("degraded_candidate", 42, True)):
        model, calibrator = build(ds, split, params, seed=seed, permute_labels=permute)
        path = OUT_DIR / f"{name}.cbm"
        model.save_model(str(path))
        calibrator.save(calibration_path_for(path))
        m = prob_metrics(y_te, calibrator.transform(model.predict_proba(x_te)[:, 1]))
        report[name] = {
            "artifact": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "calibration": calibrator.method,
            "roc_auc": round(m["roc_auc"], 4),
            "brier": round(m["brier"], 4),
        }
    (OUT_DIR / "demo_candidates.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
