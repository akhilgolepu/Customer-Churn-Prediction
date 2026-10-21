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


def test_canary_disagreement_rate_is_measured_over_all_compared_requests():
    """Regression: the rate used to be divided by requests *served* by the shadow
    (canary_traffic_percent of the total), inflating it past 100% and rolling
    back healthy candidates."""
    service = CanaryRolloutService(
        enabled=True,
        traffic_percent=10,
        min_samples=50,
        max_disagreement_rate=0.35,
        rollback_cooldown_seconds=0,
    )

    triggered = False
    for i in range(200):
        disagrees = i % 10 == 0  # 10% of requests disagree
        result = service.record_prediction(
            prediction_id=f"pred-{i}",
            active_probability=0.9,
            shadow_probability=0.1 if disagrees else 0.9,
            threshold=0.5,
        )
        triggered = triggered or result["rollback_triggered"]

    snapshot = service.snapshot()
    assert snapshot["compared_samples"] == 200
    assert snapshot["disagreements"] == 20
    assert abs(snapshot["disagreement_rate"] - 0.10) < 1e-9
    assert triggered is False


def test_canary_reset_clears_counters_and_restores_configured_enabled_state():
    service = CanaryRolloutService(
        enabled=True, traffic_percent=100, min_samples=1, max_disagreement_rate=0.1, rollback_cooldown_seconds=0
    )
    service.record_prediction("p1", 0.9, 0.1, 0.5)
    service.disable()
    assert service.snapshot()["enabled"] is False

    service.reset()

    snapshot = service.snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["compared_samples"] == 0
    assert snapshot["disagreements"] == 0
