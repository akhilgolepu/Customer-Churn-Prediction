from pydantic import BaseModel, Field
from typing import Literal


JobType = Literal["batch_scoring", "retraining", "drift_report", "quality_check", "report_generation"]
JobStatus = Literal["queued", "running", "completed", "failed"]


class JobRecord(BaseModel):
    id: str
    job_type: JobType
    status: JobStatus
    created_at: float
    updated_at: float
    attempts: int = 0
    error: str | None = None
    idempotency_key: str | None = None
    result: dict | None = None


class BatchJobResponse(BaseModel):
    job: JobRecord


class JobsListResponse(BaseModel):
    items: list[JobRecord]
    page: int
    page_size: int
    total: int


class RetrainRequest(BaseModel):
    reason: str = Field(default="manual")


class ReportRequest(BaseModel):
    report_type: Literal["drift", "quality"] = "drift"
