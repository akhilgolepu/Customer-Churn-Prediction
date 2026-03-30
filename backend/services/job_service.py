import asyncio
import csv
import io
import time
import uuid
from typing import Any

import pandas as pd

from core.settings import get_settings
from repositories.job_repository import JobItem, JobRepository
from schemas.prediction import PredictionRequest
from storage.adapters import ObjectStorage, random_object_key
from services.prediction_service import PredictionService


class JobService:
    def __init__(
        self,
        repo: JobRepository,
        prediction_service: PredictionService,
        object_storage: ObjectStorage | None = None,
    ) -> None:
        self._repo = repo
        self._prediction_service = prediction_service
        self._object_storage = object_storage
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue_batch_scoring(self, csv_bytes: bytes, idempotency_key: str | None = None) -> JobItem:
        settings = get_settings()
        if idempotency_key:
            existing = self._repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        payload: dict[str, Any]
        if self._object_storage is not None:
            key = random_object_key(settings.batch_upload_prefix, ".csv")
            uri = self._object_storage.upload_bytes(key=key, payload=csv_bytes, content_type="text/csv")
            payload = {"csv_uri": uri}
        else:
            payload = {"csv": csv_bytes.decode("utf-8")}

        job = JobItem(
            id=str(uuid.uuid4()),
            job_type="batch_scoring",
            status="queued",
            created_at=time.time(),
            updated_at=time.time(),
            idempotency_key=idempotency_key,
            payload=payload,
        )
        self._repo.create(job)
        await self._queue.put(job.id)
        return job

    async def enqueue_simple_job(self, job_type: str, payload: dict | None = None, idempotency_key: str | None = None) -> JobItem:
        if idempotency_key:
            existing = self._repo.get_by_idempotency_key(idempotency_key)
            if existing:
                return existing

        job = JobItem(
            id=str(uuid.uuid4()),
            job_type=job_type,
            status="queued",
            created_at=time.time(),
            updated_at=time.time(),
            idempotency_key=idempotency_key,
            payload=payload or {},
        )
        self._repo.create(job)
        await self._queue.put(job.id)
        return job

    def get_job(self, job_id: str) -> JobItem | None:
        return self._repo.get(job_id)

    def list_jobs(self, page: int, page_size: int, job_type: str | None = None, status: str | None = None):
        return self._repo.list_paginated(page=page, page_size=page_size, job_type=job_type, status=status)

    @staticmethod
    def _risk_tier(probability: float) -> str:
        if probability < 0.33:
            return "low"
        if probability < 0.66:
            return "medium"
        return "high"

    async def worker_loop(self) -> None:
        settings = get_settings()
        while True:
            job_id = await self._queue.get()
            job = self._repo.get(job_id)
            if not job:
                self._queue.task_done()
                continue

            job.status = "running"
            job.updated_at = time.time()
            self._repo.update(job)

            success = False
            for attempt in range(1, settings.batch_worker_retry_count + 1):
                try:
                    job.attempts = attempt
                    if job.job_type == "batch_scoring":
                        result = await self._run_batch_scoring(job)
                    elif job.job_type == "retraining":
                        await asyncio.sleep(1.2)
                        result = {"status": "retraining_triggered", "reason": job.payload.get("reason", "manual")}
                    elif job.job_type in {"drift_report", "quality_check", "report_generation"}:
                        await asyncio.sleep(0.8)
                        result = {"status": "generated", "job_type": job.job_type}
                    else:
                        await asyncio.sleep(0.3)
                        result = {"status": "ok"}

                    job.result = result
                    job.status = "completed"
                    job.error = None
                    job.updated_at = time.time()
                    self._repo.update(job)
                    success = True
                    break
                except Exception as exc:
                    job.error = str(exc)
                    job.updated_at = time.time()
                    self._repo.update(job)

            if not success:
                job.status = "failed"
                job.updated_at = time.time()
                self._repo.update(job)

            self._queue.task_done()

    async def _run_batch_scoring(self, job: JobItem) -> dict:
        settings = get_settings()
        if self._object_storage is not None and job.payload.get("csv_uri"):
            csv_text = self._object_storage.download_bytes(str(job.payload["csv_uri"])).decode("utf-8")
        else:
            csv_text = job.payload.get("csv", "")
        frame = pd.read_csv(io.StringIO(csv_text))

        required_columns = set(PredictionRequest.model_fields.keys())
        incoming_columns = set(str(column) for column in frame.columns)
        missing_columns = sorted(required_columns - incoming_columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        results = []
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        for _, row in frame.iterrows():
            row_payload: dict[str, Any] = {str(key): value for key, value in row.to_dict().items()}
            payload = PredictionRequest(**row_payload)
            prediction = await self._prediction_service.predict(payload, threshold=0.5)
            tier = self._risk_tier(float(prediction["probability"]))
            prediction["riskTier"] = tier
            risk_counts[tier] += 1
            results.append(prediction)

        avg_probability = sum(item["probability"] for item in results) / len(results) if results else 0.0
        churn_count = sum(1 for item in results if item["isChurn"])

        report_buffer = io.StringIO()
        writer = csv.DictWriter(
            report_buffer,
            fieldnames=["row_index", "prediction_id", "probability", "is_churn", "risk_tier"],
        )
        writer.writeheader()
        for index, item in enumerate(results):
            writer.writerow(
                {
                    "row_index": index,
                    "prediction_id": item["predictionId"],
                    "probability": round(float(item["probability"]), 6),
                    "is_churn": bool(item["isChurn"]),
                    "risk_tier": item["riskTier"],
                }
            )

        report_csv = report_buffer.getvalue()
        result = {
            "rows": len(results),
            "avg_probability": avg_probability,
            "churn_count": churn_count,
            "risk_tiers": risk_counts,
            "report_csv": report_csv,
            "predictions": results[:100],
        }

        if self._object_storage is not None:
            report_key = random_object_key(settings.batch_report_prefix, ".csv")
            result["report_uri"] = self._object_storage.upload_bytes(
                key=report_key,
                payload=report_csv.encode("utf-8"),
                content_type="text/csv",
            )

        return result


class SchedulerService:
    def __init__(self, job_service: JobService) -> None:
        self._job_service = job_service

    async def quality_check_loop(self) -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(settings.schedule_quality_check_seconds)
            await self._job_service.enqueue_simple_job("quality_check", payload={"source": "scheduler"})

    async def drift_report_loop(self) -> None:
        settings = get_settings()
        while True:
            await asyncio.sleep(settings.schedule_drift_report_seconds)
            await self._job_service.enqueue_simple_job("drift_report", payload={"source": "scheduler"})
