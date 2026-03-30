from dataclasses import dataclass
import time
import uuid

from sqlalchemy import Select, select

from db.models import FeedbackEvent
from db.session import PostgresSessionFactory


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


class PostgresFeedbackRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

    def add_feedback(self, prediction_id: str, useful: bool, comment: str | None) -> FeedbackItem:
        created_at = time.time()
        payload = {"useful": useful, "comment": comment}
        with self._session_factory.session_scope() as session:
            session.add(
                FeedbackEvent(
                    org_id=self._org_id,
                    prediction_id=uuid.UUID(prediction_id),
                    event_type="feedback",
                    payload=payload,
                )
            )
        return FeedbackItem(prediction_id=prediction_id, useful=useful, comment=comment, created_at=created_at)

    def add_outcome(self, prediction_id: str, actual_churn: bool, notes: str | None) -> OutcomeItem:
        created_at = time.time()
        payload = {"actual_churn": actual_churn, "notes": notes}
        with self._session_factory.session_scope() as session:
            session.add(
                FeedbackEvent(
                    org_id=self._org_id,
                    prediction_id=uuid.UUID(prediction_id),
                    event_type="outcome",
                    payload=payload,
                )
            )
        return OutcomeItem(prediction_id=prediction_id, actual_churn=actual_churn, notes=notes, created_at=created_at)

    def list_feedback(self) -> list[FeedbackItem]:
        statement: Select[tuple[FeedbackEvent]] = (
            select(FeedbackEvent)
            .where(FeedbackEvent.org_id == self._org_id)
            .where(FeedbackEvent.event_type == "feedback")
            .order_by(FeedbackEvent.event_at.asc())
        )
        with self._session_factory.session_scope() as session:
            rows = session.execute(statement).scalars().all()

        return [
            FeedbackItem(
                prediction_id=str(row.prediction_id),
                useful=bool(row.payload.get("useful", False)),
                comment=row.payload.get("comment"),
                created_at=row.event_at.timestamp(),
            )
            for row in rows
        ]

    def list_outcomes(self) -> list[OutcomeItem]:
        statement: Select[tuple[FeedbackEvent]] = (
            select(FeedbackEvent)
            .where(FeedbackEvent.org_id == self._org_id)
            .where(FeedbackEvent.event_type == "outcome")
            .order_by(FeedbackEvent.event_at.asc())
        )
        with self._session_factory.session_scope() as session:
            rows = session.execute(statement).scalars().all()

        return [
            OutcomeItem(
                prediction_id=str(row.prediction_id),
                actual_churn=bool(row.payload.get("actual_churn", False)),
                notes=row.payload.get("notes"),
                created_at=row.event_at.timestamp(),
            )
            for row in rows
        ]

    def get_outcome(self, prediction_id: str) -> OutcomeItem | None:
        statement: Select[tuple[FeedbackEvent]] = (
            select(FeedbackEvent)
            .where(FeedbackEvent.org_id == self._org_id)
            .where(FeedbackEvent.prediction_id == uuid.UUID(prediction_id))
            .where(FeedbackEvent.event_type == "outcome")
            .order_by(FeedbackEvent.event_at.desc())
            .limit(1)
        )
        with self._session_factory.session_scope() as session:
            row = session.execute(statement).scalars().first()

        if row is None:
            return None

        return OutcomeItem(
            prediction_id=str(row.prediction_id),
            actual_churn=bool(row.payload.get("actual_churn", False)),
            notes=row.payload.get("notes"),
            created_at=row.event_at.timestamp(),
        )
