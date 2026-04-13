"""
MLflow Integration Service - Experiment tracking and lineage management.

Provides centralized experiment tracking, model registry integration, and
lineage tracking connecting training runs to deployed models.
"""

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, recall_score, precision_score, f1_score

logger = logging.getLogger(__name__)


class MLflowExperimentTracker:
    """Manages MLflow experiment tracking and versioning."""

    def __init__(
        self,
        tracking_uri: Optional[str] = None,
        experiment_name: str = "churn_prediction",
        registry_uri: Optional[str] = None,
    ):
        """
        Initialize MLflow tracker.

        Args:
            tracking_uri: MLflow tracking server URI (default: local backend/mlruns)
            experiment_name: Experiment name to track
            registry_uri: Model registry backend (default: same as tracking)
        """
        # Set tracking URI
        if tracking_uri is None:
            tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "file:backend/mlruns")
        
        self.tracking_uri = tracking_uri
        mlflow.set_tracking_uri(tracking_uri)

        # Set registry URI (defaults to tracking URI)
        if registry_uri:
            os.environ["MLFLOW_BACKEND_STORE_URI"] = registry_uri

        # Get or create experiment
        self.client = MlflowClient(tracking_uri=tracking_uri)
        self.experiment_name = experiment_name
        
        try:
            self.experiment_id = self.client.get_experiment_by_name(experiment_name).experiment_id
        except AttributeError:
            # Experiment doesn't exist, create it
            self.experiment_id = self.client.create_experiment(experiment_name)

        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow tracker initialized: {experiment_name} (ID: {self.experiment_id})")

    @contextmanager
    def tracking_run(
        self,
        run_name: Optional[str] = None,
        run_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        Context manager for MLflow run tracking.

        Usage:
            with tracker.tracking_run(run_name="baseline_v1") as run:
                mlflow.log_params({"lr": 0.1})
                mlflow.log_metrics({"auc": 0.89})
        """
        with mlflow.start_run(
            experiment_id=self.experiment_id,
            run_name=run_name,
            run_id=run_id,
        ) as run:
            if tags:
                mlflow.set_tags(tags)
            
            logger.info(f"Started MLflow run: {run.info.run_id}")
            try:
                yield run
            except Exception as e:
                logger.error(f"Error in MLflow run {run.info.run_id}: {e}")
                raise
            finally:
                logger.info(f"Completed MLflow run: {run.info.run_id}")

    def log_training_config(
        self,
        model_type: str,
        model_params: Dict[str, Any],
        training_data_version: str,
        preprocessing_version: str,
        test_size: float = 0.2,
        random_state: int = 42,
    ):
        """Log training configuration as parameters."""
        mlflow.log_params({
            "model_type": model_type,
            "training_data_version": training_data_version,
            "preprocessing_version": preprocessing_version,
            "test_size": test_size,
            "random_state": random_state,
            **{f"param_{k}": str(v) for k, v in model_params.items()},
        })

    def log_dataset_stats(
        self,
        df: pd.DataFrame,
        dataset_name: str = "train",
    ):
        """Log dataset statistics."""
        stats = {
            f"{dataset_name}_n_samples": len(df),
            f"{dataset_name}_n_features": len(df.columns),
            f"{dataset_name}_missing_pct": float(df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100),
        }
        
        # Class distribution for target column if present
        if "target" in df.columns or "Churn" in df.columns:
            target_col = "target" if "target" in df.columns else "Churn"
            class_dist = df[target_col].value_counts()
            stats[f"{dataset_name}_class_0_count"] = int(class_dist.get(0, 0))
            stats[f"{dataset_name}_class_1_count"] = int(class_dist.get(1, 0))

        mlflow.log_metrics(stats)
        logger.info(f"Logged {dataset_name} stats: {stats}")

    def log_metrics(
        self,
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        y_pred_binary: np.ndarray,
        stage: str = "test",
    ):
        """Log classification metrics."""
        metrics = {
            f"{stage}_auc": float(roc_auc_score(y_true, y_pred_proba)),
            f"{stage}_recall": float(recall_score(y_true, y_pred_binary, zero_division=0)),
            f"{stage}_precision": float(precision_score(y_true, y_pred_binary, zero_division=0)),
            f"{stage}_f1": float(f1_score(y_true, y_pred_binary, zero_division=0)),
        }
        
        mlflow.log_metrics(metrics)
        logger.info(f"Logged {stage} metrics: {metrics}")
        return metrics

    def log_confusion_matrix(
        self,
        y_true: np.ndarray,
        y_pred_binary: np.ndarray,
        stage: str = "test",
    ):
        """Log confusion matrix as artifact."""
        from sklearn.metrics import confusion_matrix
        cm = confusion_matrix(y_true, y_pred_binary)
        
        cm_dict = {
            "true_negatives": int(cm[0, 0]),
            "false_positives": int(cm[0, 1]),
            "false_negatives": int(cm[1, 0]),
            "true_positives": int(cm[1, 1]),
        }

        temp_dir = Path(tempfile.gettempdir())
        artifact_path = temp_dir / f"{stage}_confusion_matrix.json"
        with artifact_path.open("w", encoding="utf-8") as f:
            json.dump(cm_dict, f)

        mlflow.log_artifact(str(artifact_path))
        logger.info(f"Logged {stage} confusion matrix")

    def log_feature_importance(
        self,
        model,
        feature_names: List[str],
        n_top: int = 20,
    ):
        """Log feature importance from tree-based model (e.g., CatBoost)."""
        try:
            importances = model.get_feature_importance()
            
            # Create ranking
            feature_importance_dict = {
                name: float(imp)
                for name, imp in sorted(
                    zip(feature_names, importances),
                    key=lambda x: x[1],
                    reverse=True,
                )[:n_top]
            }
            
            temp_dir = Path(tempfile.gettempdir())
            artifact_path = temp_dir / "feature_importance.json"
            with artifact_path.open("w", encoding="utf-8") as f:
                json.dump(feature_importance_dict, f, indent=2)

            mlflow.log_artifact(str(artifact_path))
            
            # Log top 5 as metrics
            for i, (name, imp) in enumerate(list(feature_importance_dict.items())[:5]):
                mlflow.log_metric(f"feature_importance_rank_{i+1}", imp)
            
            logger.info(f"Logged feature importance (top {n_top})")
        except Exception as e:
            logger.warning(f"Could not extract feature importance: {e}")

    def log_model_artifact(
        self,
        model_path: Path,
        model_name: str = "churn_model",
    ):
        """Log trained model artifact."""
        if isinstance(model_path, str):
            model_path = Path(model_path)
        
        mlflow.log_artifact(str(model_path), artifact_path="models")
        logger.info(f"Logged model artifact: {model_path}")

    def register_model(
        self,
        model_uri: str,
        model_name: str = "churn_predictor",
        version_description: str = "",
    ) -> str:
        """
        Register model in MLflow Model Registry.

        Args:
            model_uri: URI to logged model (e.g., "runs:/run_id/model")
            model_name: Name in model registry
            version_description: Version description

        Returns:
            Model version (e.g., "1", "2")
        """
        model_version = mlflow.register_model(
            model_uri=model_uri,
            name=model_name,
            await_registration_for=300,
        )
        
        if version_description:
            self.client.update_model_version(
                name=model_name,
                version=model_version.version,
                description=version_description,
            )
        
        logger.info(f"Registered model {model_name} version {model_version.version}")
        return model_version.version

    def transition_model_stage(
        self,
        model_name: str,
        version: str,
        stage: str,  # "Staging", "Production", "Archived"
    ):
        """Transition model to new stage."""
        self.client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage=stage,
        )
        logger.info(f"Transitioned {model_name} v{version} to {stage}")

    def create_lineage_record(
        self,
        run_id: str,
        model_version: str,
        pipeline_bundle_path: Path,
        evaluation_metrics: Dict[str, float],
        validation_report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Create lineage record connecting training run to deployed model.

        Args:
            run_id: MLflow run ID
            model_version: Deployed model version
            pipeline_bundle_path: Path to pipeline bundle artifact
            evaluation_metrics: Dictionary of evaluation metrics
            validation_report_path: Path to validation gate report

        Returns:
            Lineage record dictionary
        """
        lineage_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "mlflow_run_id": run_id,
            "mlflow_experiment_id": self.experiment_id,
            "deployed_model_version": model_version,
            "pipeline_bundle_path": str(pipeline_bundle_path),
            "evaluation_metrics": evaluation_metrics,
            "validation_report_path": str(validation_report_path) if validation_report_path else None,
        }
        
        # Log as artifact
        temp_dir = Path(tempfile.gettempdir())
        artifact_path = temp_dir / "lineage_record.json"
        with artifact_path.open("w", encoding="utf-8") as f:
            json.dump(lineage_record, f, indent=2)

        mlflow.log_artifact(str(artifact_path))
        logger.info(f"Created lineage record for model {model_version}")
        
        return lineage_record

    def get_experiment_runs(
        self,
        order_by: Optional[str] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get recent runs from experiment.

        Args:
            order_by: Sort order (e.g., "metrics.auc DESC")
            max_results: Maximum number of results

        Returns:
            List of run dictionaries
        """
        runs = self.client.search_runs(
            experiment_ids=[self.experiment_id],
            order_by=[order_by or "start_time DESC"],
            max_results=max_results,
        )
        
        return [
            {
                "run_id": run.info.run_id,
                "run_name": run.info.run_name,
                "status": run.info.status,
                "metrics": run.data.metrics,
                "params": run.data.params,
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
            }
            for run in runs
        ]

    def compare_runs(self, run_ids: List[str]) -> pd.DataFrame:
        """
        Compare metrics and params across runs.

        Returns:
            DataFrame with runs as rows and metrics/params as columns
        """
        runs = [self.client.get_run(run_id) for run_id in run_ids]
        
        comparison_data = []
        for run in runs:
            row = {
                "run_id": run.info.run_id,
                "run_name": run.info.run_name,
                **run.data.metrics,
                **{f"param_{k}": v for k, v in run.data.params.items()},
            }
            comparison_data.append(row)
        
        return pd.DataFrame(comparison_data)

    def export_experiment_summary(self, output_path: Path):
        """Export experiment summary for reporting."""
        runs = self.get_experiment_runs(max_results=100)
        
        summary = {
            "experiment_name": self.experiment_name,
            "experiment_id": self.experiment_id,
            "total_runs": len(runs),
            "runs": runs,
            "exported_at": datetime.utcnow().isoformat(),
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Exported experiment summary to {output_path}")


# Convenience functions for notebook integration

def start_mlflow_run(
    experiment_name: str = "churn_prediction",
    run_name: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
):
    """Start MLflow run (convenience for notebooks)."""
    mlflow.set_experiment(experiment_name)
    return mlflow.start_run(run_name=run_name)


def log_training_metrics(
    y_train_true: np.ndarray,
    y_train_pred_proba: np.ndarray,
    y_train_pred_binary: np.ndarray,
    y_test_true: np.ndarray,
    y_test_pred_proba: np.ndarray,
    y_test_pred_binary: np.ndarray,
):
    """Log train and test metrics."""
    tracker = MLflowExperimentTracker()
    
    train_metrics = tracker.log_metrics(
        y_train_true, y_train_pred_proba, y_train_pred_binary, "train"
    )
    test_metrics = tracker.log_metrics(
        y_test_true, y_test_pred_proba, y_test_pred_binary, "test"
    )
    
    return train_metrics, test_metrics


def log_cross_validation_results(fold_results: List[Dict[str, float]]):
    """Log cross-validation results."""
    avg_auc = np.mean([r.get("auc", 0) for r in fold_results])
    avg_f1 = np.mean([r.get("f1", 0) for r in fold_results])
    
    mlflow.log_metrics({
        "cv_avg_auc": avg_auc,
        "cv_avg_f1": avg_f1,
        "cv_n_folds": len(fold_results),
    })


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example usage
    tracker = MLflowExperimentTracker(experiment_name="churn_test")

    with tracker.tracking_run(
        run_name="baseline_v1",
        tags={"team": "ml", "environment": "dev"}
    ) as run:
        # Log config
        tracker.log_training_config(
            model_type="CatBoost",
            model_params={"depth": 6, "iterations": 100},
            training_data_version="dvc://v1.0.0",
            preprocessing_version="v1.0.0",
        )

        # Log metrics
        y_true = np.array([0, 1, 0, 1, 1, 0])
        y_pred_proba = np.array([0.1, 0.9, 0.2, 0.8, 0.85, 0.15])
        y_pred_binary = (y_pred_proba >= 0.5).astype(int)

        tracker.log_metrics(y_true, y_pred_proba, y_pred_binary, "test")
        print(f"Run ID: {run.info.run_id}")

    # Get recent runs
    recent_runs = tracker.get_experiment_runs(max_results=5)
    print(f"Recent runs: {recent_runs}")
