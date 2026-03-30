from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import PlainTextResponse

from core.dependencies import get_job_service, require_roles
from core.exceptions import NotFoundError
from schemas.jobs import BatchJobResponse, JobRecord, JobsListResponse, ReportRequest, RetrainRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])


def to_job_record(job) -> JobRecord:
    payload = asdict(job)
    return JobRecord(
        id=payload["id"],
        job_type=payload["job_type"],
        status=payload["status"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        attempts=payload["attempts"],
        error=payload["error"],
        idempotency_key=payload["idempotency_key"],
        result=payload["result"],
    )


@router.post("/batch-score", response_model=BatchJobResponse)
async def batch_score(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    job_service=Depends(get_job_service),
    _=Depends(require_roles("admin", "analyst")),
):
    content = await file.read()
    job = await job_service.enqueue_batch_scoring(content, idempotency_key=idempotency_key)
    return {"job": to_job_record(job)}


@router.post("/retrain", response_model=BatchJobResponse)
async def retrain(
    payload: RetrainRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    job_service=Depends(get_job_service),
    _=Depends(require_roles("admin")),
):
    job = await job_service.enqueue_simple_job(
        "retraining", payload={"reason": payload.reason}, idempotency_key=idempotency_key
    )
    return {"job": to_job_record(job)}


@router.post("/reports", response_model=BatchJobResponse)
async def reports(
    payload: ReportRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    job_service=Depends(get_job_service),
    _=Depends(require_roles("admin", "analyst")),
):
    job = await job_service.enqueue_simple_job(
        "report_generation",
        payload={"report_type": payload.report_type},
        idempotency_key=idempotency_key,
    )
    return {"job": to_job_record(job)}


@router.get("", response_model=JobsListResponse)
def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    job_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    job_service=Depends(get_job_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    items, total = job_service.list_jobs(page=page, page_size=page_size, job_type=job_type, status=status)
    return {
        "items": [to_job_record(item) for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/{job_id}", response_model=BatchJobResponse)
def get_job(job_id: str, job_service=Depends(get_job_service), _=Depends(require_roles("admin", "analyst", "viewer"))):
    job = job_service.get_job(job_id)
    if not job:
        raise NotFoundError("Job not found")
    return {"job": to_job_record(job)}


@router.get("/{job_id}/download", response_class=PlainTextResponse)
def download_job_report(
    job_id: str,
    job_service=Depends(get_job_service),
    _=Depends(require_roles("admin", "analyst", "viewer")),
):
    job = job_service.get_job(job_id)
    if not job:
        raise NotFoundError("Job not found")
    if job.job_type != "batch_scoring":
        raise NotFoundError("Download is only available for batch scoring jobs")
    if job.status != "completed" or not job.result:
        raise NotFoundError("Batch report is not ready")

    return str(job.result.get("report_csv", ""))
