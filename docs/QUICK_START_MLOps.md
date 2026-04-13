# Quick Start: Integrated MLOps Workflow

## Using Validation Gates, MLflow, and Drift Detection Together

---

## Setup (5 minutes)

### 1. Install Dependencies

```bash
cd g:\23881A66E2\Projects\Customer_Churn_Predictor
pip install -r backend/requirements.txt
```

### 2. Create Configuration File

**`backend/config/monitoring.yml`**:

```yaml
mlflow:
  tracking_uri: file:backend/mlruns
  experiment_name: churn_prediction

validation:
  model_quality:
    min_auc: 0.75
    min_recall: 0.65
  fairness:
    demographic_parity_tolerance: 0.10
  performance:
    max_api_latency_ms: 6000

monitoring:
  drift_threshold: 0.05
  retraining_trigger_features: 3

alerts:
  channels:
    webhook:
      type: webhook
      webhook_url: http://localhost:8000/webhooks/alerts
```

---

## Complete Training → Validation → Monitoring Pipeline

### Step 1: Train Model with MLflow Tracking

```python
from backend.services.mlflow_tracker import MLflowExperimentTracker
from pathlib import Path
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier

# Initialize tracker
tracker = MLflowExperimentTracker(experiment_name="churn_prediction")

# Start tracked run
with tracker.tracking_run(run_name="exp_baseline_v1") as run:
    # Load and prepare data
    df = pd.read_csv("data/Telco-Customer-Churn.csv")
    # ... preprocessing ...

    # Log configuration
    tracker.log_training_config(
        model_type="CatBoost",
        model_params={"depth": 6, "iterations": 100},
        training_data_version="dvc://churn/v1.2.0",
        preprocessing_version="v1.0.0",
    )

    tracker.log_dataset_stats(X_train, "train")
    tracker.log_dataset_stats(X_test, "test")

    # Train model
    model = CatBoostClassifier(**model_params)
    model.fit(X_train, y_train, verbose=False)

    # Get predictions
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred_binary = model.predict(X_test)

    # Log metrics
    metrics = tracker.log_metrics(y_test, y_pred_proba, y_pred_binary, "test")

    # Save model
    model_path = Path("model/artifacts/catboost_churn.cbm")
    model.save_model(str(model_path))
    tracker.log_model_artifact(model_path)

    print(f"✓ Training complete (Run ID: {run.info.run_id})")
    print(f"  Test AUC: {metrics['test_auc']:.4f}")
```

### Step 2: Run Validation Gates

```python
from backend.services.model_validation_service import ModelValidationGate
from backend.services.model_registry_service import ModelRegistryService, ModelStage

# Initialize validator
validator = ModelValidationGate()

# Run validation
validation_report = validator.validate_for_promotion(
    model_version="v1.3.0",
    y_true=y_test,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    protected_attribute=X_test["contract_type"].map({...}).values,
    latency_measurements={
        "preprocess_ms": 800,
        "model_predict_ms": 1500,
        "api_e2e_ms": 3200,
    },
    memory_mb=250,
    test_df=X_test,
    expected_columns=list(X_test.columns),
    expected_dtypes={col: str(X_test[col].dtype) for col in X_test.columns},
)

print(f"✓ Validation Report:")
print(f"  Status: {validation_report.overall_status}")
print(f"  Passed: {validation_report.passed_checks}/{validation_report.total_checks}")

if validation_report.promotion_allowed:
    print(f"  ✓ Ready for promotion!")
else:
    print(f"  ✗ Blockers:")
    for blocker in validation_report.blockers:
        print(f"    - {blocker}")
```

### Step 3: Request Promotion (with Integration)

```python
# Initialize registry
registry = ModelRegistryService()

# Request promotion (includes validation)
promo_record = registry.request_promotion(
    model_version="v1.3.0",
    from_stage=ModelStage.CANDIDATE,
    to_stage=ModelStage.SHADOW,
    y_true=y_test,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    latency_measurements=latency_measurements,
    promoted_by=f"mlflow_run:{run.info.run_id}",
    notes="Baseline model with feature engineering",
)

print(f"Promotion Status: {promo_record.status}")
print(f"Validation Passed: {promo_record.validation_passed}")

# If approved, execute promotion
if promo_record.validation_passed:
    success = registry.approve_promotion(
        model_version="v1.3.0",
        from_stage=ModelStage.CANDIDATE,
        to_stage=ModelStage.SHADOW,
    )
    print(f"✓ Model promoted to shadow: {success}")

# Create lineage record
lineage = tracker.create_lineage_record(
    run_id=run.info.run_id,
    model_version="v1.3.0",
    pipeline_bundle_path=Path("model/artifacts/bundles/churn_pipeline_v1.3.0.zip"),
    evaluation_metrics=metrics,
    validation_report_path=Path(promo_record.validation_report_path),
)
print(f"✓ Lineage recorded in MLflow")
```

### Step 4: Setup Drift Monitoring

```python
from backend.services.drift_detector import EvidentiallyDriftDetector
from backend.services.alert_router import (
    AlertRouter, AlertSeverity, SlackAlertChannel, create_router_from_config
)

# Initialize detector with training data as reference
detector = EvidentiallyDriftDetector(
    reference_data=X_train,
    feature_names=list(X_train.columns),
    numerical_features=X_train.select_dtypes(include=['float64', 'int64']).columns.tolist(),
    drift_threshold=0.05,
)

# Setup alert routing
alert_config = {
    "channels": {
        "slack": {
            "type": "slack",
            "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
            "channel": "#ml-alerts",
        }
    },
    "severity_rules": {
        "critical": ["slack"],
        "high": ["slack"],
        "medium": [],
        "low": [],
        "info": [],
    },
}

router = create_router_from_config(alert_config)
```

### Step 5: Monitor Production Data (Scheduled Job)

```python
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

scheduler = BackgroundScheduler()

def monitor_drift():
    """Run drift detection job every 12 hours."""
    print(f"\n[{datetime.now()}] Running drift detection...")

    # Load production data (last 24 hours)
    production_data = load_production_data(hours=24)

    # Detect data drift
    data_drift_report = detector.detect_data_drift(production_data)

    # Detect performance drift
    y_train_pred = model.predict_proba(X_train)[:, 1]
    perf_drift_report = detector.detect_performance_drift(
        production_data=production_data,
        y_true=Y_production_true,  # From logged feedback
        y_pred_proba=Y_production_pred,
        y_pred_binary=Y_production_binary,
        reference_auc=metrics['test_auc'],
    )

    # Alert on findings
    if data_drift_report.alerts_severity in ["critical", "high"]:
        router.send_alert(
            title="Data Drift Detected",
            message=f"{len(data_drift_report.drifted_features)} features show drift",
            severity=AlertSeverity.HIGH,
            details={
                "drifted_features": ", ".join(data_drift_report.drifted_features),
                "severity": data_drift_report.alerts_severity,
                "report_id": data_drift_report.report_id,
            },
        )

        # Trigger retraining if needed
        if detector.should_retrain(data_drift_report):
            print("⚠ Retraining recommended!")
            # Queue retraining pipeline...

    if perf_drift_report.drifted_features:
        router.send_alert(
            title="Performance Drift Detected",
            message=f"Model AUC dropped from {perf_drift_report.metrics['reference_auc']:.4f} to {perf_drift_report.metrics['production_auc']:.4f}",
            severity=AlertSeverity.CRITICAL,
            details=perf_drift_report.metrics,
        )

    # Save reports
    detector.save_report(data_drift_report, Path("backend/data/drift_reports"))

# Schedule job
scheduler.add_job(monitor_drift, "interval", hours=12)
scheduler.start()
```

---

## Quick Reference Commands

### View MLflow Experiments

```bash
mlflow ui --backend-store-uri=file:backend/mlruns --port 5000
# Visit: http://localhost:5000
```

### Run All Tests

```bash
pytest backend/tests/test_model_validation_service.py -v
pytest backend/tests/test_mlflow_tracker.py -v
pytest backend/tests/test_drift_detection.py -v
```

### Generate Drift Report

```python
from backend.services.drift_detector import EvidentiallyDriftDetector
from pathlib import Path

detector = EvidentiallyDriftDetector(reference_data=train_data)
report = detector.detect_data_drift(production_data)
detector.save_report(report, Path("backend/data/drift_reports"))

# View report at: backend/data/drift_reports/{report_id}.json
```

### Check Promotion Status

```python
registry = ModelRegistryService()
status = registry.get_promotion_status(
    model_version="v1.3.0",
    from_stage=ModelStage.CANDIDATE,
    to_stage=ModelStage.SHADOW,
)
print(status.to_dict())
```

### Export Experiment Summary

```python
tracker = MLflowExperimentTracker()
tracker.export_experiment_summary(Path("reports/experiment_summary.json"))
```

---

## Typical Workflow (Day-to-Day)

### Morning: Check Monitoring Dashboard

```python
# Query recent drift alerts
history = detector.get_drift_history(days=1)
for event in history:
    if event.alerts_severity == "critical":
        print(f"🚨 {event.timestamp}: {event.alerts}")
```

### Mid-Day: Train New Model

```bash
# Run training notebook with MLflow integration
jupyter notebook model/training/training.ipynb
```

### Afternoon: Review Results

```python
# Compare today's run with baseline
runs = tracker.get_experiment_runs(max_results=10)
comparison = tracker.compare_runs([runs[0]['run_id'], runs[1]['run_id']])
print(comparison[['run_name', 'test_auc', 'test_f1']])
```

### Evening: One-Click Evaluation & Deployment

```python
# Script handles: train → validate → promote → notify
python scripts/train_and_promote.py --model-version v1.4.0
```

---

## Integration Points

```
Training (Notebook)
       ↓
    MLflow Tracking
       ↓
   Validation Gates
       ↓
   Model Registry
    (Promotion)
       ↓
  Production API
       ↓
   Drift Detection
       ↓
   Alert Router
    (Slack/Email/PagerDuty)
       ↓
  Human Decision
   (Retrain/Rollback)
```

---

## Troubleshooting

### Validation Gates Failing?

1. Check `validation_gates_guide.md` for threshold tuning
2. Review specific blocker messages
3. Inspect validation report JSON

### MLflow Connection Issues?

1. Verify tracking URI: `mlflow.get_tracking_uri()`
2. Check backend/mlruns directory exists
3. Restart MLflow UI if needed

### Drift Alerts Not Arriving?

1. Test webhook: `curl -X POST http://webhook-url -d '{"test": true}'`
2. Check Slack/Email credentials in config
3. Verify severity routing is configured

---

## Next Steps

1. **Customize Thresholds**: Adjust validation/drift thresholds for your business
2. **Connect to Slack**: Update webhook URL in alert config
3. **Schedule Monitoring**: Deploy drift detection as scheduled service
4. **Add Retraining**: Link drift alerts to automatic retraining pipeline
5. **Production Deployment**: Set up canary testing before full rollout

---

## Reference Documentation

- [Validation Gates Guide](../validation_gates_guide.md)
- [MLflow Integration Guide](../mlflow_integration_guide.md)
- [Implementation Tracker](./mlops_implementation_tracker.md)
- [Session Summary](./SESSION_SUMMARY_20260413.md)
