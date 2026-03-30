from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class JobItem:
    id: str
    job_type: str
    status: str
    created_at: float
    updated_at: float
    attempts: int = 0
    error: str | None = None
    idempotency_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None


class JobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, JobItem] = {}
        self._idempotency_map: dict[str, str] = {}
        self._lock = Lock()

    def create(self, job: JobItem) -> JobItem:
        with self._lock:
            self._jobs[job.id] = job
            if job.idempotency_key:
                self._idempotency_map[job.idempotency_key] = job.id
            return job

    def get_by_idempotency_key(self, key: str) -> JobItem | None:
        with self._lock:
            job_id = self._idempotency_map.get(key)
            return self._jobs.get(job_id) if job_id else None

    def get(self, job_id: str) -> JobItem | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: JobItem) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def list_paginated(self, page: int, page_size: int, job_type: str | None = None, status: str | None = None) -> tuple[list[JobItem], int]:
        with self._lock:
            items = list(self._jobs.values())
            if job_type:
                items = [item for item in items if item.job_type == job_type]
            if status:
                items = [item for item in items if item.status == status]
            items.sort(key=lambda item: item.created_at, reverse=True)
            total = len(items)
            start = (page - 1) * page_size
            end = start + page_size
            return items[start:end], total
