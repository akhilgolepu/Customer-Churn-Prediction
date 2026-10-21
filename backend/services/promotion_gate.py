"""Pre-promotion gate: score a candidate on labelled data and run ModelValidationGate.

Called by ModelRegistryService.promote_candidate before the active model is
swapped. Promotion is refused when there are blockers, unless an admin passes
an explicit, audit-logged override.

The evaluation set is a labelled CSV in the raw Telco schema
(PROMOTION_EVAL_DATA_PATH). With the default (the full Telco CSV) it contains
rows the candidate was trained on, so its AUC is optimistic: this is a sanity
gate that catches broken or regressed models, not an unbiased estimate. With
real data, point it at recent labelled outcomes that no candidate trained on.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from services.model_validation_service import ModelValidationGate

# scorer(artifact_path) -> predict_fn(features_frame) -> calibrated P(churn) per row
Scorer = Callable[[str], Callable[[pd.DataFrame], np.ndarray]]


def _default_scorer(artifact_path: str) -> Callable[[pd.DataFrame], np.ndarray]:
    from model_loader import load_scorer

    return load_scorer(artifact_path)


def load_labelled_frame(path: Path) -> tuple[pd.DataFrame, np.ndarray]:
    from ml.preprocessing.preprocessing import load_artifacts, prepare_for_model, preprocess

    df = pd.read_csv(path)
    if "Churn" not in df.columns:
        raise ValueError(f"Evaluation data at {path} has no 'Churn' column")
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    y = (df["Churn"].astype(str) == "Yes").astype(int).to_numpy()
    feature_list, cat_cols = load_artifacts()
    x = prepare_for_model(preprocess(df.drop(columns=["Churn"])), feature_list)
    for col in cat_cols:
        x[col] = x[col].astype(str)
    return x, y


class PromotionGate:
    def __init__(
        self,
        eval_data_path: str | Path,
        decision_threshold: float,
        min_auc: float = 0.75,
        min_precision: float = 0.0,
        min_recall: float = 0.0,
        min_f1: float = 0.0,
        max_auc_drop: float = 0.02,
        scorer: Scorer | None = None,
    ) -> None:
        self._eval_data_path = Path(eval_data_path)
        self._threshold = float(decision_threshold)
        self._quality_config = {
            "min_auc": min_auc,
            "min_precision": min_precision,
            "min_recall": min_recall,
            "min_f1": min_f1,
        }
        self._max_auc_drop = float(max_auc_drop)
        self._scorer = scorer or _default_scorer

    def evaluate(self, model_version: str, candidate_artifact: str, active_artifact: str | None) -> dict:
        base = {
            "model_version": model_version,
            "eval_data_path": str(self._eval_data_path),
            "decision_threshold": self._threshold,
            "thresholds": {**self._quality_config, "max_auc_drop_vs_active": self._max_auc_drop},
        }
        if not self._eval_data_path.exists():
            return {
                **base,
                "promotion_allowed": False,
                "blockers": [
                    f"No labelled evaluation data at {self._eval_data_path}; the gate cannot validate the candidate"
                ],
                "warnings": [],
                "checks": [],
            }

        x, y = load_labelled_frame(self._eval_data_path)
        try:
            predict_candidate = self._scorer(candidate_artifact)
        except Exception as exc:  # unreadable artifact is a blocker, not a 500
            return {**base, "promotion_allowed": False, "blockers": [f"Candidate artifact could not be loaded: {exc}"],
                    "warnings": [], "checks": []}

        p = np.asarray(predict_candidate(x), dtype=float)
        started = time.perf_counter()
        predict_candidate(x.iloc[:1])
        single_row_ms = (time.perf_counter() - started) * 1000

        gate = ModelValidationGate()
        gate.quality_validator.config.update(self._quality_config)
        report = gate.validate_for_promotion(
            model_version=model_version,
            y_true=y,
            y_pred_proba=p,
            y_pred_binary=(p >= self._threshold).astype(int),
            latency_measurements={"model_predict": single_row_ms},
            test_df=x,
            expected_columns=list(x.columns),
            expected_dtypes={col: "object" for col in x.columns if x[col].dtype == object},
        )
        blockers = list(report.blockers)
        warnings = list(report.warnings)

        candidate_summary = {"roc_auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p))}
        active_summary = None
        if active_artifact and active_artifact != candidate_artifact:
            try:
                p_active = np.asarray(self._scorer(active_artifact)(x), dtype=float)
                active_summary = {
                    "roc_auc": float(roc_auc_score(y, p_active)),
                    "brier": float(brier_score_loss(y, p_active)),
                }
                drop = active_summary["roc_auc"] - candidate_summary["roc_auc"]
                if drop > self._max_auc_drop:
                    blockers.append(
                        f"Candidate ROC-AUC {candidate_summary['roc_auc']:.4f} is {drop:.4f} below the active model "
                        f"({active_summary['roc_auc']:.4f}); allowed drop is {self._max_auc_drop:.4f}"
                    )
            except Exception as exc:
                warnings.append(f"Active model could not be scored for comparison: {exc}")

        return {
            **base,
            "promotion_allowed": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "eval_rows": int(len(y)),
            "candidate": candidate_summary,
            "active": active_summary,
            "checks": report.checks,
        }
