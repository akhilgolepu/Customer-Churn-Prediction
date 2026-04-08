from __future__ import annotations

from typing import Any


class AuditService:
    def __init__(self, repo) -> None:
        self._repo = repo

    def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._repo.log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            metadata=metadata,
        )
