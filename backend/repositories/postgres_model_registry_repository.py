from dataclasses import dataclass
import uuid

from sqlalchemy import Select, desc, select

from db.models import ModelVersion
from db.session import PostgresSessionFactory


@dataclass
class ModelVersionItem:
    id: str
    version: str
    metrics: dict[str, float]
    artifact_path: str
    status: str
    created_at: float


class PostgresModelRegistryRepository:
    def __init__(self, session_factory: PostgresSessionFactory, org_id: str, default_artifact_path: str) -> None:
        self._session_factory = session_factory
        self._org_id = uuid.UUID(org_id)

        with self._session_factory.session_scope() as session:
            existing = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "active")
                .limit(1)
            ).scalars().first()

            if existing is None:
                session.add(
                    ModelVersion(
                        org_id=self._org_id,
                        version_tag="v1",
                        stage="active",
                        artifact_uri=default_artifact_path,
                        metrics_summary={},
                        feature_schema={},
                    )
                )

    def list_versions(self) -> list[ModelVersionItem]:
        statement: Select[tuple[ModelVersion]] = (
            select(ModelVersion)
            .where(ModelVersion.org_id == self._org_id)
            .where(ModelVersion.deleted_at.is_(None))
            .order_by(ModelVersion.created_at.asc())
        )
        with self._session_factory.session_scope() as session:
            rows = session.execute(statement).scalars().all()

        return [
            ModelVersionItem(
                id=str(row.id),
                version=row.version_tag,
                metrics=row.metrics_summary,
                artifact_path=row.artifact_uri,
                status=row.stage,
                created_at=row.created_at.timestamp(),
            )
            for row in rows
        ]

    def get(self, model_id: str) -> ModelVersionItem | None:
        with self._session_factory.session_scope() as session:
            row = session.execute(
                select(ModelVersion)
                .where(ModelVersion.id == uuid.UUID(model_id))
                .where(ModelVersion.org_id == self._org_id)
                .limit(1)
            ).scalars().first()

        if row is None:
            return None

        return ModelVersionItem(
            id=str(row.id),
            version=row.version_tag,
            metrics=row.metrics_summary,
            artifact_path=row.artifact_uri,
            status=row.stage,
            created_at=row.created_at.timestamp(),
        )

    def register_candidate(self, version: str, metrics: dict[str, float], artifact_path: str) -> ModelVersionItem:
        with self._session_factory.session_scope() as session:
            row = ModelVersion(
                org_id=self._org_id,
                version_tag=version,
                stage="candidate",
                artifact_uri=artifact_path,
                metrics_summary=metrics,
                feature_schema={},
            )
            session.add(row)
            session.flush()

            return ModelVersionItem(
                id=str(row.id),
                version=row.version_tag,
                metrics=row.metrics_summary,
                artifact_path=row.artifact_uri,
                status=row.stage,
                created_at=row.created_at.timestamp(),
            )

    def set_shadow(self, candidate_model_id: str) -> None:
        candidate_id = uuid.UUID(candidate_model_id)
        with self._session_factory.session_scope() as session:
            current_shadow = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "shadow")
            ).scalars().all()

            for row in current_shadow:
                row.stage = "candidate"

            candidate = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.id == candidate_id)
                .limit(1)
            ).scalars().first()
            if candidate:
                candidate.stage = "shadow"

    def promote(self, candidate_model_id: str) -> None:
        candidate_id = uuid.UUID(candidate_model_id)
        with self._session_factory.session_scope() as session:
            active = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "active")
            ).scalars().all()
            for row in active:
                row.stage = "archived"

            candidate = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.id == candidate_id)
                .limit(1)
            ).scalars().first()
            if candidate:
                candidate.stage = "active"
                candidate.activated_at = candidate.activated_at or candidate.updated_at

            shadow_rows = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "shadow")
            ).scalars().all()
            for row in shadow_rows:
                if row.id == candidate_id:
                    row.stage = "active"

    def rollback(self, target_model_id: str | None = None) -> None:
        with self._session_factory.session_scope() as session:
            active = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "active")
            ).scalars().first()

            if target_model_id:
                target = session.execute(
                    select(ModelVersion)
                    .where(ModelVersion.org_id == self._org_id)
                    .where(ModelVersion.id == uuid.UUID(target_model_id))
                    .limit(1)
                ).scalars().first()
            else:
                target = session.execute(
                    select(ModelVersion)
                    .where(ModelVersion.org_id == self._org_id)
                    .where(ModelVersion.stage == "archived")
                    .order_by(desc(ModelVersion.created_at))
                    .limit(1)
                ).scalars().first()

            if not target:
                return

            if active:
                active.stage = "archived"
            target.stage = "active"
            target.activated_at = target.activated_at or target.updated_at

    def state(self) -> tuple[str, str | None]:
        with self._session_factory.session_scope() as session:
            active = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "active")
                .limit(1)
            ).scalars().first()
            shadow = session.execute(
                select(ModelVersion)
                .where(ModelVersion.org_id == self._org_id)
                .where(ModelVersion.stage == "shadow")
                .limit(1)
            ).scalars().first()

        return (str(active.id) if active else "", str(shadow.id) if shadow else None)
