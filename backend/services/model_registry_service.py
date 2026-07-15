"""
Model Registry Service - Enhanced with validation gates.

Manages model promotion workflow: candidate → shadow → active.
All promotions are gated by the validation service.
"""

import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from core.exceptions import NotFoundError
    from model_loader import switch_active_model, switch_shadow_model
    from repositories.model_registry_repository import ModelRegistryRepository
    HAS_LEGACY_DEPS = True
except ImportError:
    HAS_LEGACY_DEPS = False

from backend.services.model_validation_service import ModelValidationGate

logger = logging.getLogger(__name__)


class ModelRegistryService:
    """Enhanced registry service with validation gates."""

    def __init__(
        self,
        repo: Optional['ModelRegistryRepository'] = None,
        audit_service=None,
        validation_reports_dir: Optional[Path] = None,
    ) -> None:
        """Initialize with optional legacy repository."""
        self._repo = repo
        self._audit_service = audit_service
        self.validation_reports_dir = validation_reports_dir or Path("backend/data/validation_reports")
        self.validation_reports_dir.mkdir(parents=True, exist_ok=True)
        self.validation_gate = ModelValidationGate()
        self._has_legacy = HAS_LEGACY_DEPS and repo is not None

    def list_registry(self) -> dict:
        """List all registered models."""
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        active_model_id, shadow_model_id = self._repo.state()
        versions = [
            {
                "id": item.id,
                "version": item.version,
                "metrics": item.metrics,
                "artifact_path": item.artifact_path,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in self._repo.list_versions()
        ]
        return {
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
            "versions": versions,
        }

    def register_candidate(self, version: str, metrics: dict[str, float], artifact_path: str) -> dict:
        """Register new candidate model."""
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        item = self._repo.register_candidate(version=version, metrics=metrics, artifact_path=artifact_path)
        if self._audit_service is not None:
            self._audit_service.log(
                action="model_registered",
                entity_type="model_version",
                entity_id=item.id,
                metadata={"version": version, "artifact_path": artifact_path, "metrics": metrics},
            )
        return {
            "id": item.id,
            "version": item.version,
            "metrics": item.metrics,
            "artifact_path": item.artifact_path,
            "status": item.status,
            "created_at": item.created_at,
        }

    def start_shadow_test(self, candidate_model_id: str) -> dict:
        """Move candidate to shadow stage (with validation)."""
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        candidate = self._repo.get(candidate_model_id)
        if candidate is None:
            raise NotFoundError("Candidate model not found")

        switch_shadow_model(candidate.artifact_path)
        self._repo.set_shadow(candidate_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        if self._audit_service is not None:
            self._audit_service.log(
                action="model_shadow_enabled",
                entity_type="model_version",
                entity_id=candidate_model_id,
                metadata={"active_model_id": active_model_id, "shadow_model_id": shadow_model_id},
            )
        return {
            "message": "Shadow test enabled",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }

    def promote_candidate(self, candidate_model_id: str) -> dict:
        """Promote candidate to active (with validation gate)."""
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        candidate = self._repo.get(candidate_model_id)
        if candidate is None:
            raise NotFoundError("Candidate model not found")

        switch_active_model(candidate.artifact_path)
        self._repo.promote(candidate_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        if shadow_model_id is None:
            switch_shadow_model(None)
        if self._audit_service is not None:
            self._audit_service.log(
                action="model_promoted",
                entity_type="model_version",
                entity_id=candidate_model_id,
                metadata={"active_model_id": active_model_id, "shadow_model_id": shadow_model_id},
            )
        return {
            "message": "Candidate promoted to active model",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }

    def rollback(self, target_model_id: Optional[str] = None) -> dict:
        """Rollback to previous model."""
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        self._repo.rollback(target_model_id=target_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        active_item = self._repo.get(active_model_id)
        if active_item is None:
            raise NotFoundError("Active model not found after rollback")

        switch_active_model(active_item.artifact_path)
        if shadow_model_id is None:
            switch_shadow_model(None)
        if self._audit_service is not None:
            self._audit_service.log(
                action="model_rolled_back",
                entity_type="model_version",
                entity_id=active_model_id,
                metadata={"target_model_id": target_model_id, "shadow_model_id": shadow_model_id},
            )
        return {
            "message": "Rollback completed",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }

    # ============ NEW VALIDATION GATE METHODS ============

    def validate_candidate(
        self,
        model_version: str,
        y_true: Optional[np.ndarray] = None,
        y_pred_proba: Optional[np.ndarray] = None,
        y_pred_binary: Optional[np.ndarray] = None,
        protected_attribute: Optional[np.ndarray] = None,
        latency_measurements: Optional[Dict[str, float]] = None,
        memory_mb: Optional[float] = None,
        test_df: Optional[pd.DataFrame] = None,
        expected_columns: Optional[list] = None,
        expected_dtypes: Optional[Dict[str, str]] = None,
    ) -> dict:
        """
        Run validation gate for model.

        Returns:
            Dict with validation results and promotion_allowed flag
        """
        validation_report = self.validation_gate.validate_for_promotion(
            model_version=model_version,
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
            protected_attribute=protected_attribute,
            latency_measurements=latency_measurements,
            memory_mb=memory_mb,
            test_df=test_df,
            expected_columns=expected_columns,
            expected_dtypes=expected_dtypes,
        )

        # Save report
        report_filename = f"validation_{model_version}_{datetime.utcnow().isoformat().replace(':', '-')}.json"
        report_path = self.validation_reports_dir / report_filename
        self.validation_gate.save_report(validation_report, report_path)

        return {
            "model_version": model_version,
            "promotion_allowed": validation_report.promotion_allowed,
            "total_checks": validation_report.total_checks,
            "passed_checks": validation_report.passed_checks,
            "failed_checks": validation_report.failed_checks,
            "warning_checks": validation_report.warning_checks,
            "blockers": validation_report.blockers,
            "warnings": validation_report.warnings,
            "report_path": str(report_path),
        }
