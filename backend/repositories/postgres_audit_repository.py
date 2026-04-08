from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from db.models import AuditLog
from db.session import PostgresSessionFactory


class PostgresAuditRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

    def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._session_factory.session_scope() as session:
            session.add(
                AuditLog(
                    org_id=self._org_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=uuid.UUID(entity_id) if entity_id else None,
                    request_id=request_id,
                    metadata_json=metadata or {},
                    event_at=datetime.now(tz=timezone.utc),
                )
            )
