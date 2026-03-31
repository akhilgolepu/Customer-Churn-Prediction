from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import Select, desc, func, select

from db.models import ModelVersion, Prediction
from db.session import PostgresSessionFactory
from repositories.prediction_repository import PredictionHistoryItem


class PostgresPredictionRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

    @staticmethod
    def _risk_tier(probability: float) -> str:
        if probability < 0.33:
            return "low"
        if probability < 0.66:
            return "medium"
        return "high"

    def _resolve_active_model_version_id(self) -> uuid.UUID:
        statement: Select[tuple[ModelVersion]] = (
            select(ModelVersion)
            .where(ModelVersion.org_id == self._org_id)
            .where(ModelVersion.deleted_at.is_(None))
            .where(ModelVersion.stage == "active")
            .order_by(desc(func.coalesce(ModelVersion.activated_at, ModelVersion.created_at)))
            .limit(1)
        )

        with self._session_factory.session_scope() as session:
            row = session.execute(statement).scalars().first()

        if row is None:
            raise RuntimeError("No active model version found for organization")
        return row.id

    def add(self, item: PredictionHistoryItem) -> None:
        model_version_id = self._resolve_active_model_version_id()
        probability = float(item.probability)
        prediction_at = datetime.fromtimestamp(item.created_at, tz=timezone.utc)

        with self._session_factory.session_scope() as session:
            session.add(
                Prediction(
                    id=uuid.UUID(item.id),
                    org_id=self._org_id,
                    model_version_id=model_version_id,
                    raw_input=item.inputs,
                    engineered_snapshot=item.inputs,
                    probability=probability,
                    risk_score=probability,
                    risk_tier=self._risk_tier(probability),
                    threshold=float(item.threshold),
                    is_churn=bool(item.is_churn),
                    prediction_at=prediction_at,
                )
            )

    def list_paginated(
        self,
        page: int,
        page_size: int,
        is_churn: bool | None = None,
    ) -> tuple[list[PredictionHistoryItem], int]:
        base_statement: Select[tuple[Prediction]] = (
            select(Prediction)
            .where(Prediction.org_id == self._org_id)
            .where(Prediction.deleted_at.is_(None))
        )

        if is_churn is not None:
            base_statement = base_statement.where(Prediction.is_churn == is_churn)

        count_statement = select(func.count()).select_from(base_statement.subquery())
        data_statement = (
            base_statement
            .order_by(desc(Prediction.prediction_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        with self._session_factory.session_scope() as session:
            total = int(session.execute(count_statement).scalar_one())
            rows = session.execute(data_statement).scalars().all()

        return (
            [
                PredictionHistoryItem(
                    id=str(row.id),
                    created_at=row.prediction_at.timestamp(),
                    probability=float(row.probability),
                    is_churn=bool(row.is_churn),
                    threshold=float(row.threshold),
                    inputs=row.raw_input,
                )
                for row in rows
            ],
            total,
        )
