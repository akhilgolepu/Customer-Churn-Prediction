"""
Tests for MLflow tracker service.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path
from backend.services.mlflow_tracker import MLflowExperimentTracker


@pytest.fixture
def temp_tracking_uri():
    """Create temporary MLflow tracking directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield f"file:{tmpdir}"


@pytest.fixture
def tracker(temp_tracking_uri):
    """Create MLflow tracker with temporary backend."""
    return MLflowExperimentTracker(
        tracking_uri=temp_tracking_uri,
        experiment_name="test_experiment",
    )


@pytest.fixture
def sample_data():
    """Generate sample prediction data."""
    y_true = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1])
    y_pred_proba = np.array([0.1, 0.9, 0.2, 0.8, 0.85, 0.15, 0.92, 0.1, 0.88, 0.95])
    y_pred_binary = (y_pred_proba >= 0.5).astype(int)
    return y_true, y_pred_proba, y_pred_binary


class TestMLflowExperimentTracker:
    """Test MLflow tracker functionality."""

    def test_tracker_initialization(self, tracker):
        """Test tracker initialization."""
        assert tracker.experiment_name == "test_experiment"
        assert tracker.experiment_id is not None
        assert tracker.client is not None

    def test_tracking_run_context_manager(self, tracker):
        """Test tracking run context manager."""
        with tracker.tracking_run(run_name="test_run") as run:
            assert run is not None
            assert run.info.run_name == "test_run"

    def test_log_training_config(self, tracker, sample_data):
        """Test logging training configuration."""
        with tracker.tracking_run(run_name="config_test"):
            tracker.log_training_config(
                model_type="CatBoost",
                model_params={"depth": 6, "iterations": 100},
                training_data_version="dvc://v1.0.0",
                preprocessing_version="v1.0.0",
                test_size=0.2,
            )
            # If no exception, test passes
            assert True

    def test_log_dataset_stats(self, tracker):
        """Test logging dataset statistics."""
        df = pd.DataFrame({
            "feature_1": np.random.rand(100),
            "feature_2": np.random.rand(100),
            "target": np.random.randint(0, 2, 100),
        })

        with tracker.tracking_run(run_name="dataset_test"):
            tracker.log_dataset_stats(df, "train")
            # If no exception, test passes
            assert True

    def test_log_metrics(self, tracker, sample_data):
        """Test logging classification metrics."""
        y_true, y_pred_proba, y_pred_binary = sample_data

        with tracker.tracking_run(run_name="metrics_test"):
            metrics = tracker.log_metrics(
                y_true, y_pred_proba, y_pred_binary, "test"
            )

            assert "test_auc" in metrics
            assert "test_recall" in metrics
            assert "test_precision" in metrics
            assert "test_f1" in metrics
            assert all(isinstance(v, float) for v in metrics.values())

    def test_log_confusion_matrix(self, tracker, sample_data):
        """Test logging confusion matrix."""
        y_true, _, y_pred_binary = sample_data

        with tracker.tracking_run(run_name="cm_test"):
            tracker.log_confusion_matrix(y_true, y_pred_binary, "test")
            # If no exception, test passes
            assert True

    def test_log_feature_importance(self, tracker):
        """Test logging feature importance."""
        # Mock feature importance data
        feature_names = ["feature_1", "feature_2", "feature_3"]
        importances = np.array([0.5, 0.3, 0.2])

        # Create mock model with get_feature_importance
        class MockModel:
            def get_feature_importance(self):
                return importances

        with tracker.tracking_run(run_name="importance_test"):
            model = MockModel()
            tracker.log_feature_importance(model, feature_names)
            # If no exception, test passes
            assert True

    def test_create_lineage_record(self, tracker, sample_data):
        """Test creating lineage record."""
        y_true, y_pred_proba, y_pred_binary = sample_data

        with tracker.tracking_run(run_name="lineage_test") as run:
            evaluation_metrics = {
                "auc": float(0.89),
                "f1": float(0.75),
            }

            with tempfile.TemporaryDirectory() as tmpdir:
                bundle_path = Path(tmpdir) / "bundle.zip"
                bundle_path.touch()

                lineage = tracker.create_lineage_record(
                    run_id=run.info.run_id,
                    model_version="v1.0.0",
                    pipeline_bundle_path=bundle_path,
                    evaluation_metrics=evaluation_metrics,
                )

                assert lineage["mlflow_run_id"] == run.info.run_id
                assert lineage["deployed_model_version"] == "v1.0.0"
                assert lineage["evaluation_metrics"] == evaluation_metrics

    def test_get_experiment_runs(self, tracker):
        """Test retrieving experiment runs."""
        # Create multiple runs
        for i in range(3):
            with tracker.tracking_run(run_name=f"run_{i}"):
                import mlflow
                mlflow.log_metric("auc", 0.85 + i * 0.01)

        runs = tracker.get_experiment_runs(max_results=10)
        assert len(runs) >= 3
        assert all("run_id" in r for r in runs)
        assert all("metrics" in r for r in runs)

    def test_compare_runs(self, tracker):
        """Test comparing runs."""
        run_ids = []
        
        for i in range(2):
            with tracker.tracking_run(run_name=f"compare_run_{i}"):
                import mlflow
                mlflow.log_metric("auc", 0.80 + i * 0.05)
                mlflow.log_param("learning_rate", 0.1 + i * 0.05)
                run_ids.append(mlflow.active_run().info.run_id)

        if len(run_ids) >= 2:
            df = tracker.compare_runs(run_ids[:2])
            assert len(df) == 2
            assert "auc" in df.columns or any("auc" in str(c) for c in df.columns)


class TestMLflowIntegrationPatterns:
    """Test common MLflow usage patterns."""

    def test_full_training_run_workflow(self, tracker, sample_data):
        """Test complete training run with MLflow."""
        y_true, y_pred_proba, y_pred_binary = sample_data

        with tracker.tracking_run(
            run_name="full_workflow",
            tags={"stage": "development", "model": "catboost"}
        ):
            # Log config
            tracker.log_training_config(
                model_type="CatBoost",
                model_params={"depth": 6, "iterations": 100},
                training_data_version="v1.0.0",
                preprocessing_version="v1.0.0",
            )

            # Log dataset stats
            df = pd.DataFrame({
                "feature_1": np.random.rand(100),
                "feature_2": np.random.rand(100),
                "target": np.random.randint(0, 2, 100),
            })
            tracker.log_dataset_stats(df, "train")

            # Log metrics
            test_metrics = tracker.log_metrics(
                y_true, y_pred_proba, y_pred_binary, "test"
            )

            # Log confusion matrix
            tracker.log_confusion_matrix(y_true, y_pred_binary, "test")

            # Verify metrics were logged
            assert test_metrics["test_auc"] > 0
            assert test_metrics["test_f1"] > 0

    def test_cross_validation_workflow(self, tracker):
        """Test cross-validation experiment tracking."""
        fold_results = [
            {"auc": 0.85, "f1": 0.75},
            {"auc": 0.87, "f1": 0.76},
            {"auc": 0.86, "f1": 0.74},
        ]

        with tracker.tracking_run(run_name="cv_workflow"):
            import mlflow
            from backend.services.mlflow_tracker import log_cross_validation_results

            log_cross_validation_results(fold_results)
            # If no exception, test passes
            assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
