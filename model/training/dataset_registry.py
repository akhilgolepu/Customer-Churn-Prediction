from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = ROOT_DIR / "data" / "dataset_catalog.json"


@dataclass(frozen=True)
class DatasetEntry:
    id: str
    name: str
    path: str
    target_column: str
    positive_label: Any
    task: str
    domain: str
    status: str
    notes: str

    @property
    def absolute_path(self) -> Path:
        return ROOT_DIR / self.path


class DatasetRegistry:
    def __init__(self, catalog_path: Path = DEFAULT_CATALOG_PATH) -> None:
        self.catalog_path = catalog_path
        self._datasets = self._load_catalog()

    def _load_catalog(self) -> list[DatasetEntry]:
        with self.catalog_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        datasets = payload.get("datasets", [])
        return [DatasetEntry(**item) for item in datasets]

    def list(self, include_planned: bool = True) -> list[DatasetEntry]:
        if include_planned:
            return self._datasets
        return [item for item in self._datasets if item.status == "active"]

    def get(self, dataset_id: str) -> DatasetEntry:
        for item in self._datasets:
            if item.id == dataset_id:
                return item
        raise KeyError(f"Dataset '{dataset_id}' is not defined in catalog: {self.catalog_path}")

    def validate(self) -> list[str]:
        issues: list[str] = []
        for dataset in self._datasets:
            if dataset.status == "planned":
                continue
            if not dataset.absolute_path.exists():
                issues.append(
                    f"[{dataset.id}] missing file: {dataset.absolute_path}"
                )
        return issues


class DatasetProfiler:
    def __init__(self, registry: DatasetRegistry) -> None:
        self.registry = registry

    def summarize(self, dataset: DatasetEntry) -> dict[str, Any]:
        if not dataset.absolute_path.exists():
            return {
                "id": dataset.id,
                "name": dataset.name,
                "status": dataset.status,
                "present": False,
                "path": str(dataset.absolute_path),
            }

        df = pd.read_csv(dataset.absolute_path)
        target = dataset.target_column

        if target not in df.columns:
            return {
                "id": dataset.id,
                "name": dataset.name,
                "status": dataset.status,
                "present": True,
                "path": str(dataset.absolute_path),
                "rows": int(df.shape[0]),
                "columns": int(df.shape[1]),
                "target_present": False,
                "issue": f"target column '{target}' not found",
            }

        target_series = df[target]
        churn_rate = float((target_series == dataset.positive_label).mean())

        return {
            "id": dataset.id,
            "name": dataset.name,
            "status": dataset.status,
            "present": True,
            "path": str(dataset.absolute_path),
            "rows": int(df.shape[0]),
            "columns": int(df.shape[1]),
            "target_present": True,
            "target_column": target,
            "positive_label": dataset.positive_label,
            "churn_rate": round(churn_rate, 4),
        }

    def summarize_all(self) -> list[dict[str, Any]]:
        return [self.summarize(dataset) for dataset in self.registry.list(include_planned=True)]
