from __future__ import annotations

import services.model_registry_service as registry_module
from repositories.model_registry_repository import ModelRegistryRepository
from repositories.sqlite_store import SQLiteStore
from services.model_registry_service import ModelRegistryService


class _PassingGate:
    def evaluate(self, version, candidate_artifact, active_artifact):
        return {"promotion_allowed": True, "blockers": [], "warnings": []}


def _service(tmp_path, monkeypatch):
    calls: list[str | None] = []
    monkeypatch.setattr(registry_module, "switch_shadow_model", lambda path: calls.append(path))
    monkeypatch.setattr(registry_module, "switch_active_model", lambda path: None)
    repo = ModelRegistryRepository(store=SQLiteStore(str(tmp_path / "registry.db")), default_artifact_path="model/a.cbm")
    service = ModelRegistryService(
        repo=repo, validation_reports_dir=tmp_path / "reports", promotion_gate=_PassingGate()
    )
    return service, repo, calls


def test_abort_canary_rejects_shadow_and_keeps_active(tmp_path, monkeypatch):
    service, repo, calls = _service(tmp_path, monkeypatch)
    active_id, _ = repo.state()
    candidate = service.register_candidate("v2", {}, "model/b.cbm")
    service.start_shadow_test(candidate["id"])

    result = service.abort_canary("disagreement too high")

    assert result["rejected_model_id"] == candidate["id"]
    assert result["active_model_id"] == active_id
    assert result["shadow_model_id"] is None
    assert repo.get(candidate["id"]).status == "rejected"
    assert repo.get(active_id).status == "active"
    assert calls[-1] is None  # shadow model unloaded from the runtime


def test_abort_canary_does_not_demote_a_healthy_active_model(tmp_path, monkeypatch):
    """Regression: the old auto-rollback called rollback(), which archived the
    healthy active model and restored an older one."""
    service, repo, _ = _service(tmp_path, monkeypatch)
    v2 = service.register_candidate("v2", {}, "model/b.cbm")
    service.promote_candidate(v2["id"])  # v1 archived, v2 active
    v3 = service.register_candidate("v3", {}, "model/c.cbm")
    service.start_shadow_test(v3["id"])

    service.abort_canary("disagreement too high")

    active_id, shadow_id = repo.state()
    assert active_id == v2["id"]
    assert shadow_id is None
    assert repo.get(v3["id"]).status == "rejected"
