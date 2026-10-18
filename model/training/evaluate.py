"""Model comparison, calibration report and slice metrics.

  * Stratified 5-fold CV on train+validation for dummy, logistic regression,
    CatBoost (shipped recipe, no class weight), CatBoost with the old balanced
    class weight, and LightGBM: mean and 95% interval per metric, plus a paired
    bootstrap of every model against logistic regression on the pooled
    out-of-fold scores.
  * Test split, reported once: every comparison model refit on train+validation,
    and the shipped (train-only, calibrated) artifact as written by train.py.
  * Reliability diagram on the test split.
  * Slice metrics on the test split (SeniorCitizen, TenureGroup, Contract,
    InternetService).

Nothing here chooses anything; it only measures.

Outputs: docs/model_comparison.md, docs/reliability_diagram.png,
docs/slice_metrics.md, docs/evaluation.json, metrics.json

Usage:
    python model/training/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import precision_score, recall_score
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    MODEL_NAMES,
    PROB_METRICS,
    REPO_ROOT,
    bootstrap_ci,
    category_levels,
    fit_model,
    load_dataset,
    load_params,
    mean_ci,
    paired_bootstrap,
    predict,
    prob_metrics,
    three_way_split,
)

from model.calibration import Calibrator  # noqa: E402

DOCS = REPO_ROOT / "docs"
LABELS = {
    "dummy": "Dummy (predict base rate)",
    "logistic_regression": "Logistic regression (one-hot + scaling)",
    "catboost": "CatBoost, no class weight (shipped recipe)",
    "catboost_weighted": "CatBoost, balanced class weight (old recipe)",
    "lightgbm": "LightGBM",
}
BASELINE = "logistic_regression"


def cross_validate(ds, split, params):
    dev = split.dev
    x_dev, y_dev = ds.x.iloc[dev], ds.y.iloc[dev]
    categories = category_levels(ds.x, ds.cat_cols)
    cv = params["cv"]
    skf = StratifiedKFold(n_splits=cv["folds"], shuffle=True, random_state=cv["seed"])
    per_fold = {m: [] for m in MODEL_NAMES}
    oof = {m: np.zeros(len(dev)) for m in MODEL_NAMES}
    for k, (fit_idx, score_idx) in enumerate(skf.split(x_dev, y_dev), start=1):
        for name in MODEL_NAMES:
            model = fit_model(name, x_dev.iloc[fit_idx], y_dev.iloc[fit_idx], ds.cat_cols, params, categories)
            p = predict(model, x_dev.iloc[score_idx])
            oof[name][score_idx] = p
            per_fold[name].append(prob_metrics(y_dev.iloc[score_idx], p))
        print(f"  CV fold {k}/{cv['folds']} done", flush=True)
    summary = {
        name: {m: mean_ci([f[m] for f in folds]) for m in PROB_METRICS} for name, folds in per_fold.items()
    }
    return summary, oof, y_dev.to_numpy()


def test_once(ds, split, params):
    categories = category_levels(ds.x, ds.cat_cols)
    x_dev, y_dev = ds.x.iloc[split.dev], ds.y.iloc[split.dev]
    x_te = ds.x.iloc[split.test]
    return {
        name: predict(fit_model(name, x_dev, y_dev, ds.cat_cols, params, categories), x_te) for name in MODEL_NAMES
    }


def shipped_scores(ds, split, params):
    from catboost import CatBoostClassifier

    model = CatBoostClassifier()
    model.load_model(str(REPO_ROOT / params["output"]["model_path"]))
    calibrator = Calibrator.load(REPO_ROOT / params["output"]["calibration_path"])
    raw = model.predict_proba(ds.x.iloc[split.test])[:, 1]
    return raw, calibrator.transform(raw), calibrator


def reliability(y, p, bins: int) -> dict:
    edges = np.linspace(0.0, 1.0, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        mask = which == b
        n = int(mask.sum())
        if n == 0:
            continue
        mean_p, obs = float(p[mask].mean()), float(y[mask].mean())
        ece += n / len(y) * abs(obs - mean_p)
        rows.append({"bin_low": float(edges[b]), "bin_high": float(edges[b + 1]), "n": n, "mean_predicted": mean_p, "observed_rate": obs})
    return {"bins": rows, "ece": float(ece)}


def plot_reliability(curves: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, muted, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    series = [("#2a78d6", "o"), ("#eb6834", "s"), ("#1baf7a", "^")]
    fig, (ax, axh) = plt.subplots(
        2, 1, figsize=(6.4, 7.2), gridspec_kw={"height_ratios": [3, 1]}, sharex=True, facecolor=surface
    )
    for a in (ax, axh):
        a.set_facecolor(surface)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(muted)
        a.tick_params(colors=muted, labelsize=9)
        a.grid(True, color=grid, linewidth=0.8)
        a.set_axisbelow(True)
    ax.plot([0, 1], [0, 1], color=muted, linewidth=1.2, linestyle="--", label="Perfect calibration")
    width = 0.1 / (len(curves) + 1)
    for i, (label, rel) in enumerate(curves.items()):
        color, marker = series[i]
        xs = [r["mean_predicted"] for r in rel["bins"]]
        ys = [r["observed_rate"] for r in rel["bins"]]
        ax.plot(xs, ys, color=color, marker=marker, markersize=8, linewidth=2,
                markeredgecolor=surface, markeredgewidth=1.5, label=f"{label} (ECE {rel['ece']:.3f})")
        centers = [(r["bin_low"] + r["bin_high"]) / 2 for r in rel["bins"]]
        axh.bar([c + (i - (len(curves) - 1) / 2) * width for c in centers], [r["n"] for r in rel["bins"]],
                width=width * 0.9, color=color, edgecolor=surface, linewidth=0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Observed churn rate in bin", color=ink, fontsize=10)
    ax.set_title("Reliability on the held-out test split (n = 1,409)", color=ink, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=8.5, labelcolor=ink, loc="upper left")
    axh.set_ylabel("Rows per bin", color=ink, fontsize=10)
    axh.set_xlabel("Predicted churn probability (10 equal-width bins)", color=ink, fontsize=10)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)


def at_threshold(y, p, thr) -> dict:
    pred = (p >= thr).astype(int)
    return {
        "threshold": thr,
        "flagged_pct": float(pred.mean()),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
    }


def slice_report(ds, split, p, thr, params) -> dict:
    from model.preprocessing.preprocessing import preprocess

    cfg, bcfg = params["slices"], params["bootstrap"]
    raw_te = ds.raw.iloc[split.test].reset_index(drop=True)
    groups = preprocess(raw_te)  # adds TenureGroup
    y = ds.y.iloc[split.test].to_numpy()
    overall = {**prob_metrics(y, p), **at_threshold(y, p, thr), "mean_predicted": float(p.mean()), "observed_rate": float(y.mean())}
    out = {"overall": overall, "threshold": thr, "slices": {}}
    for col in cfg["columns"]:
        rows = []
        for value in sorted(groups[col].astype(str).unique()):
            mask = (groups[col].astype(str) == value).to_numpy()
            ys, ps = y[mask], p[mask]
            row = {"value": value, "n": int(mask.sum()), "positives": int(ys.sum()),
                   "observed_rate": float(ys.mean()), "mean_predicted": float(ps.mean()),
                   **at_threshold(ys, ps, thr)}
            row["calibration_gap"] = row["mean_predicted"] - row["observed_rate"]
            if 0 < ys.sum() < len(ys):
                row["roc_auc"] = prob_metrics(ys, ps)["roc_auc"]
                row["roc_auc_ci"] = bootstrap_ci(ys, ps, "roc_auc", n=1000, seed=bcfg["seed"])
            else:
                row["roc_auc"], row["roc_auc_ci"] = None, None
            flags = []
            if row["n"] >= cfg["min_rows"]:
                if row["roc_auc"] is not None and overall["roc_auc"] - row["roc_auc"] > cfg["max_auc_gap"]:
                    flags.append("AUC")
                if abs(row["calibration_gap"]) > cfg["max_calibration_gap"]:
                    flags.append("calibration")
                if row["positives"] >= 10 and overall["recall"] - row["recall"] > cfg["max_recall_gap"]:
                    flags.append("recall")
            else:
                flags.append("too few rows")
            row["flags"] = flags
            rows.append(row)
        out["slices"][col] = rows
    return out


def fmt_ci(d: dict, digits: int = 4) -> str:
    return f"{d['mean']:.{digits}f} [{d['ci_low']:.{digits}f}, {d['ci_high']:.{digits}f}]"


def fmt_diff(d: dict) -> str:
    return f"{d['diff']:+.4f} [{d['ci_low']:+.4f}, {d['ci_high']:+.4f}]"


def write_comparison_md(path, cv_summary, cv_diffs, test_metrics, test_diffs, shipped, cal, params, n_dev, n_test):
    lines = [
        "# Model comparison",
        "",
        "Generated by `python model/training/evaluate.py` (settings in `params.yaml`). Do not edit by hand.",
        "",
        f"Data: IBM Telco Customer Churn, stratified 60/20/20 split, seed {params['split']['seed']}. "
        f"Cross-validation uses train+validation ({n_dev:,} rows, {params['cv']['folds']} stratified folds); "
        f"the test split ({n_test:,} rows) is scored once. Boosting models early-stop on an inner "
        f"{params['cv']['inner_early_stopping_size']:.0%} of the rows they are trained on, never on scoring rows. "
        "The comparison models are uncalibrated; the shipped artifact row uses the calibration chosen by `train.py`.",
        "",
        "## Cross-validation (mean [95% t-interval over folds])",
        "",
        "| Model | ROC-AUC | PR-AUC | Brier | Log loss |",
        "|---|---|---|---|---|",
    ]
    for name in MODEL_NAMES:
        s = cv_summary[name]
        lines.append(f"| {LABELS[name]} | " + " | ".join(fmt_ci(s[m]) for m in PROB_METRICS) + " |")
    lines += [
        "",
        "Fold intervals are optimistic about precision (folds share training rows); the paired bootstrap below is the comparison to rely on.",
        "",
        f"## Paired bootstrap vs logistic regression, pooled out-of-fold scores (n = {n_dev:,}, {params['bootstrap']['n_resamples']} resamples)",
        "",
        "Difference = model minus logistic regression, [95% interval]. Higher is better for AUCs, lower is better for Brier and log loss.",
        "",
        "| Model | Δ ROC-AUC | Δ PR-AUC | Δ Brier | Δ Log loss |",
        "|---|---|---|---|---|",
    ]
    for name in MODEL_NAMES:
        if name == BASELINE:
            continue
        lines.append(f"| {LABELS[name]} | " + " | ".join(fmt_diff(cv_diffs[name][m]) for m in PROB_METRICS) + " |")
    lines += [
        "",
        f"## Held-out test split, reported once (n = {n_test:,})",
        "",
        "| Model | ROC-AUC | PR-AUC | Brier | Log loss |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in MODEL_NAMES:
        t = test_metrics[name]
        lines.append(f"| {LABELS[name]}, refit on train+val | " + " | ".join(f"{t[m]:.4f}" for m in PROB_METRICS) + " |")
    lines.append(
        f"| **Shipped artifact** (CatBoost on train, calibration: {cal.method}) | "
        + " | ".join(f"{shipped[m]:.4f}" for m in PROB_METRICS) + " |"
    )
    lines += [
        "",
        "Paired bootstrap on the test split, model minus logistic regression:",
        "",
        "| Model | Δ ROC-AUC | Δ PR-AUC | Δ Brier | Δ Log loss |",
        "|---|---|---|---|---|",
    ]
    for name, diffs in test_diffs.items():
        lines.append(f"| {LABELS.get(name, name)} | " + " | ".join(fmt_diff(diffs[m]) for m in PROB_METRICS) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_slices_md(path, report):
    o = report["overall"]
    lines = [
        "# Slice metrics (held-out test split)",
        "",
        "Generated by `python model/training/evaluate.py`. Shipped model, calibrated score, "
        f"decision threshold {report['threshold']:.2f}.",
        "",
        f"Overall: n = 1,409, churn rate {o['observed_rate']:.3f}, mean predicted {o['mean_predicted']:.3f}, "
        f"ROC-AUC {o['roc_auc']:.3f}, flagged {o['flagged_pct']:.1%}, precision {o['precision']:.3f}, recall {o['recall']:.3f}.",
        "",
        "A slice is flagged when (with at least 50 rows) its AUC is more than 0.05 below overall, its mean predicted "
        "probability is more than 0.05 away from its observed churn rate, or its recall is more than 0.15 below overall. "
        "Slice AUC intervals are bootstrap (1,000 resamples) and wide: most slices have only a few hundred rows.",
        "",
    ]
    for col, rows in report["slices"].items():
        lines += [
            f"## {col}",
            "",
            "| Value | n | Churn rate | Mean predicted | Calib. gap | ROC-AUC [95% CI] | Flagged | Precision | Recall | Flags |",
            "|---|---:|---:|---:|---:|---|---:|---:|---:|---|",
        ]
        for r in rows:
            auc = "n/a" if r["roc_auc"] is None else f"{r['roc_auc']:.3f} [{r['roc_auc_ci'][0]:.3f}, {r['roc_auc_ci'][1]:.3f}]"
            lines.append(
                f"| {r['value']} | {r['n']} | {r['observed_rate']:.3f} | {r['mean_predicted']:.3f} | {r['calibration_gap']:+.3f} | "
                f"{auc} | {r['flagged_pct']:.1%} | {r['precision']:.3f} | {r['recall']:.3f} | {', '.join(r['flags']) or '-'} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    params = load_params()
    ds = load_dataset(params)
    split = three_way_split(ds.y, params)
    boot = params["bootstrap"]
    thr = float(params["evaluation"]["decision_threshold"])

    print("Cross-validating ...", flush=True)
    cv_summary, oof, y_dev = cross_validate(ds, split, params)
    print("Bootstrapping out-of-fold differences ...", flush=True)
    cv_diffs = {
        name: paired_bootstrap(y_dev, oof[name], oof[BASELINE], boot["n_resamples"], boot["seed"])
        for name in MODEL_NAMES if name != BASELINE
    }

    print("Scoring the test split once ...", flush=True)
    y_te = ds.y.iloc[split.test].to_numpy()
    test_scores = test_once(ds, split, params)
    test_metrics = {name: prob_metrics(y_te, p) for name, p in test_scores.items()}
    raw_te, cal_te, calibrator = shipped_scores(ds, split, params)
    shipped = prob_metrics(y_te, cal_te)
    test_diffs = {
        name: paired_bootstrap(y_te, test_scores[name], test_scores[BASELINE], boot["n_resamples"], boot["seed"])
        for name in ("catboost", "lightgbm")
    }
    test_diffs["shipped"] = paired_bootstrap(y_te, cal_te, test_scores[BASELINE], boot["n_resamples"], boot["seed"])
    LABELS["shipped"] = "Shipped artifact"

    bins = params["calibration"]["reliability_bins"]
    rel = {
        "Shipped CatBoost (no class weight)": reliability(y_te, cal_te, bins),
        "CatBoost, balanced class weight": reliability(y_te, test_scores["catboost_weighted"], bins),
        "Logistic regression": reliability(y_te, test_scores[BASELINE], bins),
    }
    plot_reliability(rel, DOCS / "reliability_diagram.png")

    slices = slice_report(ds, split, cal_te, thr, params)

    DOCS.mkdir(exist_ok=True)
    write_comparison_md(DOCS / "model_comparison.md", cv_summary, cv_diffs, test_metrics, test_diffs, shipped,
                        calibrator, params, len(split.dev), len(split.test))
    write_slices_md(DOCS / "slice_metrics.md", slices)

    evaluation = {
        "cv": cv_summary,
        "cv_paired_bootstrap_vs_logreg": cv_diffs,
        "test": test_metrics,
        "test_paired_bootstrap_vs_logreg": test_diffs,
        "shipped_test": {
            "calibration_method": calibrator.method,
            "raw": prob_metrics(y_te, raw_te),
            "calibrated": shipped,
            "ece_calibrated": rel["Shipped CatBoost (no class weight)"]["ece"],
            "at_decision_threshold": at_threshold(y_te, cal_te, thr),
            "roc_auc_ci": bootstrap_ci(y_te, cal_te, "roc_auc", boot["n_resamples"], boot["seed"]),
        },
        "reliability_test": rel,
        "slices_test": slices,
    }
    (DOCS / "evaluation.json").write_text(json.dumps(evaluation, indent=2), encoding="utf-8")

    metrics = {
        "test_roc_auc": shipped["roc_auc"],
        "test_pr_auc": shipped["pr_auc"],
        "test_brier": shipped["brier"],
        "test_log_loss": shipped["log_loss"],
        "test_ece": evaluation["shipped_test"]["ece_calibrated"],
        "cv_roc_auc_catboost": cv_summary["catboost"]["roc_auc"]["mean"],
        "cv_roc_auc_logreg": cv_summary[BASELINE]["roc_auc"]["mean"],
        "decision_threshold": thr,
        **{f"test_{k}_at_threshold": v for k, v in evaluation["shipped_test"]["at_decision_threshold"].items()
           if k != "threshold"},
    }
    (REPO_ROOT / params["output"]["metrics_path"]).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps({"cv_roc_auc": {k: round(v["roc_auc"]["mean"], 4) for k, v in cv_summary.items()},
                      "shipped_test": evaluation["shipped_test"]}, indent=2))
    print("Wrote docs/model_comparison.md, docs/slice_metrics.md, docs/reliability_diagram.png, docs/evaluation.json, metrics.json")


if __name__ == "__main__":
    main()
