# Drift demo: shifted traffic -> drift alerts -> retraining trigger

Traffic: held-out test split of the Telco data. Windows of 300 requests through `POST /api/v1/predictions/predict`. Live monitor thresholds: input drift 0.20, prediction drift 0.15 (relative change of the mean between the older and newer half of recent predictions).

## 1. Baseline traffic only

**Monitor after 300 baseline requests**

| Signal | Older half | Newer half | Relative change | Threshold | Alert |
|---|---:|---:|---:|---:|---|
| MonthlyCharges | 66.241 | 65.261 | -0.015 | 0.20 | no |
| tenure | 33.867 | 30.693 | -0.094 | 0.20 | no |
| TotalCharges | 2339.888 | 2105.044 | -0.100 | 0.20 | no |
| SeniorCitizen | 0.153 | 0.160 | +0.043 | 0.20 | no |
| TotalServices | 2.000 | 1.967 | -0.017 | 0.20 | no |
| prediction_mean | 0.270 | 0.277 | +0.027 | 0.15 | no |

Alerts: none

Scheduler poll: no retraining job

## 2. Shifted traffic

Shift applied to the next window: tenure x 0.3, MonthlyCharges x 1.3, TotalCharges = tenure x MonthlyCharges (all other fields unchanged, so the rows still pass validation).

**Monitor after 300 more, shifted requests**

| Signal | Older half | Newer half | Relative change | Threshold | Alert |
|---|---:|---:|---:|---:|---|
| MonthlyCharges | 65.751 | 87.017 | +0.323 | 0.20 | **yes** |
| tenure | 32.280 | 9.650 | -0.701 | 0.20 | **yes** |
| TotalCharges | 2222.466 | 896.832 | -0.596 | 0.20 | **yes** |
| SeniorCitizen | 0.157 | 0.187 | +0.191 | 0.20 | no |
| TotalServices | 1.983 | 2.047 | +0.032 | 0.20 | no |
| prediction_mean | 0.273 | 0.392 | +0.432 | 0.15 | **yes** |

Alerts: ['Input drift alert on MonthlyCharges: delta=0.323', 'Input drift alert on tenure: delta=-0.701', 'Input drift alert on TotalCharges: delta=-0.596', 'Prediction drift alert: delta=0.432']

Mean served churn probability: baseline window 0.273, shifted window 0.392.

## 3. Evidently: per-feature drift tests (baseline window vs shifted window)

| Feature | Test | Score | Threshold | Drift |
|---|---|---:|---:|---|
| MonthlyCharges | K-S p_value | 1.15e-17 | 0.05 | **yes** |
| tenure | K-S p_value | 1.42e-42 | 0.05 | **yes** |
| TotalCharges | K-S p_value | 5.19e-11 | 0.05 | **yes** |
| SeniorCitizen | Z-test p_value | 0.33 | 0.05 | no |
| Partner | Z-test p_value | 0.191 | 0.05 | no |
| Dependents | Z-test p_value | 1 | 0.05 | no |
| PhoneService | Z-test p_value | 0.642 | 0.05 | no |
| MultipleLines | chi-square p_value | 0.782 | 0.05 | no |
| InternetService | chi-square p_value | 0.529 | 0.05 | no |
| OnlineSecurity | chi-square p_value | 0.929 | 0.05 | no |
| OnlineBackup | chi-square p_value | 0.116 | 0.05 | no |
| DeviceProtection | chi-square p_value | 0.265 | 0.05 | no |
| TechSupport | chi-square p_value | 0.587 | 0.05 | no |
| StreamingTV | chi-square p_value | 0.771 | 0.05 | no |
| StreamingMovies | chi-square p_value | 0.972 | 0.05 | no |
| Contract | chi-square p_value | 0.755 | 0.05 | no |
| PaperlessBilling | Z-test p_value | 1 | 0.05 | no |
| PaymentMethod | chi-square p_value | 0.0542 | 0.05 | no |

Drifted features: 3 of 18 (dataset drift: False); detector severity: high; should_retrain: True.

## 4. Retraining trigger

Scheduler poll: enqueued a retraining job with reason **drift_alert**.

- retraining job status: **completed** (attempts: 1)
- candidate `auto_20261018T172011Z` registered from 7043 rows; holdout AUC 0.8430; validation gate allowed: False; promoted: False

## 5. Verification

- [x] no alerts on baseline-only traffic
- [x] no retraining job before the shift
- [x] live monitor flags tenure, MonthlyCharges and TotalCharges
- [x] prediction drift alert fires
- [x] Evidently flags the shifted features
- [x] drift alert enqueues a retraining job

Result: **PASS**
