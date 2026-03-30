from dataclasses import dataclass
import json
import time
import uuid

from repositories.sqlite_store import SQLiteStore


@dataclass
class ModelVersionItem:
    id: str
    version: str
    metrics: dict[str, float]
    artifact_path: str
    status: str
    created_at: float


class ModelRegistryRepository:
    def _read_state_from_connection(self, conn) -> tuple[str, str | None]:
        active_row = conn.execute(
            "SELECT state_value FROM model_registry_state WHERE state_key = ?",
            ("active_model_id",),
        ).fetchone()
        shadow_row = conn.execute(
            "SELECT state_value FROM model_registry_state WHERE state_key = ?",
            ("shadow_model_id",),
        ).fetchone()
        active = str(active_row["state_value"]) if active_row else ""
        shadow = str(shadow_row["state_value"]) if shadow_row and shadow_row["state_value"] else None
        return active, shadow

    def __init__(self, store: SQLiteStore, default_artifact_path: str) -> None:
        self._store = store
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_versions (
                        id TEXT PRIMARY KEY,
                        version TEXT NOT NULL,
                        metrics_json TEXT NOT NULL,
                        artifact_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS model_registry_state (
                        state_key TEXT PRIMARY KEY,
                        state_value TEXT
                    )
                    """
                )

                total = conn.execute("SELECT COUNT(*) AS c FROM model_versions").fetchone()["c"]
                if int(total) == 0:
                    boot = ModelVersionItem(
                        id=str(uuid.uuid4()),
                        version="v1",
                        metrics={},
                        artifact_path=default_artifact_path,
                        status="active",
                        created_at=time.time(),
                    )
                    conn.execute(
                        """
                        INSERT INTO model_versions (id, version, metrics_json, artifact_path, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (boot.id, boot.version, json.dumps(boot.metrics), boot.artifact_path, boot.status, boot.created_at),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                        ("active_model_id", boot.id),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                        ("shadow_model_id", ""),
                    )

    def list_versions(self) -> list[ModelVersionItem]:
        with self._store.lock:
            with self._store.connection() as conn:
                rows = conn.execute(
                    "SELECT id, version, metrics_json, artifact_path, status, created_at FROM model_versions ORDER BY created_at ASC"
                ).fetchall()
        return [
            ModelVersionItem(
                id=str(row["id"]),
                version=str(row["version"]),
                metrics=json.loads(str(row["metrics_json"])),
                artifact_path=str(row["artifact_path"]),
                status=str(row["status"]),
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]

    def get(self, model_id: str) -> ModelVersionItem | None:
        with self._store.lock:
            with self._store.connection() as conn:
                row = conn.execute(
                    "SELECT id, version, metrics_json, artifact_path, status, created_at FROM model_versions WHERE id = ?",
                    (model_id,),
                ).fetchone()
        if row is None:
            return None
        return ModelVersionItem(
            id=str(row["id"]),
            version=str(row["version"]),
            metrics=json.loads(str(row["metrics_json"])),
            artifact_path=str(row["artifact_path"]),
            status=str(row["status"]),
            created_at=float(row["created_at"]),
        )

    def register_candidate(self, version: str, metrics: dict[str, float], artifact_path: str) -> ModelVersionItem:
        item = ModelVersionItem(
            id=str(uuid.uuid4()),
            version=version,
            metrics=metrics,
            artifact_path=artifact_path,
            status="candidate",
            created_at=time.time(),
        )
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO model_versions (id, version, metrics_json, artifact_path, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item.id, item.version, json.dumps(item.metrics), item.artifact_path, item.status, item.created_at),
                )
        return item

    def set_shadow(self, candidate_model_id: str) -> None:
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                    ("shadow_model_id", candidate_model_id),
                )

    def promote(self, candidate_model_id: str) -> None:
        with self._store.lock:
            with self._store.connection() as conn:
                active_model_id, shadow_model_id = self._read_state_from_connection(conn)
                conn.execute("UPDATE model_versions SET status = 'archived' WHERE id = ?", (active_model_id,))
                conn.execute("UPDATE model_versions SET status = 'active' WHERE id = ?", (candidate_model_id,))
                conn.execute(
                    "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                    ("active_model_id", candidate_model_id),
                )
                if shadow_model_id == candidate_model_id:
                    conn.execute(
                        "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                        ("shadow_model_id", ""),
                    )

    def rollback(self, target_model_id: str | None = None) -> None:
        with self._store.lock:
            with self._store.connection() as conn:
                active_model_id, shadow_model_id = self._read_state_from_connection(conn)
                if target_model_id:
                    next_active = target_model_id
                else:
                    archived_row = conn.execute(
                        """
                        SELECT id FROM model_versions
                        WHERE status = 'archived'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ).fetchone()
                    if archived_row is None:
                        return
                    next_active = str(archived_row["id"])

                conn.execute("UPDATE model_versions SET status = 'archived' WHERE id = ?", (active_model_id,))
                conn.execute("UPDATE model_versions SET status = 'active' WHERE id = ?", (next_active,))
                conn.execute(
                    "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                    ("active_model_id", next_active),
                )
                if shadow_model_id == next_active:
                    conn.execute(
                        "INSERT OR REPLACE INTO model_registry_state (state_key, state_value) VALUES (?, ?)",
                        ("shadow_model_id", ""),
                    )

    def state(self) -> tuple[str, str | None]:
        with self._store.lock:
            with self._store.connection() as conn:
                return self._read_state_from_connection(conn)
