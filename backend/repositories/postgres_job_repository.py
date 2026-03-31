from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Select, desc, func, select

from db.models import JobRun
from db.session import PostgresSessionFactory
from repositories.job_repository import JobItem


class PostgresJobRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

    @staticmethod
    def _to_job_item(row: JobRun) -> JobItem:
        return JobItem(
            id=str(row.id),
            job_type=row.job_type,
            status=row.status,
            created_at=row.created_at.timestamp(),
            updated_at=row.updated_at.timestamp(),
            attempts=row.attempts,
            error=row.error,
            idempotency_key=row.idempotency_key,
            payload=row.payload,
            result=row.result,
        )

    def create(self, job: JobItem) -> JobItem:
        with self._session_factory.session_scope() as session:
            row = JobRun(
                id=uuid.UUID(job.id),
                org_id=self._org_id,
                job_type=job.job_type,
                status=job.status,
                attempts=job.attempts,
                error=job.error,
                idempotency_key=job.idempotency_key,
                payload=job.payload,
                result=job.result,
                created_at=datetime.fromtimestamp(job.created_at, tz=timezone.utc),
                updated_at=datetime.fromtimestamp(job.updated_at, tz=timezone.utc),
            )
            session.add(row)
        return job

    def get_by_idempotency_key(self, key: str) -> JobItem | None:
        statement: Select[tuple[JobRun]] = (
            select(JobRun)
            .where(JobRun.org_id == self._org_id)
            .where(JobRun.idempotency_key == key)
            .where(JobRun.deleted_at.is_(None))
            .limit(1)
        )
        with self._session_factory.session_scope() as session:
            row = session.execute(statement).scalars().first()
        return self._to_job_item(row) if row else None

    def get(self, job_id: str) -> JobItem | None:
        statement: Select[tuple[JobRun]] = (
            select(JobRun)
            .where(JobRun.org_id == self._org_id)
            .where(JobRun.id == uuid.UUID(job_id))
            .where(JobRun.deleted_at.is_(None))
            .limit(1)
        )
        with self._session_factory.session_scope() as session:
            row = session.execute(statement).scalars().first()
        return self._to_job_item(row) if row else None

    def update(self, job: JobItem) -> None:
        with self._session_factory.session_scope() as session:
            row = session.execute(
                select(JobRun)
                .where(JobRun.org_id == self._org_id)
                .where(JobRun.id == uuid.UUID(job.id))
                .where(JobRun.deleted_at.is_(None))
                .limit(1)
            ).scalars().first()

            if row is None:
                return

            row.status = job.status
            row.updated_at = datetime.fromtimestamp(job.updated_at, tz=timezone.utc)
            row.attempts = job.attempts
            row.error = job.error
            row.payload = job.payload
            row.result = job.result

    def list_paginated(
        self,
        page: int,
        page_size: int,
        job_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[JobItem], int]:
        base_statement: Select[tuple[JobRun]] = (
            select(JobRun)
            .where(JobRun.org_id == self._org_id)
            .where(JobRun.deleted_at.is_(None))
        )

        if job_type:
            base_statement = base_statement.where(JobRun.job_type == job_type)
        if status:
            base_statement = base_statement.where(JobRun.status == status)

        count_statement = select(func.count()).select_from(base_statement.subquery())
        data_statement = (
            base_statement
            .order_by(desc(JobRun.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        with self._session_factory.session_scope() as session:
            total = int(session.execute(count_statement).scalar_one())
            rows = session.execute(data_statement).scalars().all()

        return ([self._to_job_item(row) for row in rows], total)
