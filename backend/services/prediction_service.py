import asyncio
import math
import time
import uuid
from dataclasses import dataclass

import numpy as np

from core.exceptions import CircuitOpenError
from core.settings import get_settings
from feature_engineering import engineer_features
from model_loader import explain as explain_model
from model_loader import predict_proba
from model_loader import predict_shadow_proba
from repositories.prediction_repository import PredictionHistoryItem, PredictionRepository
from schemas.prediction import PredictionRequest


@dataclass
class CircuitBreaker:
    failure_threshold: int
    recovery_seconds: int
    failure_count: int = 0
    opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.opened_at is None:
            return True
        return (time.time() - self.opened_at) > self.recovery_seconds

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()


class PredictionService:
    def __init__(self, repo: PredictionRepository, audit_service=None, canary_service=None, model_registry_service=None) -> None:
        self._repo = repo
        self._audit_service = audit_service
        self._canary_service = canary_service
        self._model_registry_service = model_registry_service
        settings = get_settings()
        self._breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_seconds=settings.circuit_breaker_recovery_seconds,
        )

    async def _run_with_resilience(self, fn):
        settings = get_settings()
        if not self._breaker.allow_request():
            raise CircuitOpenError()

        last_exc: Exception | None = None
        for _ in range(settings.dependency_retry_count + 1):
            try:
                result = await asyncio.wait_for(asyncio.to_thread(fn), timeout=settings.dependency_timeout_seconds)
                self._breaker.record_success()
                return result
            except Exception as exc:
                self._breaker.record_failure()
                last_exc = exc
        if last_exc:
            raise last_exc
        raise RuntimeError("Unknown dependency failure")

    async def predict(self, request: PredictionRequest, threshold: float) -> dict:
        df = engineer_features(request)
        active_probability = float(await self._run_with_resilience(lambda: predict_proba(df)))
        shadow_probability = await self._run_with_resilience(lambda: predict_shadow_proba(df))
        prediction_id = str(uuid.uuid4())

        variant = "active"
        rollback_triggered = False
        if self._canary_service is not None:
            canary_eval = self._canary_service.record_prediction(
                prediction_id=prediction_id,
                active_probability=active_probability,
                shadow_probability=shadow_probability,
                threshold=threshold,
            )
            variant = str(canary_eval.get("variant", "active"))
            rollback_triggered = bool(canary_eval.get("rollback_triggered", False))

        probability = active_probability
        if variant == "shadow" and shadow_probability is not None:
            probability = float(shadow_probability)

        if rollback_triggered and self._model_registry_service is not None:
            try:
                self._model_registry_service.rollback()
                if self._canary_service is not None:
                    self._canary_service.disable()
            except Exception:   # nosec B110
                # Rollback attempts should not fail prediction path.
                pass

        is_churn = probability >= threshold

        self._repo.add(
            PredictionHistoryItem(
                id=prediction_id,
                created_at=time.time(),
                probability=probability,
                is_churn=is_churn,
                threshold=threshold,
                inputs=request.model_dump(),
            )
        )

        if self._audit_service is not None:
            self._audit_service.log(
                action="prediction_created",
                entity_type="prediction",
                entity_id=prediction_id,
                metadata={
                    "probability": probability,
                    "active_probability": active_probability,
                    "shadow_probability": shadow_probability,
                    "variant": variant,
                    "threshold": threshold,
                    "is_churn": is_churn,
                },
            )

        result = {"predictionId": prediction_id, "probability": probability, "isChurn": is_churn}
        result["activeProbability"] = active_probability
        if shadow_probability is not None:
            result["shadowProbability"] = float(shadow_probability)
            result["variant"] = variant
        return result

    async def explain(self, request: PredictionRequest) -> dict:
        df = engineer_features(request)
        shap_values = await self._run_with_resilience(lambda: explain_model(df))

        features = df.columns.tolist()
        row = df.iloc[0]

        def to_json_value(value):
            if isinstance(value, np.generic):
                value = value.item()
            elif isinstance(value, np.ndarray):
                value = value.tolist()
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                return None
            return value

        values = [to_json_value(row[feature]) for feature in features]
        shap_list = [float(item) for item in np.array(shap_values).ravel().tolist()]

        drivers = [
            {"feature": feature, "value": value, "impact": impact}
            for feature, value, impact in zip(features, values, shap_list)
        ]
        drivers.sort(key=lambda item: abs(item["impact"]), reverse=True)

        return {"top_drivers": drivers[:5]}

    def history(self, page: int, page_size: int, is_churn: bool | None):
        items, total = self._repo.list_paginated(page=page, page_size=page_size, is_churn=is_churn)
        return {
            "items": [
                {
                    "id": item.id,
                    "created_at": item.created_at,
                    "probability": item.probability,
                    "isChurn": item.is_churn,
                    "threshold": item.threshold,
                }
                for item in items
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        }
