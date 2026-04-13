from __future__ import annotations

import hashlib
import time
from threading import Lock
from typing import Any


class CanaryRolloutService:
    """Controls canary traffic split, A/B tracking, and rollback decisions."""

    def __init__(
        self,
        enabled: bool,
        traffic_percent: int,
        min_samples: int,
        max_disagreement_rate: float,
        rollback_cooldown_seconds: int,
    ) -> None:
        self._enabled = enabled
        self._traffic_percent = max(0, min(100, int(traffic_percent)))
        self._min_samples = max(1, int(min_samples))
        self._max_disagreement_rate = float(max_disagreement_rate)
        self._rollback_cooldown_seconds = int(rollback_cooldown_seconds)

        self._lock = Lock()
        self._total = 0
        self._canary_samples = 0
        self._disagreements = 0
        self._last_rollback_at: float | None = None
        self._last_rollback_reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def choose_variant(self, prediction_id: str) -> str:
        if not self._enabled or self._traffic_percent <= 0:
            return "active"

        bucket = int(hashlib.sha256(prediction_id.encode("utf-8")).hexdigest()[:8], 16) % 100
        return "shadow" if bucket < self._traffic_percent else "active"

    def record_prediction(
        self,
        prediction_id: str,
        active_probability: float,
        shadow_probability: float | None,
        threshold: float,
    ) -> dict[str, Any]:
        with self._lock:
            self._total += 1

            if shadow_probability is None:
                return {
                    "variant": "active",
                    "rollback_triggered": False,
                    "disagreement_rate": 0.0,
                }

            variant = self.choose_variant(prediction_id)
            if variant == "shadow":
                self._canary_samples += 1

            active_label = active_probability >= threshold
            shadow_label = shadow_probability >= threshold
            disagreement = active_label != shadow_label
            if disagreement:
                self._disagreements += 1

            disagreement_rate = self._disagreements / self._canary_samples if self._canary_samples else 0.0
            rollback_triggered = self._should_rollback(disagreement_rate)
            if rollback_triggered:
                self._last_rollback_at = time.time()
                self._last_rollback_reason = (
                    f"Canary disagreement rate {disagreement_rate:.3f} exceeded threshold {self._max_disagreement_rate:.3f}"
                )

            return {
                "variant": variant,
                "rollback_triggered": rollback_triggered,
                "disagreement_rate": disagreement_rate,
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            disagreement_rate = self._disagreements / self._canary_samples if self._canary_samples else 0.0
            return {
                "enabled": self._enabled,
                "traffic_percent": self._traffic_percent,
                "min_samples": self._min_samples,
                "max_disagreement_rate": self._max_disagreement_rate,
                "total_predictions": self._total,
                "canary_samples": self._canary_samples,
                "disagreements": self._disagreements,
                "disagreement_rate": disagreement_rate,
                "last_rollback_at": self._last_rollback_at,
                "last_rollback_reason": self._last_rollback_reason,
            }

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    def _should_rollback(self, disagreement_rate: float) -> bool:
        if not self._enabled:
            return False
        if self._canary_samples < self._min_samples:
            return False
        if disagreement_rate <= self._max_disagreement_rate:
            return False
        if self._last_rollback_at is None:
            return True
        return (time.time() - self._last_rollback_at) >= self._rollback_cooldown_seconds
