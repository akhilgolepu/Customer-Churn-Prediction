from dataclasses import dataclass
import time

from repositories.sqlite_store import SQLiteStore


@dataclass
class FeedbackItem:
    prediction_id: str
    useful: bool
    comment: str | None
    created_at: float


@dataclass
class OutcomeItem:
    prediction_id: str
    actual_churn: bool
    notes: str | None
    created_at: float


class FeedbackRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self._store = store
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        prediction_id TEXT NOT NULL,
                        useful INTEGER NOT NULL,
                        comment TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS outcomes (
                        prediction_id TEXT PRIMARY KEY,
                        actual_churn INTEGER NOT NULL,
                        notes TEXT,
                        created_at REAL NOT NULL
                    )
                    """
                )

    def add_feedback(self, prediction_id: str, useful: bool, comment: str | None) -> FeedbackItem:
        item = FeedbackItem(
            prediction_id=prediction_id,
            useful=useful,
            comment=comment,
            created_at=time.time(),
        )
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    "INSERT INTO feedback (prediction_id, useful, comment, created_at) VALUES (?, ?, ?, ?)",
                    (item.prediction_id, int(item.useful), item.comment, item.created_at),
                )
        return item

    def add_outcome(self, prediction_id: str, actual_churn: bool, notes: str | None) -> OutcomeItem:
        item = OutcomeItem(
            prediction_id=prediction_id,
            actual_churn=actual_churn,
            notes=notes,
            created_at=time.time(),
        )
        with self._store.lock:
            with self._store.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO outcomes (prediction_id, actual_churn, notes, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(prediction_id) DO UPDATE SET
                        actual_churn=excluded.actual_churn,
                        notes=excluded.notes,
                        created_at=excluded.created_at
                    """,
                    (item.prediction_id, int(item.actual_churn), item.notes, item.created_at),
                )
        return item

    def list_feedback(self) -> list[FeedbackItem]:
        with self._store.lock:
            with self._store.connection() as conn:
                rows = conn.execute(
                    "SELECT prediction_id, useful, comment, created_at FROM feedback ORDER BY id ASC"
                ).fetchall()
        return [
            FeedbackItem(
                prediction_id=str(row["prediction_id"]),
                useful=bool(row["useful"]),
                comment=row["comment"],
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]

    def list_outcomes(self) -> list[OutcomeItem]:
        with self._store.lock:
            with self._store.connection() as conn:
                rows = conn.execute(
                    "SELECT prediction_id, actual_churn, notes, created_at FROM outcomes"
                ).fetchall()
        return [
            OutcomeItem(
                prediction_id=str(row["prediction_id"]),
                actual_churn=bool(row["actual_churn"]),
                notes=row["notes"],
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]

    def get_outcome(self, prediction_id: str) -> OutcomeItem | None:
        with self._store.lock:
            with self._store.connection() as conn:
                row = conn.execute(
                    "SELECT prediction_id, actual_churn, notes, created_at FROM outcomes WHERE prediction_id = ?",
                    (prediction_id,),
                ).fetchone()
        if row is None:
            return None
        return OutcomeItem(
            prediction_id=str(row["prediction_id"]),
            actual_churn=bool(row["actual_churn"]),
            notes=row["notes"],
            created_at=float(row["created_at"]),
        )
