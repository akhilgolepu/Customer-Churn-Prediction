# Model Validation Gate Integration Guide

## Overview

The model validation gate service provides a comprehensive pre-promotion quality assurance system. All models must pass strict validation gates before promotion to shadow or active stages.

## Quick Start

### 1. Run Validation on a Candidate Model

```python
from backend.services.model_validation_service import ModelValidationGate
import numpy as np
import pandas as pd

# Initialize gate
gate = ModelValidationGate()

# Prepare evaluation data
y_true = np.array([0, 1, 0, 1, ...])  # Ground truth
y_pred_proba = model.predict_proba(X_test)[:, 1]  # Probabilities
y_pred_binary = (y_pred_proba >= 0.5).astype(int)  # Binary predictions

# Run validation
report = gate.validate_for_promotion(
    model_version="v1.2.3",
    y_true=y_true,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    latency_measurements={
        "model_predict_ms": 1500.0,
        "preprocess_ms": 800.0,
    },
    memory_mb=250.0,
)

print(f"Promotion allowed: {report.promotion_allowed}")
if not report.promotion_allowed:
    print(f"Blockers: {report.blockers}")
```

### 2. With Fairness Checks

```python
# Include protected attributes for fairness evaluation
protected_attr = test_data["contract_type"].map({"Month-to-month": 0, "One year": 1, "Two year": 1}).values

report = gate.validate_for_promotion(
    model_version="v1.2.3",
    y_true=y_true,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    protected_attribute=protected_attr,
    latency_measurements={"model_predict_ms": 1500.0, "preprocess_ms": 800.0},
    memory_mb=250.0,
)
```

### 3. With Data Integrity Checks

```python
# Include test data for schema and missing data validation
expected_columns = ["feature_1", "feature_2", "feature_3", "target"]
expected_dtypes = {
    "feature_1": "float",
    "feature_2": "float",
    "feature_3": "int",
    "target": "int",
}

report = gate.validate_for_promotion(
    model_version="v1.2.3",
    y_true=y_true,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    test_df=test_data,
    expected_columns=expected_columns,
    expected_dtypes=expected_dtypes,
    latency_measurements={"model_predict_ms": 1500.0},
    memory_mb=250.0,
)
```

## Validation Check Categories

### 1. Model Quality (`quality`)

Validates binary classification performance:

| Check           | Default Threshold | Purpose                                                     |
| --------------- | ----------------- | ----------------------------------------------------------- |
| ROC AUC Score   | >= 0.75           | Overall discrimination ability                              |
| Recall Score    | >= 0.65           | Ability to catch churners (minimize false negatives)        |
| Precision Score | >= 0.50           | Accuracy of positive predictions (minimize false positives) |
| F1 Score        | >= 0.57           | Harmonic mean of precision and recall                       |

**Configuration**: Edit `ModelQualityValidator.config`

### 2. Fairness (`fairness`)

Validates demographic parity across protected groups:

| Check              | Default Tolerance | Purpose                                                   |
| ------------------ | ----------------- | --------------------------------------------------------- |
| Demographic Parity | +/- 10%           | Ensures positive prediction rate is similar across groups |

**Example**: If Group 0 has 60% positive prediction rate and Group 1 has 67%, difference is 7% (within tolerance).

**Configuration**: Edit `FairnessValidator.config`

### 3. Performance (`performance`)

Validates latency and memory usage:

| Check                   | Default Threshold     | Purpose                            |
| ----------------------- | --------------------- | ---------------------------------- |
| Latency (preprocess)    | < 2000ms              | Preprocessing performance budget   |
| Latency (model_predict) | < 2000ms              | Model inference performance budget |
| Latency (api_e2e)       | < 6000ms              | Total API response time budget     |
| Memory Usage            | < 500MB               | Peak memory footprint              |
| Throughput              | >= 10 predictions/sec | Minimum throughput                 |

**Configuration**: Edit `PerformanceValidator.config`

### 4. Data Integrity (`data_integrity`)

Validates data schema and quality:

| Check           | Default Threshold    | Purpose                       |
| --------------- | -------------------- | ----------------------------- |
| Column Presence | 100% of expected     | All required features present |
| Data Types      | Match expected types | Correct numpy/pandas dtypes   |
| Missing Data    | <= 1% per column     | Low missing value rate        |

**Configuration**: Edit `DataIntegrityValidator.config`

## Report Structure

```json
{
  "model_version": "v1.2.3",
  "timestamp": "2026-04-13T15:30:45.123456",
  "overall_status": "passed",
  "total_checks": 12,
  "passed_checks": 12,
  "failed_checks": 0,
  "warning_checks": 0,
  "checks": [
    {
      "name": "ROC AUC Score",
      "category": "quality",
      "status": "passed",
      "thresholds": { "min_auc": 0.75 },
      "expected": ">= 0.75",
      "actual": 0.789,
      "message": "AUC = 0.7890"
    }
  ],
  "blockers": [],
  "warnings": [],
  "promotion_allowed": true
}
```

## Interpreting Results

### Promotion Allowed (✓)

```
overall_status: "passed"
blockers: []
promotion_allowed: true
```

Model passes ALL quality gates and can proceed to promotion workflow.

### Promotion Blocked (✗)

```
overall_status: "failed"
blockers: [
  "Model quality metrics below thresholds",
  "Fairness check failed: demographic parity not achieved"
]
promotion_allowed: false
```

Model FAILS one or more hard gates. Cannot be promoted without manual override.

### Warnings (⚠)

```
overall_status: "passed"
warnings: [
  "Fairness warning: difference in positive rates = 9.8%"
],
promotion_allowed: true
```

Model passes gates but has advisory warnings. Promotion allowed with caution.

## Customizing Thresholds

```python
from backend.services.model_validation_service import ModelQualityValidator

# Lower AUC threshold for less-critical use case
validator = ModelQualityValidator()
validator.config["min_auc"] = 0.70
validator.config["min_recall"] = 0.60

# Higher fairness tolerance for balanced group sizes
fairness_validator = FairnessValidator()
fairness_validator.config["demographic_parity_tolerance"] = 0.15
```

## Measuring Performance

Use utility functions to capture metrics:

```python
from backend.services.model_validation_service import measure_latency, measure_memory_usage

# Measure preprocessing latency
preproc_result, preproc_latency_ms = measure_latency(
    preprocess,
    X
)

# Measure model inference memory
pred_result, peak_memory_mb = measure_memory_usage(
    model.predict_proba,
    X
)

# Use in validation
report = gate.validate_for_promotion(
    model_version="v1",
    y_pred_proba=pred_result,
    latency_measurements={
        "preprocess_ms": preproc_latency_ms,
        "model_predict_ms": ?,
    },
    memory_mb=peak_memory_mb,
)
```

## Integration with Model Registry

```python
from backend.services.model_registry_service import ModelRegistryService, ModelStage

registry = ModelRegistryService()

# Request promotion with validation
promo_record = registry.request_promotion(
    model_version="v1",
    from_stage=ModelStage.CANDIDATE,
    to_stage=ModelStage.SHADOW,
    y_true=y_true,
    y_pred_proba=y_pred_proba,
    y_pred_binary=y_pred_binary,
    promoted_by="training_pipeline@company.com",
    notes="Trained on Q2 2026 data",
)

if promo_record.validation_passed:
    # Approval
    success = registry.approve_promotion(
        model_version="v1",
        from_stage=ModelStage.CANDIDATE,
        to_stage=ModelStage.SHADOW,
    )
    print(f"Promotion: {success}")
else:
    # Review blockers
    print(f"Blockers: {promo_record.blockers}")
```

## Common Patterns

### CI/CD Integration

```yaml
# .github/workflows/ci.yml
- name: Run model validation gates
  run: |
    python -m pytest backend/tests/test_model_validation_service.py -v
    python scripts/validate_model.py --model-version ${GITHUB_SHA::7}}
```

### Scheduled Fairness Audits

```python
# scripts/audit_fairness.py
import schedule
from backend.services.model_validation_service import ModelValidationGate

gate = ModelValidationGate()

def audit_active_model():
    """Run fairness audit on current active model."""
    # Load current active model
    # Run validation with fairness focus
    report = gate.validate_for_promotion(
        ...fairness parameters...
    )
    # Alert if fairness degraded

schedule.every().week.do(audit_active_model)
```

### A/B Test Pre-gates

```python
# Before enabling A/B test, validate shadow model
gate = ModelValidationGate()
report = gate.validate_for_promotion(
    model_version=shadow_version,
    metric_check_level="strict",  # Higher bar for A/B
)

if not report.promotion_allowed:
    logger.error(f"Shadow model failed A/B pre-gate: {report.blockers}")
    sys.exit(1)
```

## Testing Validation Gates

```python
from backend.tests.test_model_validation_service import *

# Run full test suite
pytest backend/tests/test_model_validation_service.py -v

# Run specific category
pytest backend/tests/test_model_validation_service.py::TestModelQualityValidator -v
```

## Troubleshooting

### Issue: "Demographic parity not achieved"

**Cause**: Model shows different positive prediction rates across demographic groups.

**Solutions**:

1. Balance training data across groups
2. Use fairness-aware training (e.g., fairness constraints)
3. Increase fairness tolerance if acceptable
4. Segment model (separate model per group)

### Issue: "Latency exceeds threshold"

**Cause**: Model inference takes too long (GPU memory, complex model).

**Solutions**:

1. Profile code to find bottleneck: `cProfile`, `py-spy`
2. Optimize preprocessing (vectorize, cache)
3. Reduce model complexity (fewer trees in CatBoost)
4. Increase threshold if acceptable for use case

### Issue: "Memory usage exceeds threshold"

**Cause**: Peak memory during inference too high.

**Solutions**:

1. Profile memory: `memory_profiler`, `tracemalloc`
2. Batch predict to reduce peak memory
3. Reduce model size (fewer features, simpler model)
4. Stream data processing instead of loading all at once

### Issue: "Schema validation failed"

**Cause**: Test data has unexpected columns or types.

**Solutions**:

1. Verify expected_columns matches actual feature_list
2. Verify expected_dtypes matches preprocessing output
3. Check test data generation pipeline
4. Ensure consistency between training and inference

## See Also

- [Model Registry Service](model_registry_service.py) - Promotion workflow orchestration
- [Model Loader](../model_loader.py) - Runtime model loading with bundle verification
- [Preprocessing](../../model/preprocessing/preprocessing.py) - Feature engineering and schema
- [Training Notebook](../../model/training/training.ipynb) - Model training with validation integration
