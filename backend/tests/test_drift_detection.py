"""
Tests for drift detection and alert routing.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path
from backend.services.drift_detector import (
    EvidentiallyDriftDetector,
    ConceptDriftMonitor,
    DriftReport,
    DriftAlert,
)
from backend.services.alert_router import (
    AlertRouter,
    AlertSeverity,
    WebhookAlertChannel,
    create_router_from_config,
)


@pytest.fixture
def reference_data():
    """Create reference dataset."""
    np.random.seed(42)
    return pd.DataFrame({
        "feature_1": np.random.normal(0, 1, 1000),
        "feature_2": np.random.normal(0, 1, 1000),
        "feature_3": np.random.normal(0, 1, 1000),
    })


@pytest.fixture
def detector(reference_data):
    """Create drift detector."""
    try:
        return EvidentiallyDriftDetector(
            reference_data=reference_data,
            feature_names=["feature_1", "feature_2", "feature_3"],
            numerical_features=["feature_1", "feature_2", "feature_3"],
            drift_threshold=0.05,
        )
    except ImportError:
        pytest.skip("Evidently AI not installed")


class TestEvidentiallyDriftDetector:
    """Test drift detection functionality."""

    def test_detector_initialization(self, detector):
        """Test detector initialization."""
        assert detector.reference_data is not None
        assert len(detector.feature_names) == 3
        assert detector.drift_threshold == 0.05

    def test_detect_no_drift(self, detector, reference_data):
        """Test detection when no drift present."""
        # Use similar distribution
        production_data = pd.DataFrame({
            "feature_1": np.random.normal(0, 1, 500),
            "feature_2": np.random.normal(0, 1, 500),
            "feature_3": np.random.normal(0, 1, 500),
        })

        try:
            report = detector.detect_data_drift(production_data)
            assert isinstance(report, DriftReport)
            assert report.report_id is not None
        except ImportError:
            pytest.skip("Evidently AI not installed")

    def test_detect_drift_present(self, detector):
        """Test detection when drift is present."""
        # Create drifted production data
        production_data = pd.DataFrame({
            "feature_1": np.random.normal(2.0, 1.5, 500),  # Drifted
            "feature_2": np.random.normal(0, 1, 500),
            "feature_3": np.random.normal(0, 1, 500),
        })

        try:
            report = detector.detect_data_drift(production_data)
            assert isinstance(report, DriftReport)
            assert report.timestamp is not None
        except ImportError:
            pytest.skip("Evidently AI not installed")

    def test_detect_outliers(self, detector, reference_data):
        """Test outlier detection."""
        # Create data with outliers
        production_data = pd.concat([
            pd.DataFrame({
                "feature_1": np.random.normal(0, 1, 480),
                "feature_2": np.random.normal(0, 1, 480),
                "feature_3": np.random.normal(0, 1, 480),
            }),
            pd.DataFrame({
                "feature_1": np.random.uniform(10, 20, 20),  # Outliers
                "feature_2": np.random.uniform(10, 20, 20),
                "feature_3": np.random.uniform(10, 20, 20),
            }),
        ], ignore_index=True)

        try:
            report = detector.detect_outliers(production_data, sigma_threshold=3.0)
            assert isinstance(report, DriftReport)
            assert report.report_id is not None
        except ImportError:
            pytest.skip("Evidently AI not installed")

    def test_performance_drift_detection(self, detector):
        """Test performance drift detection."""
        y_true = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1])
        y_pred_proba = np.array([0.1, 0.9, 0.2, 0.8, 0.85, 0.15, 0.92, 0.1, 0.88, 0.95])
        y_pred_binary = (y_pred_proba >= 0.5).astype(int)
        production_data = pd.DataFrame({
            "feature_1": np.random.rand(10),
            "feature_2": np.random.rand(10),
            "feature_3": np.random.rand(10),
        })

        try:
            report = detector.detect_performance_drift(
                production_data=production_data,
                y_true=y_true,
                y_pred_proba=y_pred_proba,
                y_pred_binary=y_pred_binary,
                reference_auc=0.95,
            )

            assert isinstance(report, DriftReport)
            assert "model_performance" in [a["feature_name"] for a in report.alerts]
        except ImportError:
            pytest.skip("Evidently AI not installed")

    def test_save_report(self, detector, reference_data):
        """Test saving drift report."""
        production_data = pd.DataFrame({
            "feature_1": np.random.normal(0, 1, 500),
            "feature_2": np.random.normal(0, 1, 500),
            "feature_3": np.random.normal(0, 1, 500),
        })

        try:
            report = detector.detect_data_drift(production_data)

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = detector.save_report(report, Path(tmpdir))
                assert output_path.exists()
                assert output_path.suffix == ".json"
        except ImportError:
            pytest.skip("Evidently AI not installed")

    def test_should_retrain_logic(self, detector, reference_data):
        """Test retraining trigger logic."""
        production_data = pd.DataFrame({
            "feature_1": np.random.normal(2.0, 1.5, 500),
            "feature_2": np.random.normal(2.0, 1.5, 500),
            "feature_3": np.random.normal(2.0, 1.5, 500),
            "feature_4": np.random.normal(0, 1, 500),
        })

        try:
            detector.detect_data_drift(production_data)

            # Test retraining trigger with mock critical report
            critical_report = DriftReport(
                report_id="test",
                timestamp=pd.Timestamp.now().isoformat(),
                reference_period="reference",
                production_period="production",
                drifted_features=["f1", "f2", "f3", "f4"],
                data_quality_issues=[],
                alerts=[],
                metrics={},
                alerts_severity="critical",
            )

            should_retrain = detector.should_retrain(critical_report, drift_feature_threshold=3)
            assert should_retrain is True
        except ImportError:
            pytest.skip("Evidently AI not installed")


class TestConceptDriftMonitor:
    """Test concept drift monitoring."""

    def test_monitor_initialization(self):
        """Test monitor initialization."""
        baseline = {"auc": 0.85, "f1": 0.75}
        monitor = ConceptDriftMonitor(baseline_metrics=baseline)

        assert monitor.baseline_metrics == baseline
        assert monitor.history == []

    def test_no_concept_drift(self):
        """Test case with no concept drift."""
        baseline = {"auc": 0.85, "f1": 0.75}
        monitor = ConceptDriftMonitor(baseline_metrics=baseline)

        current = {"auc": 0.84, "f1": 0.74}  # Small drop, < 5%
        drift_detected, degraded = monitor.check_metrics(current)

        assert drift_detected is False
        assert len(degraded) == 0

    def test_concept_drift_detected(self):
        """Test case with concept drift."""
        baseline = {"auc": 0.85, "f1": 0.75}
        monitor = ConceptDriftMonitor(baseline_metrics=baseline, degradation_threshold=0.05)

        current = {"auc": 0.78, "f1": 0.68}  # > 5% drop
        drift_detected, degraded = monitor.check_metrics(current)

        assert drift_detected is True
        assert len(degraded) > 0

    def test_drift_history(self):
        """Test drift history tracking."""
        baseline = {"auc": 0.85}
        monitor = ConceptDriftMonitor(baseline_metrics=baseline)

        for i in range(3):
            current = {"auc": 0.85 - i * 0.02}
            monitor.check_metrics(current)

        history = monitor.get_drift_history(days=7)
        assert len(history) == 3


class TestAlertRouter:
    """Test alert routing."""

    def test_router_initialization(self):
        """Test router initialization."""
        router = AlertRouter()
        assert len(router.channels) == 0
        assert len(router.severity_rules) == 5

    def test_register_channel(self):
        """Test channel registration."""
        router = AlertRouter()
        channel = WebhookAlertChannel(webhook_url="http://localhost:8000/webhook")

        router.register_channel("test_webhook", channel)

        assert "test_webhook" in router.channels

    def test_set_severity_routing(self):
        """Test severity routing configuration."""
        router = AlertRouter()
        channel = WebhookAlertChannel(webhook_url="http://localhost:8000/webhook")
        router.register_channel("test", channel)

        router.set_severity_routing(AlertSeverity.CRITICAL, ["test"])

        assert "test" in router.severity_rules[AlertSeverity.CRITICAL]

    def test_create_router_from_config(self):
        """Test creating router from config."""
        config = {
            "channels": {
                "webhook": {
                    "type": "webhook",
                    "webhook_url": "http://localhost:8000/webhook",
                }
            },
            "severity_rules": {
                "critical": ["webhook"],
                "high": ["webhook"],
                "medium": [],
                "low": [],
                "info": [],
            },
        }

        router = create_router_from_config(config)

        assert "webhook" in router.channels
        assert "webhook" in router.severity_rules[AlertSeverity.CRITICAL]


class TestAlertChannels:
    """Test alert channels."""

    def test_webhook_alert_channel_creation(self):
        """Test webhook channel creation."""
        channel = WebhookAlertChannel(
            webhook_url="http://localhost:8000/webhook",
            custom_headers={"X-API-Key": "test-key"},
        )

        assert channel.webhook_url == "http://localhost:8000/webhook"
        assert "X-API-Key" in channel.custom_headers


class TestDriftAlert:
    """Test drift alert data structures."""

    def test_drift_alert_creation(self):
        """Test creating drift alert."""
        alert = DriftAlert(
            timestamp="2026-04-13T10:00:00",
            feature_name="feature_1",
            drift_detected=True,
            drift_type="statistical",
            magnitude=0.03,
            threshold=0.05,
            reference_value=0.5,
            production_value=0.48,
            message="Drift detected in feature_1",
        )

        assert alert.feature_name == "feature_1"
        assert alert.drift_detected is True

    def test_drift_alert_to_dict(self):
        """Test converting alert to dict."""
        alert = DriftAlert(
            timestamp="2026-04-13T10:00:00",
            feature_name="feature_1",
            drift_detected=True,
            drift_type="statistical",
            magnitude=0.03,
            threshold=0.05,
        )

        alert_dict = alert.to_dict()
        assert isinstance(alert_dict, dict)
        assert alert_dict["feature_name"] == "feature_1"


class TestDriftReport:
    """Test drift report data structures."""

    def test_drift_report_creation(self):
        """Test creating drift report."""
        report = DriftReport(
            report_id="drift_001",
            timestamp="2026-04-13T10:00:00",
            reference_period="Training data",
            production_period="Production data",
            drifted_features=["feature_1", "feature_2"],
            data_quality_issues=[],
            alerts=[],
            metrics={},
        )

        assert report.report_id == "drift_001"
        assert len(report.drifted_features) == 2

    def test_drift_report_to_json(self):
        """Test converting report to JSON."""
        report = DriftReport(
            report_id="drift_001",
            timestamp="2026-04-13T10:00:00",
            reference_period="Training",
            production_period="Production",
            drifted_features=["f1"],
            data_quality_issues=[],
            alerts=[],
            metrics={},
        )

        json_str = report.to_json()
        assert "drift_001" in json_str
        assert "f1" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
