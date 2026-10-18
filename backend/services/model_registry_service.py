"""
Model Registry Service - Enhanced with validation gates.

Manages model promotion workflow: candidate → shadow → active.
Every promotion runs the PromotionGate (ModelValidationGate on labelled data)
first; blockers refuse the promotion unless an audit-logged override is given.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from core.exceptions import AppError, NotFoundError, PromotionBlockedError
    from model_loader import switch_active_model, switch_shadow_model
    from repositories.model_registry_repository import ModelRegistryRepository
    HAS_LEGACY_DEPS = True
except ImportError:
    HAS_LEGACY_DEPS = False

from backend.services.model_validation_service import ModelValidationGate

logger = logging.getLogger(__name__)

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "validation_reports"


class ModelRegistryService:
    """Enhanced registry service with validation gates."""

    def __init__(
        self,
        repo: Optional['ModelRegistryRepository'] = None,
        audit_service=None,
        validation_reports_dir: Optional[Path] = None,
        promotion_gate=None,
    ) -> None:
        """promotion_gate: object with evaluate(version, candidate_artifact, active_artifact) -> dict
        (services.promotion_gate.PromotionGate). Without one, promote_candidate refuses to run."""
        self._repo = repo
        self._audit_service = audit_service
        self._promotion_gate = promotion_gate
        self.validation_reports_dir = validation_reports_dir or _DEFAULT_REPORTS_DIR
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

    def promote_candidate(
        self,
        candidate_model_id: str,
        *,
        override_gate: bool = False,
        override_reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> dict:
        """Promote candidate to active after the validation gate passes.

        Blockers raise PromotionBlockedError (HTTP 409). override_gate=True with a
        reason promotes anyway and writes a model_promotion_gate_overridden audit event.
        """
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}
        if self._promotion_gate is None:
            raise AppError("gate_not_configured", "Promotion gate is not configured", status_code=500)

        candidate = self._repo.get(candidate_model_id)
        if candidate is None:
            raise NotFoundError("Candidate model not found")
        if override_gate and not (override_reason and override_reason.strip()):
            raise AppError("override_reason_required", "override_gate requires a non-empty override_reason", 422)

        current_active_id, _ = self._repo.state()
        current_active = self._repo.get(current_active_id) if current_active_id else None
        gate = self._promotion_gate.evaluate(
            candidate.version,
            candidate.artifact_path,
            current_active.artifact_path if current_active else None,
        )
        gate["report_path"] = self._save_gate_report(candidate.version, gate)
        gate_summary = {
            "promotion_allowed": gate["promotion_allowed"],
            "blockers": gate["blockers"],
            "warnings": gate.get("warnings", []),
            "candidate": gate.get("candidate"),
            "active": gate.get("active"),
            "eval_rows": gate.get("eval_rows"),
            "report_path": gate["report_path"],
            "overridden": False,
        }

        if not gate["promotion_allowed"]:
            if not override_gate:
                self._audit(
                    "model_promotion_blocked",
                    candidate_model_id,
                    {"version": candidate.version, "blockers": gate["blockers"], "actor": actor},
                )
                raise PromotionBlockedError(gate_summary)
            gate_summary["overridden"] = True
            self._audit(
                "model_promotion_gate_overridden",
                candidate_model_id,
                {
                    "version": candidate.version,
                    "blockers": gate["blockers"],
                    "override_reason": override_reason,
                    "actor": actor,
                },
            )

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
                metadata={
                    "active_model_id": active_model_id,
                    "shadow_model_id": shadow_model_id,
                    "gate_overridden": gate_summary["overridden"],
                    "actor": actor,
                },
            )
        return {
            "message": "Candidate promoted to active model",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
            "validation": gate_summary,
        }

    def _audit(self, action: str, entity_id: str, metadata: dict) -> None:
        if self._audit_service is not None:
            self._audit_service.log(action=action, entity_type="model_version", entity_id=entity_id, metadata=metadata)

    def _save_gate_report(self, version: str, gate: dict) -> str:
        self.validation_reports_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
        path = self.validation_reports_dir / f"promotion_gate_{version}_{stamp}.json"
        path.write_text(json.dumps(gate, indent=2, default=str), encoding="utf-8")
        return str(path)

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

    def sync_runtime(self) -> None:
        """Load the registry's active and shadow artifacts into the runtime.

        The registry persists (SQLite file / Postgres) but the runtime always
        starts from the default artifact, so without this a restart after a
        promotion served the old model while the registry reported the new one.
        An active artifact that cannot be loaded aborts startup; an unloadable
        shadow is rejected (audited) so registry and runtime agree.
        """
        if not self._has_legacy:
            return
        active_id, shadow_id = self._repo.state()
        active = self._repo.get(active_id) if active_id else None
        if active is not None:
            try:
                switch_active_model(active.artifact_path)
            except Exception as exc:
                raise RuntimeError(
                    f"Registry active model {active.version} ({active.artifact_path}) could not be loaded: {exc}"
                ) from exc
        if shadow_id:
            shadow = self._repo.get(shadow_id)
            try:
                switch_shadow_model(shadow.artifact_path if shadow else None)
            except Exception as exc:
                logger.error("Shadow model could not be loaded at startup: %s", exc)
                self.abort_canary(f"shadow artifact could not be loaded at startup: {exc}")

    def ensure_challenger(self, artifact_path: str, version: str, metrics: Optional[dict] = None) -> Optional[str]:
        """Put the standing challenger in the shadow slot when nothing else is being tested.

        Returns the challenger's model id when it is (now) in shadow, else None.
        A challenger that the canary rejected earlier is not re-attached.
        """
        if not self._has_legacy:
            return None
        active_id, shadow_id = self._repo.state()
        versions = [v for v in self._repo.list_versions() if v.artifact_path == artifact_path]
        if shadow_id:
            return shadow_id if any(v.id == shadow_id for v in versions) else None
        if any(v.id == active_id for v in versions):
            return None  # the challenger was promoted; nothing to shadow
        if any(v.status == "rejected" for v in versions):
            logger.warning("Challenger %s was rejected earlier; not re-attaching it", artifact_path)
            return None
        existing = next((v for v in versions if v.status == "candidate"), None)
        challenger_id = existing.id if existing else self.register_candidate(
            version=version, metrics=metrics or {}, artifact_path=artifact_path
        )["id"]
        self.start_shadow_test(challenger_id)
        self._audit("challenger_attached", challenger_id, {"version": version, "artifact_path": artifact_path})
        return challenger_id

    def abort_canary(self, reason: str) -> dict:
        """Stop a failing shadow/canary candidate without touching the active model.

        Used by the automatic canary rollback. (rollback() demotes the *active*
        model, which is the wrong action when the active model is the healthy
        one and the shadow candidate is the one disagreeing.)
        """
        if not self._has_legacy:
            return {"error": "Legacy repository not configured"}

        rejected_id = self._repo.reject_shadow()
        switch_shadow_model(None)
        active_model_id, shadow_model_id = self._repo.state()
        if self._audit_service is not None:
            self._audit_service.log(
                action="canary_rolled_back",
                entity_type="model_version",
                entity_id=rejected_id or "",
                metadata={"reason": reason, "active_model_id": active_model_id},
            )
        return {
            "message": "Canary rolled back; shadow candidate rejected",
            "rejected_model_id": rejected_id,
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
