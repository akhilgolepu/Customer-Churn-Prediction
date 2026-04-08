from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass
class AuditRecord:
    action: str
    entity_type: str
    entity_id: str | None
    request_id: str | None
    metadata: dict[str, Any]
    event_at: float


class AuditRepository:
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._records.append(
            AuditRecord(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=request_id,
                metadata=metadata or {},
                event_at=time.time(),
            )
        )
