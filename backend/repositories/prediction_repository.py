from dataclasses import dataclass, field
from threading import Lock
from typing import Any, List


@dataclass
class PredictionHistoryItem:
    id: str
    created_at: float
    probability: float
    is_churn: bool
    threshold: float
    inputs: dict[str, Any] = field(default_factory=dict)


class PredictionRepository:
    def __init__(self) -> None:
        self._items: List[PredictionHistoryItem] = []
        self._lock = Lock()

    def add(self, item: PredictionHistoryItem) -> None:
        with self._lock:
            self._items.append(item)

    def list_paginated(self, page: int, page_size: int, is_churn: bool | None = None) -> tuple[list[PredictionHistoryItem], int]:
        with self._lock:
            data = self._items
            if is_churn is not None:
                data = [item for item in data if item.is_churn == is_churn]
            total = len(data)
            start = (page - 1) * page_size
            end = start + page_size
            return data[start:end], total
