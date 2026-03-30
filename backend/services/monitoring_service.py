import math

from core.settings import get_settings
from repositories.feedback_repository import FeedbackRepository
from repositories.monitoring_repository import MonitoringRepository
from repositories.prediction_repository import PredictionRepository


class MonitoringService:
    def __init__(
        self,
        prediction_repo: PredictionRepository,
        feedback_repo: FeedbackRepository,
        monitoring_repo: MonitoringRepository,
    ) -> None:
        self._prediction_repo = prediction_repo
        self._feedback_repo = feedback_repo
        self._monitoring_repo = monitoring_repo

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _delta_ratio(baseline: float, recent: float) -> float:
        if baseline == 0:
            return 0.0 if recent == 0 else 1.0
        return (recent - baseline) / abs(baseline)

    def snapshot(self) -> dict:
        settings = get_settings()
        predictions, _ = self._prediction_repo.list_paginated(page=1, page_size=5000, is_churn=None)
        if len(predictions) < 10:
            payload = {
                "input_drift": [],
                "prediction_drift": {
                    "metric": "prediction_mean",
                    "baseline": 0.0,
                    "recent": 0.0,
                    "delta": 0.0,
                    "threshold": settings.prediction_drift_alert_threshold,
                    "alert": False,
                },
                "performance": {
                    "samples": 0,
                    "accuracy": 0.0,
                    "precision": 0.0,
                    "recall": 0.0,
                },
                "alerts": [],
            }
            self._monitoring_repo.save_snapshot(payload)
            return payload

        split = max(5, len(predictions) // 2)
        baseline = predictions[:split]
        recent = predictions[-split:]

        numeric_fields = ["MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "TotalServices"]
        input_drift = []
        alerts: list[str] = []

        for field in numeric_fields:
            base_values = [float(item.inputs.get(field, 0.0)) for item in baseline if field in item.inputs]
            recent_values = [float(item.inputs.get(field, 0.0)) for item in recent if field in item.inputs]
            base_mean = self._mean(base_values)
            recent_mean = self._mean(recent_values)
            delta = self._delta_ratio(base_mean, recent_mean)
            alert = abs(delta) >= settings.input_drift_alert_threshold
            if alert:
                alerts.append(f"Input drift alert on {field}: delta={delta:.3f}")
            input_drift.append(
                {
                    "metric": field,
                    "baseline": base_mean,
                    "recent": recent_mean,
                    "delta": delta,
                    "threshold": settings.input_drift_alert_threshold,
                    "alert": alert,
                }
            )

        base_pred = self._mean([item.probability for item in baseline])
        recent_pred = self._mean([item.probability for item in recent])
        pred_delta = self._delta_ratio(base_pred, recent_pred)
        pred_alert = abs(pred_delta) >= settings.prediction_drift_alert_threshold
        if pred_alert:
            alerts.append(f"Prediction drift alert: delta={pred_delta:.3f}")

        outcome_map = {item.prediction_id: item.actual_churn for item in self._feedback_repo.list_outcomes()}
        paired = [(item, outcome_map[item.id]) for item in predictions if item.id in outcome_map]

        tp = fp = tn = fn = 0
        for prediction, actual in paired:
            predicted = prediction.is_churn
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
            elif (not predicted) and (not actual):
                tn += 1
            else:
                fn += 1

        samples = len(paired)
        accuracy = (tp + tn) / samples if samples else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0

        if samples >= settings.min_outcomes_for_performance_tracking and recall < settings.minimum_recall_threshold:
            alerts.append(f"Performance alert: recall dropped to {recall:.3f}")

        # Avoid NaN/Inf serialization in extreme edge-cases.
        if math.isnan(accuracy) or math.isinf(accuracy):
            accuracy = 0.0

        payload = {
            "input_drift": input_drift,
            "prediction_drift": {
                "metric": "prediction_mean",
                "baseline": base_pred,
                "recent": recent_pred,
                "delta": pred_delta,
                "threshold": settings.prediction_drift_alert_threshold,
                "alert": pred_alert,
            },
            "performance": {
                "samples": samples,
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
            },
            "alerts": alerts,
        }
        self._monitoring_repo.save_snapshot(payload)
        return payload
