"""Does the Telco finding generalise? Same pipeline on a bank churn dataset.

Dataset: "Bank Customer Churn" (10,000 customers of a European bank), OpenML
data_id 46911 as curated by the TabArena team; original upload
https://www.kaggle.com/datasets/gauravtopre/bank-customer-churn-dataset.
Licence: OpenML/TabArena declare it "Public"; the Kaggle page says "Other
(specified in description)". It is downloaded at run time (no account needed)
into data/external/ and never committed.

Same protocol as the Telco model, unchanged: stratified 60/20/20 split (seed 42),
5-fold CV on train+validation for dummy / logistic regression / CatBoost (with
and without balanced class weight) / LightGBM with the hyperparameters in
params.yaml, paired bootstrap vs logistic regression on the pooled out-of-fold
scores, test split scored once, calibration for CatBoost chosen on validation.
`gender` is excluded as on Telco. Nothing here is served.

Usage:
    python ml/training/second_dataset.py      # reports/experiments/second_dataset.md, reports/experiments/second_dataset.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    MODEL_NAMES,
    PROB_METRICS,
    REPO_ROOT,
    category_levels,
    fit_catboost,
    fit_model,
    load_params,
    mean_ci,
    paired_bootstrap,
    predict,
    prob_metrics,
    three_way_split,
)
from train import select_calibration  # noqa: E402

from ml.calibration import Calibrator  # noqa: E402

OPENML_ID = 46911
CSV = REPO_ROOT / "data" / "external" / "bank-customer-churn.csv"
DOCS = REPO_ROOT / "reports" / "experiments"
TARGET = "churn"
DROP = ["gender"]
CATEGORICAL = ["country", "credit_card", "active_member"]
BASELINE = "logistic_regression"
LABELS = {
    "dummy": "Dummy (predict base rate)",
    "logistic_regression": "Logistic regression (one-hot + scaling)",
    "catboost": "CatBoost, no class weight",
    "catboost_weighted": "CatBoost, balanced class weight",
    "lightgbm": "LightGBM",
}


def download() -> pd.DataFrame:
    if not CSV.exists():
        from sklearn.datasets import fetch_openml

        frame = fetch_openml(data_id=OPENML_ID, as_frame=True, parser="auto",
                             data_home=str(REPO_ROOT / "data" / "external" / "openml_cache")).frame
        CSV.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(CSV, index=False)
    return pd.read_csv(CSV)


def prepare(df: pd.DataFrame):
    # TabArena's copy encodes the label as "Yes"/"No" (the Kaggle original uses 1/0).
    y = df[TARGET].astype(str).isin(["Yes", "1"]).astype(int)
    x = df.drop(columns=[TARGET] + DROP)
    for col in CATEGORICAL:
        x[col] = x[col].astype(str)
    return x, y


def fit_lr_nonlinear(x_fit, y_fit, cfg: dict):
    """Logistic regression with the two shapes trees can find on their own:
    products_number one-hot and a cubic spline on age (the hypothesis check)."""
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

    numeric = [c for c in x_fit.columns if c not in CATEGORICAL + ["age", "products_number"]]
    model = make_pipeline(
        ColumnTransformer([
            ("num", StandardScaler(), numeric),
            ("age", SplineTransformer(n_knots=6, degree=3), ["age"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL + ["products_number"]),
        ]),
        LogisticRegression(C=cfg["C"], max_iter=cfg["max_iter"]),
    )
    return model.fit(x_fit, y_fit)


def main() -> None:
    params = load_params()
    raw = download()
    sha = hashlib.sha256(CSV.read_bytes()).hexdigest()
    x, y = prepare(raw)
    split = three_way_split(y, params)
    cats = category_levels(x, CATEGORICAL)
    boot = params["bootstrap"]

    # Cross-validation on train+validation
    dev = split.dev
    x_dev, y_dev = x.iloc[dev], y.iloc[dev]
    skf = StratifiedKFold(n_splits=params["cv"]["folds"], shuffle=True, random_state=params["cv"]["seed"])
    folds = {m: [] for m in MODEL_NAMES}
    oof = {m: np.zeros(len(dev)) for m in MODEL_NAMES}
    oof_nl, folds_nl = np.zeros(len(dev)), []
    for k, (fit_idx, score_idx) in enumerate(skf.split(x_dev, y_dev), start=1):
        for name in MODEL_NAMES:
            model = fit_model(name, x_dev.iloc[fit_idx], y_dev.iloc[fit_idx], CATEGORICAL, params, cats)
            p = predict(model, x_dev.iloc[score_idx])
            oof[name][score_idx] = p
            folds[name].append(prob_metrics(y_dev.iloc[score_idx], p))
        lr_nl = fit_lr_nonlinear(x_dev.iloc[fit_idx], y_dev.iloc[fit_idx], params["models"]["logistic_regression"])
        oof_nl[score_idx] = lr_nl.predict_proba(x_dev.iloc[score_idx])[:, 1]
        folds_nl.append(prob_metrics(y_dev.iloc[score_idx], oof_nl[score_idx]))
        print(f"  CV fold {k} done", flush=True)
    cv = {n: {m: mean_ci([f[m] for f in fs]) for m in PROB_METRICS} for n, fs in folds.items()}
    y_dev_a = y_dev.to_numpy()
    cv_diffs = {n: paired_bootstrap(y_dev_a, oof[n], oof[BASELINE], boot["n_resamples"], boot["seed"])
                for n in MODEL_NAMES if n != BASELINE}
    nonlinear = {
        "cv": {m: mean_ci([f[m] for f in folds_nl]) for m in PROB_METRICS},
        "vs_logreg": paired_bootstrap(y_dev_a, oof_nl, oof[BASELINE], boot["n_resamples"], boot["seed"]),
        "catboost_minus_it": paired_bootstrap(y_dev_a, oof["catboost"], oof_nl, boot["n_resamples"], boot["seed"]),
    }

    # Test split, once: comparison models refit on train+validation
    x_te, y_te = x.iloc[split.test], y.iloc[split.test].to_numpy()
    test_scores = {n: predict(fit_model(n, x_dev, y_dev, CATEGORICAL, params, cats), x_te) for n in MODEL_NAMES}
    test = {n: prob_metrics(y_te, p) for n, p in test_scores.items()}
    test_diffs = {n: paired_bootstrap(y_te, test_scores[n], test_scores[BASELINE], boot["n_resamples"], boot["seed"])
                  for n in ("catboost", "lightgbm")}

    # CatBoost as it would be shipped: fit on train, early stop + calibration on validation
    cb = fit_catboost(x.iloc[split.train], y.iloc[split.train], x.iloc[split.val], y.iloc[split.val],
                      CATEGORICAL, params["models"]["catboost"])
    raw_val = cb.predict_proba(x.iloc[split.val])[:, 1]
    method, cal_table = select_calibration(raw_val, y.iloc[split.val].to_numpy(), params["calibration"])
    calibrated = Calibrator.fit(method, raw_val, y.iloc[split.val].to_numpy()).transform(cb.predict_proba(x_te)[:, 1])

    result = {
        "dataset": {"openml_id": OPENML_ID, "rows": int(len(raw)), "positive_rate": float(y.mean()),
                    "sha256": sha, "features": list(x.columns), "excluded": DROP},
        "split": {"train": int(len(split.train)), "val": int(len(split.val)), "test": int(len(split.test))},
        "cv": cv, "cv_paired_bootstrap_vs_logreg": cv_diffs,
        "logreg_nonlinear_hypothesis_check": nonlinear,
        "test": test, "test_paired_bootstrap_vs_logreg": test_diffs,
        "catboost_shipped_recipe": {"best_iteration": int(cb.get_best_iteration()), "calibration": method,
                                    "calibration_cross_fitted_on_validation": cal_table,
                                    "test_calibrated": prob_metrics(y_te, calibrated)},
    }
    (DOCS / "second_dataset.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    def ci(d): return f"{d['mean']:.3f} [{d['ci_low']:.3f}, {d['ci_high']:.3f}]"
    def diff(d): return f"{d['diff']:+.4f} [{d['ci_low']:+.4f}, {d['ci_high']:+.4f}]"
    lines = [
        "# Second dataset: bank customer churn",
        "",
        "Generated by `python ml/training/second_dataset.py`. Do not edit by hand.",
        "",
        f"OpenML data_id {OPENML_ID} (Bank Customer Churn, curated by TabArena; original on Kaggle). "
        f"{len(raw):,} customers, churn rate {y.mean():.1%}, file sha256 `{sha[:16]}...`. Licence: OpenML/TabArena "
        "say \"Public\", Kaggle says \"Other (specified in description)\"; downloaded at run time, not committed. "
        f"Features: {', '.join(x.columns)}; `gender` excluded as on Telco. Same split, models, hyperparameters "
        "and evaluation as the Telco pipeline (`params.yaml`).",
        "",
        "## Cross-validation on train+validation (mean [95% t-interval over folds])",
        "",
        "| Model | ROC-AUC | PR-AUC | Brier | Log loss |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {LABELS[n]} | " + " | ".join(ci(cv[n][m]) for m in PROB_METRICS) + " |" for n in MODEL_NAMES]
    lines += ["", f"## Paired bootstrap vs logistic regression, pooled out-of-fold scores (n = {len(dev):,})", "",
              "| Model | Δ ROC-AUC | Δ PR-AUC | Δ Brier | Δ Log loss |", "|---|---|---|---|---|"]
    lines += [f"| {LABELS[n]} | " + " | ".join(diff(cv_diffs[n][m]) for m in PROB_METRICS) + " |"
              for n in MODEL_NAMES if n != BASELINE]
    lines += ["", "## Why the gap? Hypothesis check", "",
              "Logistic regression with `products_number` one-hot and a cubic spline on `age` (the two "
              "non-linear shapes a tree model finds by itself), same CV folds:", "",
              "| Comparison (pooled out-of-fold, n = " + f"{len(dev):,}" + ") | Δ ROC-AUC | Δ PR-AUC | Δ Brier | Δ Log loss |",
              "|---|---|---|---|---|",
              "| Non-linear LR minus plain LR | " + " | ".join(diff(nonlinear["vs_logreg"][m]) for m in PROB_METRICS) + " |",
              "| CatBoost minus non-linear LR | " + " | ".join(diff(nonlinear["catboost_minus_it"][m]) for m in PROB_METRICS) + " |",
              "", f"Non-linear LR CV ROC-AUC: {ci(nonlinear['cv']['roc_auc'])}."]
    lines += ["", f"## Test split, scored once (n = {len(split.test):,})", "",
              "| Model | ROC-AUC | PR-AUC | Brier | Log loss |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {LABELS[n]}, refit on train+val | " + " | ".join(f"{test[n][m]:.4f}" for m in PROB_METRICS) + " |"
              for n in MODEL_NAMES]
    lines += ["", "| Model minus logistic regression (test) | Δ ROC-AUC | Δ PR-AUC | Δ Brier | Δ Log loss |",
              "|---|---|---|---|---|"]
    lines += [f"| {LABELS[n]} | " + " | ".join(diff(test_diffs[n][m]) for m in PROB_METRICS) + " |"
              for n in ("catboost", "lightgbm")]
    sc = result["catboost_shipped_recipe"]
    lines += ["", f"CatBoost with the served recipe (train only; early stopping and calibration on validation): "
              f"calibration selected **{method}**; test ROC-AUC {sc['test_calibrated']['roc_auc']:.4f}, "
              f"Brier {sc['test_calibrated']['brier']:.4f}.", ""]
    (DOCS / "second_dataset.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"cv_auc": {n: round(cv[n]["roc_auc"]["mean"], 4) for n in MODEL_NAMES},
                      "catboost_minus_lr_oof": cv_diffs["catboost"]["roc_auc"],
                      "nonlinear_lr_auc": nonlinear["cv"]["roc_auc"]["mean"],
                      "catboost_minus_nonlinear_lr": nonlinear["catboost_minus_it"]["roc_auc"],
                      "calibration": method}, indent=2))


if __name__ == "__main__":
    main()
