import json
import time

from repositories.sqlite_store import SQLiteStore


class MonitoringRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self._store = store
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS monitoring_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at REAL NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )

    def save_snapshot(self, payload: dict) -> None:
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    "INSERT INTO monitoring_snapshots (created_at, payload_json) VALUES (?, ?)",
                    (time.time(), json.dumps(payload)),
                )

    def latest_snapshot(self) -> dict | None:
        with self._store.lock:
            with self._store.connection() as conn:
                row = conn.execute(
                    "SELECT payload_json FROM monitoring_snapshots ORDER BY id DESC LIMIT 1"
                ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload_json"]))
