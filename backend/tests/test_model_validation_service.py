"""
Tests for model validation gate service.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path
from backend.services.model_validation_service import (
    ModelValidationGate,
    ModelQualityValidator,
    FairnessValidator,
    PerformanceValidator,
    DataIntegrityValidator,
    CheckStatus,
    measure_latency,
    measure_memory_usage,
)


@pytest.fixture
def sample_predictions():
    """Generate sample predictions for testing."""
    np.random.seed(42)
    y_true = np.random.randint(0, 2, 200)
    # Create predictions aligned with y_true positions so all arrays share the same shape.
    y_pred_proba = np.where(
        y_true == 1,
        np.random.uniform(0.7, 1.0, size=y_true.shape[0]),
        np.random.uniform(0.0, 0.3, size=y_true.shape[0]),
    )
    y_pred_binary = (y_pred_proba >= 0.5).astype(int)
    return y_true, y_pred_proba, y_pred_binary


@pytest.fixture
def sample_test_data():
    """Generate sample test data."""
    return pd.DataFrame({
        "feature_1": np.random.rand(100),
        "feature_2": np.random.rand(100),
        "target": np.random.randint(0, 2, 100),
    })


class TestModelQualityValidator:
    """Test model quality validation."""

    def test_quality_validation_passing(self, sample_predictions):
        """Test that good predictions pass quality gates."""
        y_true, y_pred_proba, y_pred_binary = sample_predictions
        validator = ModelQualityValidator()

        results, passed = validator.validate_binary_classification_metrics(
            y_true, y_pred_proba, y_pred_binary
        )

        assert len(results) == 4  # AUC, Recall, Precision, F1
        assert all(r.category == "quality" for r in results)

    def test_quality_validation_metrics_extracted(self, sample_predictions):
        """Test that metrics are correctly extracted."""
        y_true, y_pred_proba, y_pred_binary = sample_predictions
        validator = ModelQualityValidator()

        results, _ = validator.validate_binary_classification_metrics(
            y_true, y_pred_proba, y_pred_binary
        )

        names = [r.name for r in results]
        assert "ROC AUC Score" in names
        assert "Recall Score" in names
        assert "Precision Score" in names
        assert "F1 Score" in names


class TestFairnessValidator:
    """Test fairness validation."""

    def test_demographic_parity_fair(self):
        """Test fair demographic parity."""
        np.random.seed(42)
        y_true = np.random.randint(0, 2, 200)
        y_pred = np.random.randint(0, 2, 200)
        protected_attr = np.array([0] * 100 + [1] * 100)

        validator = FairnessValidator()
        result, passed = validator.validate_demographic_parity(
            y_true, y_pred, protected_attr
        )

        assert result.category == "fairness"
        assert result.name == "Demographic Parity (protected_group)"

    def test_demographic_parity_unfair(self):
        """Test unfair demographic parity."""
        y_true = np.array([1, 0] * 50)
        y_pred = np.array([1] * 100 + [0] * 100)  # Predict 1 for group 0, 0 for group 1
        protected_attr = np.array([0] * 100 + [1] * 100)

        validator = FairnessValidator()
        result, passed = validator.validate_demographic_parity(
            y_true, y_pred, protected_attr
        )

        assert result.category == "fairness"
        # Should detect inequality
        assert result.details["difference"] > 0


class TestPerformanceValidator:
    """Test performance validation."""

    def test_latency_passing(self):
        """Test passing latency check."""
        validator = PerformanceValidator()
        result = validator.validate_latency(1000.0, "model_predict")

        assert result.status == CheckStatus.PASSED
        assert result.category == "performance"

    def test_latency_failing(self):
        """Test failing latency check."""
        validator = PerformanceValidator()
        result = validator.validate_latency(5000.0, "model_predict")

        assert result.status == CheckStatus.FAILED
        assert result.category == "performance"

    def test_memory_passing(self):
        """Test passing memory check."""
        validator = PerformanceValidator()
        result = validator.validate_memory_usage(300.0)

        assert result.status == CheckStatus.PASSED

    def test_memory_failing(self):
        """Test failing memory check."""
        validator = PerformanceValidator()
        result = validator.validate_memory_usage(600.0)

        assert result.status == CheckStatus.FAILED

    def test_throughput_validation(self):
        """Test throughput validation."""
        validator = PerformanceValidator()
        result = validator.validate_throughput(total_predictions=100, duration_seconds=10)

        assert result.category == "performance"
        assert result.name == "Throughput"


class TestDataIntegrityValidator:
    """Test data integrity validation."""

    def test_schema_validation_passing(self, sample_test_data):
        """Test passing schema validation."""
        validator = DataIntegrityValidator()
        expected_columns = ["feature_1", "feature_2", "target"]
        expected_dtypes = {
            "feature_1": "float",
            "feature_2": "float",
            "target": "int",
        }

        results, passed = validator.validate_schema(
            sample_test_data, expected_columns, expected_dtypes
        )

        assert len(results) == 2  # Column presence + dtype check
        assert passed is True

    def test_schema_validation_missing_columns(self, sample_test_data):
        """Test schema validation with missing columns."""
        validator = DataIntegrityValidator()
        expected_columns = ["feature_1", "feature_2", "feature_3", "target"]
        expected_dtypes = {"feature_1": "float", "feature_2": "float", "target": "int"}

        results, passed = validator.validate_schema(
            sample_test_data, expected_columns, expected_dtypes
        )

        assert passed is False

    def test_missing_data_validation_clean(self, sample_test_data):
        """Test missing data validation on clean data."""
        validator = DataIntegrityValidator()
        result = validator.validate_missing_data(sample_test_data)

        assert result.status == CheckStatus.PASSED

    def test_missing_data_validation_dirty(self):
        """Test missing data validation on data with nulls."""
        df = pd.DataFrame({
            "feature_1": [1.0, np.nan, 3.0] * 20,
            "feature_2": [1.0, 2.0, np.nan] * 20,
        })

        validator = DataIntegrityValidator()
        result = validator.validate_missing_data(df)

        # Should detect missing values
        assert result.details["max_missing_percent"] > 0


class TestModelValidationGate:
    """Test main validation gate orchestrator."""

    def test_full_validation_passing(self, sample_predictions, sample_test_data):
        """Test full validation gate with passing checks."""
        y_true, y_pred_proba, y_pred_binary = sample_predictions
        protected_attr = np.random.randint(0, 2, len(y_true))

        gate = ModelValidationGate()
        report = gate.validate_for_promotion(
            model_version="v1",
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
            protected_attribute=protected_attr,
            latency_measurements={
                "model_predict_ms": 1500.0,
                "preprocess_ms": 800.0,
            },
            memory_mb=250.0,
            test_df=sample_test_data,
            expected_columns=["feature_1", "feature_2", "target"],
            expected_dtypes={"feature_1": "float", "feature_2": "float", "target": "int"},
        )

        assert report.model_version == "v1"
        assert report.total_checks > 0
        assert report.passed_checks > 0

    def test_validation_gate_report_json(self, sample_predictions, sample_test_data):
        """Test validation gate report can be serialized to JSON."""
        y_true, y_pred_proba, y_pred_binary = sample_predictions

        gate = ModelValidationGate()
        report = gate.validate_for_promotion(
            model_version="v1",
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
            latency_measurements={"model_predict_ms": 1500.0},
            memory_mb=250.0,
        )

        json_str = report.to_json()
        assert "model_version" in json_str
        assert "v1" in json_str

    def test_validation_gate_save_report(self, sample_predictions, sample_test_data):
        """Test validation gate report can be saved to file."""
        y_true, y_pred_proba, y_pred_binary = sample_predictions

        gate = ModelValidationGate()
        report = gate.validate_for_promotion(
            model_version="v1",
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "validation_report.json"
            gate.save_report(report, report_path)

            assert report_path.exists()
            content = report_path.read_text()
            assert "model_version" in content


class TestMeasurementUtilities:
    """Test measurement utility functions."""

    def test_measure_latency(self):
        """Test latency measurement."""
        def slow_func():
            import time
            time.sleep(0.1)
            return 42

        result, latency_ms = measure_latency(slow_func)

        assert result == 42
        assert latency_ms >= 100  # Should be at least 100ms

    def test_measure_memory(self):
        """Test memory measurement."""
        def memory_func():
            arr = [0] * 1000000
            return sum(arr)

        result, peak_mb = measure_memory_usage(memory_func)

        assert result == 0
        assert peak_mb > 0


class TestValidationGateIntegration:
    """Integration tests for validation gate."""

    def test_blockers_prevent_promotion(self):
        """Test that validation blockers prevent promotion."""
        np.random.seed(42)
        # Create predictions that should fail quality gates
        y_true = np.array([1, 0] * 50)
        y_pred_proba = np.random.uniform(0.4, 0.6, 100)  # Poor discrimination
        y_pred_binary = (y_pred_proba >= 0.5).astype(int)

        gate = ModelValidationGate()
        report = gate.validate_for_promotion(
            model_version="v_poor",
            y_true=y_true,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
        )

        # Poor model should have blockers
        assert len(report.blockers) > 0
        assert report.promotion_allowed is False

    def test_warnings_allow_but_note_issues(self):
        """Test that warnings allow promotion but note concerns."""
        gate = ModelValidationGate()
        report = gate.validate_for_promotion(
            model_version="v_warn",
            # Intentionally omit quality data to generate warnings
        )

        assert len(report.warnings) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
