"""The README's headline numbers must match the generated outputs they come from.

Each claim is recomputed from the committed results of a pipeline command
(docs/*.json, docs/demo_all.md) and the exact formatted string must appear in
README.md. Re-running a command that changes a number makes this test fail
until the README is updated, so the README cannot drift from the evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _json(name: str) -> dict:
    return json.loads((REPO_ROOT / "docs" / name).read_text(encoding="utf-8"))


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
        ("served test AUC/Brier", f"| {shipped['calibrated']['roc_auc']:.4f} | {shipped['calibrated']['brier']:.4f} |"),
        ("challenger test AUC/Brier", f"| {chal['challenger']['roc_auc']:.4f} | {chal['challenger']['brier']:.4f} |"),
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
def test_readme_states_the_measured_number(name, expected):
    assert expected in README, f"README should contain {expected!r} for {name}"


def test_demo_numbers_match_the_demo_transcript():
    demo = (REPO_ROOT / "docs" / "demo_all.md").read_text(encoding="utf-8")
    healthy = re.search(r"disagreement rate \*\*([\d.]+)%\*\*", demo).group(1)
    rolled = re.search(r"auto-rolled back after \*\*(\d+)\*\* requests", demo).group(1)
    degraded = re.search(r"rate \*\*([\d.]+)%\*\* \(limit", demo.split("Degraded retrain")[1]).group(1)
    assert "HTTP **409**" in demo
    assert f"healthy retrain ({healthy}%)" in README
    assert f"after {rolled} requests at {degraded}% disagreement" in README
