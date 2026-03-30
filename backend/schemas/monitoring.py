from pydantic import BaseModel


class DriftMetric(BaseModel):
    metric: str
    baseline: float
    recent: float
    delta: float
    threshold: float
    alert: bool


class PerformanceSummary(BaseModel):
    samples: int
    accuracy: float
    precision: float
    recall: float


class MonitoringResponse(BaseModel):
    input_drift: list[DriftMetric]
    prediction_drift: DriftMetric
    performance: PerformanceSummary
    alerts: list[str]
