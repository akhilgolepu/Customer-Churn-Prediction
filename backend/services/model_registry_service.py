from core.exceptions import NotFoundError
from model_loader import switch_active_model, switch_shadow_model
from repositories.model_registry_repository import ModelRegistryRepository


class ModelRegistryService:
    def __init__(self, repo: ModelRegistryRepository) -> None:
        self._repo = repo

    def list_registry(self) -> dict:
        active_model_id, shadow_model_id = self._repo.state()
        versions = [
            {
                "id": item.id,
                "version": item.version,
                "metrics": item.metrics,
                "artifact_path": item.artifact_path,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in self._repo.list_versions()
        ]
        return {
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
            "versions": versions,
        }

    def register_candidate(self, version: str, metrics: dict[str, float], artifact_path: str) -> dict:
        item = self._repo.register_candidate(version=version, metrics=metrics, artifact_path=artifact_path)
        return {
            "id": item.id,
            "version": item.version,
            "metrics": item.metrics,
            "artifact_path": item.artifact_path,
            "status": item.status,
            "created_at": item.created_at,
        }

    def start_shadow_test(self, candidate_model_id: str) -> dict:
        candidate = self._repo.get(candidate_model_id)
        if candidate is None:
            raise NotFoundError("Candidate model not found")

        switch_shadow_model(candidate.artifact_path)
        self._repo.set_shadow(candidate_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        return {
            "message": "Shadow test enabled",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }

    def promote_candidate(self, candidate_model_id: str) -> dict:
        candidate = self._repo.get(candidate_model_id)
        if candidate is None:
            raise NotFoundError("Candidate model not found")

        switch_active_model(candidate.artifact_path)
        self._repo.promote(candidate_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        if shadow_model_id is None:
            switch_shadow_model(None)
        return {
            "message": "Candidate promoted to active model",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }

    def rollback(self, target_model_id: str | None = None) -> dict:
        self._repo.rollback(target_model_id=target_model_id)
        active_model_id, shadow_model_id = self._repo.state()
        active_item = self._repo.get(active_model_id)
        if active_item is None:
            raise NotFoundError("Active model not found after rollback")

        switch_active_model(active_item.artifact_path)
        if shadow_model_id is None:
            switch_shadow_model(None)
        return {
            "message": "Rollback completed",
            "active_model_id": active_model_id,
            "shadow_model_id": shadow_model_id,
        }
