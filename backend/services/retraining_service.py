from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from catboost import CatBoostClassifier
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from model.preprocessing.pipeline_bundle import build_pipeline_bundle
from model.preprocessing.preprocessing import (
    load_artifacts,
    preprocess,
    prepare_for_model,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrainingConfig:
    dataset_path: Path
    artifacts_dir: Path
    bundles_dir: Path
    retrained_dir: Path
    test_size: float = 0.2
    random_state: int = 42
    iterations: int = 200
    depth: int = 6
    learning_rate: float = 0.1


class RetrainingOrchestrator:
    """Trains, validates, packages, and optionally promotes a new model version."""

    def __init__(self, model_registry_service=None, config: RetrainingConfig | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        artifacts_dir = repo_root / "model" / "artifacts"

        self._config = config or RetrainingConfig(
            dataset_path=repo_root / "data" / "Telco-Customer-Churn.csv",
            artifacts_dir=artifacts_dir,
            bundles_dir=artifacts_dir / "bundles",
            retrained_dir=artifacts_dir / "retrained",
        )
        self._registry_service = model_registry_service

    async def run(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        return await asyncio.to_thread(self._run_sync, payload)

    def _run_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc).isoformat()
        reason = str(payload.get("reason", "manual"))
        auto_promote = bool(payload.get("auto_promote", False))
        max_rows = payload.get("max_rows")

        if payload.get("dry_run"):
            return {
                "status": "dry_run",
                "reason": reason,
                "dataset_path": str(self._config.dataset_path),
                "auto_promote": auto_promote,
                "started_at": started_at,
            }

        if not self._config.dataset_path.exists():
            raise FileNotFoundError(f"Retraining dataset not found: {self._config.dataset_path}")

        frame = pd.read_csv(self._config.dataset_path)
        if isinstance(max_rows, int) and max_rows > 0:
            frame = frame.head(max_rows)

        if "Churn" not in frame.columns:
            raise ValueError("Training dataset must include 'Churn' column")

        frame = self._clean_frame(frame)
        y = frame["Churn"].map({"No": 0, "Yes": 1}).astype(int)
        x_raw = frame.drop(columns=[col for col in ["Churn", "customerID"] if col in frame.columns])

        x_train_raw, x_test_raw, y_train, y_test = train_test_split(
            x_raw,
            y,
            test_size=self._config.test_size,
            random_state=self._config.random_state,
            stratify=y,
        )

        x_train_proc = preprocess(x_train_raw)
        x_test_proc = preprocess(x_test_raw)

        feature_list, cat_columns = self._resolve_feature_contract(x_train_proc)
        x_train = prepare_for_model(x_train_proc, feature_list=feature_list)
        x_test = prepare_for_model(x_test_proc, feature_list=feature_list)

        model = CatBoostClassifier(
            iterations=self._config.iterations,
            depth=self._config.depth,
            learning_rate=self._config.learning_rate,
            random_seed=self._config.random_state,
            verbose=False,
        )
        model.fit(x_train, y_train, cat_features=cat_columns)

        y_pred_proba = model.predict_proba(x_test)[:, 1]
        y_pred = (y_pred_proba >= 0.5).astype(int)

        metrics = {
            "auc": float(roc_auc_score(y_test, y_pred_proba)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        }

        version = str(payload.get("version") or self._default_version())
        output_paths = self._save_artifacts(model, feature_list, cat_columns, version)
        bundle_path = build_pipeline_bundle(
            model_path=output_paths["model_path"],
            feature_list_path=output_paths["feature_list_path"],
            cat_columns_path=output_paths["cat_columns_path"],
            output_dir=self._config.bundles_dir,
            version=version,
        )

        registry_result = self._register_and_validate(
            version=version,
            metrics=metrics,
            bundle_path=bundle_path,
            y_true=y_test.to_numpy(),
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred,
            protected_attribute=(x_test_raw["Contract"] == "Month-to-month").astype(int).to_numpy()
            if "Contract" in x_test_raw.columns
            else None,
            test_df=x_test,
        )

        promoted = False
        if auto_promote and registry_result.get("candidate_id") and registry_result.get("validation", {}).get("promotion_allowed"):
            promoted = self._promote_candidate(registry_result["candidate_id"])

        return {
            "status": "retraining_completed",
            "reason": reason,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "version": version,
            "rows_used": int(len(frame)),
            "metrics": metrics,
            "bundle_path": str(bundle_path),
            "registry": registry_result,
            "auto_promote_requested": auto_promote,
            "promoted": promoted,
        }

    def _register_and_validate(
        self,
        version: str,
        metrics: dict[str, float],
        bundle_path: Path,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        y_pred_binary: np.ndarray,
        protected_attribute: np.ndarray | None,
        test_df: pd.DataFrame,
    ) -> dict[str, Any]:
        if self._registry_service is None:
            return {"registered": False, "validation": None}

        candidate = self._registry_service.register_candidate(
            version=version,
            metrics=metrics,
            artifact_path=str(bundle_path),
        )

        expected_dtypes = {column: str(test_df[column].dtype) for column in test_df.columns}
        validation = self._registry_service.validate_candidate(
            model_version=version,
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
            protected_attribute=protected_attribute,
            latency_measurements={
                "preprocess": 0.0,
                "model_predict": 0.0,
                "api_e2e": 0.0,
            },
            memory_mb=0.0,
            test_df=test_df,
            expected_columns=list(test_df.columns),
            expected_dtypes=expected_dtypes,
        )

        return {
            "registered": True,
            "candidate_id": candidate.get("id"),
            "validation": validation,
        }

    def _promote_candidate(self, candidate_model_id: str) -> bool:
        try:
            self._registry_service.start_shadow_test(candidate_model_id)
            self._registry_service.promote_candidate(candidate_model_id)
            return True
        except Exception as exc:
            logger.exception("Auto-promotion failed for candidate %s: %s", candidate_model_id, exc)
            return False

    def _resolve_feature_contract(self, processed_frame: pd.DataFrame) -> tuple[list[str], list[str]]:
        try:
            feature_list, cat_columns = load_artifacts()
            return list(feature_list), list(cat_columns)
        except Exception:
            feature_list = list(processed_frame.columns)
            cat_columns = [
                col for col in processed_frame.columns if str(processed_frame[col].dtype) in {"object", "category"}
            ]
            return feature_list, cat_columns

    def _save_artifacts(
        self,
        model: CatBoostClassifier,
        feature_list: list[str],
        cat_columns: list[str],
        version: str,
    ) -> dict[str, Path]:
        version_dir = self._config.retrained_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)

        model_path = version_dir / "catboost_churn.cbm"
        feature_list_path = version_dir / "feature_list.json"
        cat_columns_path = version_dir / "cat_columns.json"

        model.save_model(str(model_path))
        feature_list_path.write_text(json.dumps(feature_list, indent=2), encoding="utf-8")
        cat_columns_path.write_text(json.dumps(cat_columns, indent=2), encoding="utf-8")

        return {
            "model_path": model_path,
            "feature_list_path": feature_list_path,
            "cat_columns_path": cat_columns_path,
        }

    @staticmethod
    def _clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
        cleaned = frame.copy()
        if "TotalCharges" in cleaned.columns:
            cleaned["TotalCharges"] = pd.to_numeric(cleaned["TotalCharges"], errors="coerce").fillna(0.0)
        return cleaned

    @staticmethod
    def _default_version() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"auto_{stamp}"
