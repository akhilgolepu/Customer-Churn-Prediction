"""Prometheus metrics for the API (served at GET /metrics).

Pushed as events happen:
  churn_http_request_duration_seconds  histogram, labels method/route/status
  churn_predictions_total              counter, labels served_by (active|shadow)/decision
  churn_prediction_score               histogram of the served (calibrated) probability
  churn_canary_rollbacks_total         counter

Read from live state at scrape time (never stale):
  churn_canary_disagreement_rate, churn_canary_compared_requests,
  churn_canary_disagreements, churn_model_info{slot,version,kind,calibration}

With several uvicorn workers each process has its own registry; set
PROMETHEUS_MULTIPROC_DIR to an empty directory to aggregate them
(prometheus_client multiprocess mode).
"""

from __future__ import annotations

import os
import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

MULTIPROC = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))
REGISTRY = CollectorRegistry()

REQUEST_LATENCY = Histogram(
    "churn_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)
PREDICTIONS = Counter(
    "churn_predictions_total",
    "Predictions served, by the model that served them and the decision at the threshold.",
    ["served_by", "decision"],
    registry=REGISTRY,
)
SCORE = Histogram(
    "churn_prediction_score",
    "Served churn probability (calibrated).",
    buckets=tuple(round(0.05 * i, 2) for i in range(1, 21)),
    registry=REGISTRY,
)
CANARY_ROLLBACKS = Counter(
    "churn_canary_rollbacks_total", "Automatic canary rollbacks.", registry=REGISTRY
)
# multiprocess_mode only matters with PROMETHEUS_MULTIPROC_DIR; ignored otherwise.
CANARY_DISAGREEMENT = Gauge(
    "churn_canary_disagreement_rate",
    "Share of compared requests where active and shadow decisions differ.",
    registry=REGISTRY, multiprocess_mode="mostrecent",
)
CANARY_COMPARED = Gauge(
    "churn_canary_compared_requests", "Requests scored by both active and shadow.", registry=REGISTRY, multiprocess_mode="mostrecent"
)
CANARY_DISAGREEMENTS = Gauge(
    "churn_canary_disagreements", "Compared requests whose decisions differ.", registry=REGISTRY, multiprocess_mode="mostrecent"
)
MODEL_INFO = Gauge(
    "churn_model_info",
    "1 for the model in each slot (active / shadow).",
    ["slot", "version", "kind", "calibration"],
    registry=REGISTRY, multiprocess_mode="mostrecent",
)


def observe_request(method: str, route: str, status: int, started: float) -> None:
    REQUEST_LATENCY.labels(method=method, route=route, status=str(status)).observe(time.perf_counter() - started)


def observe_prediction(served_by: str, probability: float, is_churn: bool, rollback: bool) -> None:
    PREDICTIONS.labels(served_by=served_by, decision="churn" if is_churn else "stay").inc()
    SCORE.observe(probability)
    if rollback:
        CANARY_ROLLBACKS.inc()


def refresh_state(canary_service=None, model_registry_service=None, runtime_state: dict | None = None) -> None:
    """Pull canary counters and model identities into gauges just before a scrape."""
    if canary_service is not None:
        snap = canary_service.snapshot()
        CANARY_DISAGREEMENT.set(float(snap.get("disagreement_rate", 0.0)))
        CANARY_COMPARED.set(float(snap.get("compared_samples", 0)))
        CANARY_DISAGREEMENTS.set(float(snap.get("disagreements", 0)))

    MODEL_INFO.clear()
    runtime_state = runtime_state or {}
    versions: dict[str, str] = {}
    if model_registry_service is not None:
        try:
            registry = model_registry_service.list_registry()
            by_id = {v["id"]: v["version"] for v in registry.get("versions", [])}
            versions["active"] = by_id.get(registry.get("active_model_id"), "unknown")
            if registry.get("shadow_model_id"):
                versions["shadow"] = by_id.get(registry["shadow_model_id"], "unknown")
        except Exception:  # metrics must never break a scrape  # nosec B110
            pass
    for slot in ("active", "shadow"):
        kind = runtime_state.get(f"{slot}_model_kind")
        if kind:
            MODEL_INFO.labels(
                slot=slot,
                version=versions.get(slot, "unknown"),
                kind=kind,
                calibration=str(runtime_state.get(f"{slot}_calibration")),
            ).set(1)


def render() -> tuple[bytes, str]:
    if MULTIPROC:
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
