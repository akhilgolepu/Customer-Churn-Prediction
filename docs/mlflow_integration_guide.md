# MLflow Integration Guide

## Overview

MLflow provides experiment tracking, model registry, and lineage management. This integration connects training runs to deployed models and enables reproducible ML workflows.

## Quick Start

### 1. Basic Training with MLflow

```python
from backend.services.mlflow_tracker import MLflowExperimentTracker
import numpy as np

tracker = MLflowExperimentTracker(experiment_name="churn_prediction")

with tracker.tracking_run(run_name="baseline_v1") as run:
    # Log configuration
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

    metrics = tracker.log_metrics(y_true, y_pred_proba, y_pred_binary, "test")
    print(f"AUC: {metrics['test_auc']:.4f}")

    print(f"Run ID: {run.info.run_id}")
```

### 2. Integration with Model Registry

```python
from backend.services.model_registry_service import ModelRegistryService, ModelStage
from pathlib import Path

tracker = MLflowExperimentTracker(experiment_name="churn_prediction")
registry = ModelRegistryService()

with tracker.tracking_run(run_name="prod_candidate_v2") as run:
    # ... training code ...

    # Log model artifact
    tracker.log_model_artifact(Path("model/artifacts/catboost_churn.cbm"))

    # Create validation report
    validation_report = "backend/data/validation_reports/validation_v2_2026-04-13.json"

    # Request promotion with validation
    promo_record = registry.request_promotion(
        model_version="v2",
        from_stage=ModelStage.CANDIDATE,
        to_stage=ModelStage.SHADOW,
        y_true=y_true,
        y_pred_proba=y_pred_proba,
        y_pred_binary=y_pred_binary,
        promoted_by=f"mlflow_run:{run.info.run_id}",
    )

    # If promotion approved, create lineage record
    if promo_record.validation_passed:
        lineage = tracker.create_lineage_record(
            run_id=run.info.run_id,
            model_version="v2",
            pipeline_bundle_path=Path("model/artifacts/bundles/churn_pipeline_v2.zip"),
            evaluation_metrics=tracker.log_metrics(...),
            validation_report_path=Path(validation_report),
        )
```

## Architecture

### Tracking Components

```
MLflow Backend
├── Experiments (e.g., "churn_prediction")
│   └── Runs (training executions)
│       ├── Parameters (model config, data versions)
│       ├── Metrics (AUC, F1, etc.)
│       ├── Artifacts (models, confusion matrices, reports)
│       └── Tags (stage, team, environment)
│
└── Model Registry
    └── Registered Models (e.g., "churn_predictor")
        └── Versions (v1, v2, v3...)
            └── Stages (Staging, Production, Archived)
```

### Storage Modes

**Local Development** (default):

```python
tracker = MLflowExperimentTracker(
    tracking_uri="file:backend/mlruns"
)
```

**Remote Tracking Server**:

```python
tracker = MLflowExperimentTracker(
    tracking_uri="http://mlflow-server.example.com:5000"
)
```

**Managed Service** (AWS/Azure):

```python
tracker = MLflowExperimentTracker(
    tracking_uri="https://aws-mlflow.example.com",
    registry_uri="postgresql://user:pass@db.example.com/mlflow"
)
```

## Logging Operations

### Configuration

```python
tracker.log_training_config(
    model_type="CatBoost",
    model_params={
        "depth": 6,
        "iterations": 100,
        "learning_rate": 0.1,
    },
    training_data_version="dvc://churn/v1.2.0",
    preprocessing_version="v1.0.0",
    test_size=0.2,
    random_state=42,
)
```

Logged as parameters (searchable, comparable):

- `model_type`: CatBoost
- `param_depth`: 6
- `param_iterations`: 100
- `training_data_version`: dvc://churn/v1.2.0

### Dataset Statistics

```python
import pandas as pd

train_df = pd.read_csv("data/train.csv")
test_df = pd.read_csv("data/test.csv")

tracker.log_dataset_stats(train_df, "train")
tracker.log_dataset_stats(test_df, "test")
```

Logged metrics:

- `train_n_samples`: 4000
- `train_n_features`: 15
- `train_missing_pct`: 0.05
- `train_class_0_count`: 2800
- `train_class_1_count`: 1200

### Performance Metrics

```python
import numpy as np
from sklearn.metrics import roc_auc_score, recall_score

y_test = np.array([...])
y_pred_proba = model.predict_proba(X_test)[:, 1]
y_pred_binary = (y_pred_proba >= 0.5).astype(int)

metrics = tracker.log_metrics(
    y_test, y_pred_proba, y_pred_binary, "test"
)

# Logged metrics:
# test_auc, test_recall, test_precision, test_f1
```

### Confusion Matrix

```python
tracker.log_confusion_matrix(y_test, y_pred_binary, "test")

# Saved as artifact: test_confusion_matrix.json
# {
#   "true_negatives": 1840,
#   "false_positives": 120,
#   "false_negatives": 180,
#   "true_positives": 860
# }
```

### Feature Importance

```python
feature_names = model.feature_names_
tracker.log_feature_importance(model, feature_names, n_top=20)

# Logs:
# - artifact: feature_importance.json (top 20 features ranked)
# - metrics: feature_importance_rank_1..5
```

### Model Artifacts

```python
from pathlib import Path

tracker.log_model_artifact(
    Path("model/artifacts/catboost_churn.cbm"),
    model_name="catboost_model"
)

# Artifact saved to MLflow backend
```

## Experiment Comparison

### Query Runs

```python
# Get last 50 runs, sorted by AUC descending
runs = tracker.get_experiment_runs(
    order_by="metrics.test_auc DESC",
    max_results=50
)

for run in runs:
    print(f"{run['run_name']}: AUC={run['metrics'].get('test_auc', 'N/A')}")
```

### Compare Runs Side-by-Side

```python
run_ids = ["run_id_1", "run_id_2", "run_id_3"]
comparison_df = tracker.compare_runs(run_ids)

print(comparison_df[["run_name", "test_auc", "test_f1", "param_depth"]])
```

Output:

```
                run_name  test_auc  test_f1  param_depth
0           baseline_v1      0.81     0.70            4
1           baseline_v2      0.85     0.74            6
2     with_feature_eng      0.89     0.78            8
```

## Model Registry Integration

### Register Model

```python
with tracker.tracking_run(run_name="prod_candidate") as run:
    # ... training ...

    model_version = tracker.register_model(
        model_uri="runs:/{}/model".format(run.info.run_id),
        model_name="churn_predictor",
        version_description="Added feature engineering for TotalServices",
    )

    print(f"Registered model version: {model_version}")
```

### Transition to Staging

```python
tracker.transition_model_stage(
    model_name="churn_predictor",
    version="1",
    stage="Staging",  # Queue for testing
)
```

### Graduate to Production

```python
tracker.transition_model_stage(
    model_name="churn_predictor",
    version="1",
    stage="Production",  # Live to users
)
```

### Archive Old Versions

```python
tracker.transition_model_stage(
    model_name="churn_predictor",
    version="0",
    stage="Archived",  # Deprecated
)
```

## Lineage Tracking

### Create Lineage Record

```python
lineage = tracker.create_lineage_record(
    run_id=run.info.run_id,
    model_version="v1.2.0",
    pipeline_bundle_path=Path("model/artifacts/bundles/churn_pipeline_v1.2.0.zip"),
    evaluation_metrics={
        "test_auc": 0.89,
        "test_f1": 0.78,
        "test_recall": 0.82,
    },
    validation_report_path=Path("backend/data/validation_reports/validation_v1.2.0.json"),
)

# Artifact lineage_record.json saved to MLflow
```

### Export Experiment Summary

```python
from pathlib import Path

tracker.export_experiment_summary(
    Path("reports/experiment_summary_2026_q2.json")
)

# JSON includes:
# - Experiment metadata
# - All runs with params/metrics
# - Export timestamp
```

## Notebook Integration

### Training Notebook (model/training/training.ipynb)

```python
# Cell 1: Setup
from backend.services.mlflow_tracker import MLflowExperimentTracker
from backend.services.model_validation_service import ModelValidationGate
from backend.services.model_registry_service import ModelRegistryService, ModelStage

tracker = MLflowExperimentTracker(experiment_name="churn_prediction")
validator = ModelValidationGate()
registry = ModelRegistryService()

# Cell 2: Load and prepare data
import pandas as pd
df = pd.read_csv("data/Telco-Customer-Churn.csv")
# ... data preparation ...

# Cell 3: Start MLflow run
with tracker.tracking_run(run_name=f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}") as run:
    tracker.log_training_config(
        model_type="CatBoost",
        model_params=model_params,
        training_data_version=f"dvc://{dvc_version}",
        preprocessing_version="v1.0.0",
    )

    tracker.log_dataset_stats(train_df, "train")
    tracker.log_dataset_stats(test_df, "test")

    # Cell 4: Train model
    model = CatBoostClassifier(**model_params)
    model.fit(X_train, y_train, verbose=False)

    # Cell 5: Evaluate
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred_binary = model.predict(X_test)

    metrics = tracker.log_metrics(y_test, y_pred_proba, y_pred_binary, "test")
    tracker.log_confusion_matrix(y_test, y_pred_binary, "test")
    tracker.log_feature_importance(model, feature_names)

    # Cell 6: Validate and register
    validation_report = validator.validate_for_promotion(
        model_version="v1.3.0",
        y_true=y_test,
        y_pred_proba=y_pred_proba,
        y_pred_binary=y_pred_binary,
    )

    if validation_report.promotion_allowed:
        model.save_model("model/artifacts/catboost_churn.cbm")
        tracker.log_model_artifact(Path("model/artifacts/catboost_churn.cbm"))

        # Request promotion
        promo = registry.request_promotion(
            model_version="v1.3.0",
            from_stage=ModelStage.CANDIDATE,
            to_stage=ModelStage.SHADOW,
            y_true=y_test,
            y_pred_proba=y_pred_proba,
            y_pred_binary=y_pred_binary,
            promoted_by=f"notebook_run:{run.info.run_id}",
        )
    else:
        print(f"Validation failed: {validation_report.blockers}")
```

## MLflow UI

### Start UI (local development)

```bash
mlflow ui --backend-store-uri=file:backend/mlruns --port 5000
```

Then visit: http://localhost:5000

### Features

- Browse all experiments and runs
- Compare metrics/params across runs
- Search runs by tag, metric range
- View model registry and versions
- Download artifacts

## Best Practices

### 1. Tag Your Runs

```python
with tracker.tracking_run(
    run_name="exp_001",
    tags={
        "team": "ml",
        "environment": "dev",
        "dataset": "telco_churn",
        "split": "80/20",
        "validation_version": "v1.0",
    }
):
    # ... training ...
```

### 2. Store Data Versions

```python
tracker.log_training_config(
    training_data_version="dvc://churn/v1.2.0",  # Reproducible via DVC
    preprocessing_version="v1.0.0",  # Git tag
)
```

### 3. Link to External Systems

```python
tracker.create_lineage_record(
    run_id=run.info.run_id,
    model_version="v1.2.0",
    pipeline_bundle_path=Path(...),  # CI/CD output
    evaluation_metrics=metrics,
    validation_report_path=Path(...),  # Validation gate output
)
```

### 4. Automatic Promotion Workflow

```python
# CI/CD Pipeline
promo_record = registry.request_promotion(
    model_version=model_version,
    from_stage=ModelStage.CANDIDATE,
    to_stage=ModelStage.SHADOW,
    promoted_by="ci_pipeline",
    notes=f"Auto-promoted from GitHub Actions workflow {github_run_id}",
)

if promo_record.validation_passed:
    registry.approve_promotion(model_version=model_version, ...)
else:
    logger.error(f"Promotion blocked: {promo_record.blockers}")
```

## Troubleshooting

### MLflow Server Connection Issues

```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
print(mlflow.get_tracking_uri())  # Verify connection
```

### Large Artifacts

For large models (>500MB), use object storage backends:

```
# backend/mlruns/.env
MLFLOW_BACKEND_STORE_URI=postgresql://user:pass@db:5432/mlflow
MLFLOW_DEFAULT_ARTIFACT_ROOT=s3://my-bucket/mlflow-artifacts
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

### Memory Issues (Too Many Runs)

```python
# Clean up old runs periodically
from mlflow.tracking import MlflowClient
client = MlflowClient()

# Archive runs older than 30 days
import time
cutoff_time = int((time.time() - 30*86400) * 1000)
for run in client.search_runs(experiment_ids=[exp_id]):
    if run.info.start_time < cutoff_time:
        client.delete_run(run.info.run_id)
```

## See Also

- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Model Registry](../backend/services/model_registry_service.py)
- [Validation Gates](validation_gates_guide.md)
- [Training Notebook](../model/training/training.ipynb)
