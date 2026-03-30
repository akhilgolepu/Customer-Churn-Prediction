import uuid

from sqlalchemy import Select, desc, select

from db.models import AuditLog
from db.session import PostgresSessionFactory


class PostgresMonitoringRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

    def save_snapshot(self, payload: dict) -> None:
        with self._session_factory.session_scope() as session:
            session.add(
                AuditLog(
                    org_id=self._org_id,
                    action="monitoring_snapshot",
                    entity_type="monitoring",
                    metadata_json=payload,
                )
            )

    def latest_snapshot(self) -> dict | None:
        statement: Select[tuple[AuditLog]] = (
            select(AuditLog)
            .where(AuditLog.org_id == self._org_id)
            .where(AuditLog.action == "monitoring_snapshot")
            .order_by(desc(AuditLog.event_at))
            .limit(1)
        )

        with self._session_factory.session_scope() as session:
            row = session.execute(statement).scalars().first()

        if row is None:
            return None
        return row.metadata_json
