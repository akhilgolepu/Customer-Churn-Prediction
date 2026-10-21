"""Hand-written numbers must match the generated outputs they come from.

Each claim is recomputed from the committed results of a pipeline command
(reports/**/*.json, reports/demos/demo_all.md, reports/loadtest/*.csv) and the exact formatted
string must appear in the hand-written pages that quote it: README.md, or for
the detail moved out of it, docs/interview_notes.md and docs/results.md.
Re-running a command that changes a number makes this test fail until the
pages are updated, so they cannot drift from the evidence.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
QUOTED = "\n".join(
    (REPO_ROOT / p).read_text(encoding="utf-8") for p in ("README.md", "docs/interview_notes.md", "docs/results.md")
)


def _json(name: str) -> dict:
    matches = sorted((REPO_ROOT / "reports").rglob(name))
    assert len(matches) == 1, f"expected one reports/**/{name}, found {matches}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


def _signed(x: float, digits: int) -> str:
    return f"{x:+.{digits}f}"


def _ci(d: dict, digits: int) -> str:
    return f"{_signed(d['ci_low'], digits)}, {_signed(d['ci_high'], digits)}"


def claims() -> list[tuple[str, str]]:
    ev = _json("evaluation.json")
    th = _json("threshold_analysis.json")
    bank = _json("second_dataset.json")
    perm = _json("permutation_check.json")["summary"]
    shipped = ev["shipped_test"]
    cv = ev["cv_paired_bootstrap_vs_logreg"]["catboost"]
    chal = ev["challenger_test"]
    primary = th["scenarios"]["margin_with_incentive"]
    test = primary["test"]
    gain = test["empirical_from_validation"]["net_benefit_per_1000"] - test["threshold_0.50"]["net_benefit_per_1000"]
    gain_ci = th["primary_bootstrap_95ci_per_1000"]["empirical_minus_0.50_test"]
    seniors = {r["value"]: r["roc_auc"] for r in ev["slices_test"]["slices"]["SeniorCitizen"]}
    bank_cb = bank["cv_paired_bootstrap_vs_logreg"]["catboost"]["roc_auc"]
    bank_nl = bank["logreg_nonlinear_hypothesis_check"]["catboost_minus_it"]["roc_auc"]
    return [
        ("test ROC-AUC", f"{shipped['calibrated']['roc_auc']:.3f} (95% CI {shipped['roc_auc_ci'][0]:.3f} to {shipped['roc_auc_ci'][1]:.3f})"),
        ("CV AUC difference vs LR", f"{_signed(cv['roc_auc']['diff'], 4)}, 95% CI {_signed(cv['roc_auc']['ci_low'], 4)} to {_signed(cv['roc_auc']['ci_high'], 4)}"),
        ("CV Brier difference vs LR", f"{_signed(cv['brier']['diff'], 4)} [{_ci(cv['brier'], 4)}]"),
        ("decision disagreement", f"{chal['disagreement_rate_at_threshold']:.1%} of customers"),
        ("ECE served", f"ECE {shipped['ece_calibrated']:.3f}"),
        ("ECE old weighted", f"{ev['reliability_test']['CatBoost, balanced class weight']['ece']:.3f}"),
        ("threshold", f"{primary['empirical_threshold_validation']:.2f}"),
        ("closed-form threshold", f"{primary['closed_form_threshold']:.3f}"),
        ("gain vs 0.50", f"+${gain:,.0f} per 1,000"),
        ("gain CI", f"-${-gain_ci[0]:,.0f} to +${gain_ci[1]:,.0f}"),
        ("bank CatBoost vs LR", f"{_signed(bank_cb['diff'], 3)} (95% CI {_ci(bank_cb, 3).replace(', ', ' to ')})"),
        ("bank after non-linear LR", f"{_signed(bank_nl['diff'], 4)}"),
        ("bank rows", f"{bank['dataset']['rows']:,}-customer"),
        ("permutation mean/SD", f"averaged {perm['permuted_model_auc']['mean']:.3f} with SD {perm['permuted_model_auc']['sd']:.3f}"),
        ("permutation control SD", f"SD {perm['control_auc']['sd']:.3f} for label-independent scores"),
        ("senior AUC gap", f"({seniors['1']:.3f} vs {seniors['0']:.3f})"),
    ]


@pytest.mark.parametrize("name, expected", claims(), ids=[c[0] for c in claims()])
def test_quoted_number_matches_its_source(name, expected):
    assert expected in QUOTED, f"README/interview notes/results should contain {expected!r} for {name}"


def _cell(d: dict) -> str:
    return f"{d['mean']:.4f} [{d['ci_low']:.4f}, {d['ci_high']:.4f}]"


def test_readme_results_table_matches_cross_validation():
    cv = _json("evaluation.json")["cv"]
    for key in ("logistic_regression", "catboost", "lightgbm"):
        row = f"| {_cell(cv[key]['roc_auc'])} | {_cell(cv[key]['brier'])} |"
        assert row in README, f"README CV row for {key} should be {row!r}"


def test_readme_states_the_cost_assumptions():
    th = _json("threshold_analysis.json")
    p = th["scenarios"]["margin_with_incentive"]
    assert f"a ${p['offer_cost']:.0f} retention offer, a {p['save_rate']:.0%} save rate" in README
    readme = README.replace("\r\n", "\n")
    value = (f"{th['horizon_months']} months x ${th['mean_monthly_charge_of_churners_train_val']:.2f} mean\n"
             f"monthly charge x {p['margin']:.0%} margin = ${p['value_per_retained_customer']:.2f}")
    assert value in readme


def test_demo_numbers_match_the_demo_transcript():
    demo = (REPO_ROOT / "reports" / "demos" / "demo_all.md").read_text(encoding="utf-8")
    healthy = re.search(r"disagreement rate \*\*([\d.]+)%\*\*", demo).group(1)
    rolled = re.search(r"auto-rolled back after \*\*(\d+)\*\* requests", demo).group(1)
    degraded = re.search(r"rate \*\*([\d.]+)%\*\* \(limit", demo.split("Degraded retrain")[1]).group(1)
    assert "HTTP **409**" in demo
    assert f"healthy retrain ({healthy}%)" in QUOTED
    assert f"after {rolled} requests at {degraded}% disagreement" in QUOTED


def test_dashboard_states_the_measured_test_auc():
    """The frontend header quotes the test AUC; it once showed an unmeasured "F1 0.73"."""
    dashboard = (REPO_ROOT / "frontend" / "src" / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
    auc = _json("evaluation.json")["shipped_test"]["calibrated"]["roc_auc"]
    assert f"Test ROC-AUC:</span> {auc:.3f}" in dashboard
    assert "F1 0.73" not in dashboard


def _locust(name: str) -> dict:
    with (REPO_ROOT / "reports" / "loadtest" / f"{name}_stats.csv").open(encoding="utf-8") as f:
        return next(r for r in csv.DictReader(f) if r["Name"] == "Aggregated")


def test_load_numbers_match_the_committed_locust_csvs():
    w1, w2 = _locust("u100_w1_mixed"), _locust("u100_w2_mixed")
    p95_20 = sorted(int(_locust(n)["95%"]) for n in ("u20_w1_predict_only", "u20_w1_mixed", "u20_w2_mixed"))
    assert f"About {float(w2['Requests/s']):.0f} req/s with 2 workers, {float(w1['Requests/s']):.0f} with 1" in README
    assert f"p95 {p95_20[0]} to {p95_20[-1]} ms at 20 users" in README
