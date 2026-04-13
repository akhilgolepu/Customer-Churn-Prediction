from services.canary_service import CanaryRolloutService


def test_canary_variant_distribution_disabled():
    service = CanaryRolloutService(
        enabled=False,
        traffic_percent=20,
        min_samples=10,
        max_disagreement_rate=0.4,
        rollback_cooldown_seconds=60,
    )

    variant = service.choose_variant("pred-1")
    assert variant == "active"


def test_canary_records_disagreement_and_triggers_rollback():
    service = CanaryRolloutService(
        enabled=True,
        traffic_percent=100,
        min_samples=3,
        max_disagreement_rate=0.5,
        rollback_cooldown_seconds=0,
    )

    # Active predicts churn, shadow predicts non-churn for each request.
    for i in range(3):
        result = service.record_prediction(
            prediction_id=f"pred-{i}",
            active_probability=0.9,
            shadow_probability=0.1,
            threshold=0.5,
        )

    assert result["variant"] == "shadow"
    assert result["rollback_triggered"] is True

    snapshot = service.snapshot()
    assert snapshot["canary_samples"] == 3
    assert snapshot["disagreements"] == 3
    assert snapshot["disagreement_rate"] == 1.0
    assert snapshot["last_rollback_reason"] is not None


def test_canary_no_shadow_prediction_keeps_active():
    service = CanaryRolloutService(
        enabled=True,
        traffic_percent=50,
        min_samples=2,
        max_disagreement_rate=0.5,
        rollback_cooldown_seconds=60,
    )

    result = service.record_prediction(
        prediction_id="pred-missing-shadow",
        active_probability=0.7,
        shadow_probability=None,
        threshold=0.5,
    )

    assert result["variant"] == "active"
    assert result["rollback_triggered"] is False

    snapshot = service.snapshot()
    assert snapshot["canary_samples"] == 0
