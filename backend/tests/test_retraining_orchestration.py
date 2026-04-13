import asyncio
from types import SimpleNamespace

import pytest

from repositories.job_repository import JobRepository
from services.job_service import JobService, SchedulerService
from services.retraining_service import RetrainingOrchestrator


class _DummyPredictionService:
    async def predict(self, payload, threshold=0.5):
        return {
            "predictionId": "p1",
            "probability": 0.1,
            "isChurn": False,
        }


class _FakeRetrainingService:
    def __init__(self):
        self.calls = []

    async def run(self, payload):
        self.calls.append(payload)
        return {
            "status": "retraining_completed",
            "reason": payload.get("reason", "manual"),
        }


@pytest.mark.asyncio
async def test_job_service_executes_retraining_service():
    repo = JobRepository()
    retraining_service = _FakeRetrainingService()
    service = JobService(
        repo=repo,
        prediction_service=_DummyPredictionService(),
        retraining_service=retraining_service,
    )

    job = await service.enqueue_simple_job("retraining", payload={"reason": "test_manual"})

    worker = asyncio.create_task(service.worker_loop())
    await asyncio.wait_for(service._queue.join(), timeout=2)
    worker.cancel()

    stored = repo.get(job.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.result is not None
    assert stored.result["status"] == "retraining_completed"
    assert retraining_service.calls[0]["reason"] == "test_manual"


@pytest.mark.asyncio
async def test_scheduler_enqueues_retraining_on_drift_alert(monkeypatch):
    captured = []

    class _FakeJobService:
        async def enqueue_simple_job(self, job_type, payload=None, idempotency_key=None):
            captured.append((job_type, payload, idempotency_key))

    class _FakeMonitoringService:
        def snapshot(self):
            return {"alerts": ["Input drift alert"]}

    settings = SimpleNamespace(
        schedule_retrain_poll_seconds=0.01,
        schedule_retraining_enabled=True,
        schedule_retrain_cooldown_seconds=0,
        schedule_retrain_force_interval_seconds=86400,
    )

    import services.job_service as job_service_module

    monkeypatch.setattr(job_service_module, "get_settings", lambda: settings)

    scheduler = SchedulerService(_FakeJobService(), monitoring_service=_FakeMonitoringService())
    task = asyncio.create_task(scheduler.retraining_loop())

    await asyncio.sleep(0.05)
    task.cancel()

    assert captured, "Expected retraining jobs to be enqueued"
    job_type, payload, _ = captured[0]
    assert job_type == "retraining"
    assert payload["reason"] == "drift_alert"


def test_retraining_orchestrator_dry_run():
    orchestrator = RetrainingOrchestrator(model_registry_service=None)
    result = orchestrator._run_sync({"dry_run": True, "reason": "unit_test", "auto_promote": True})

    assert result["status"] == "dry_run"
    assert result["reason"] == "unit_test"
    assert result["auto_promote"] is True
    assert "dataset_path" in result
