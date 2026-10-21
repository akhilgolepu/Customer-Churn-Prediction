# Model card: churn probability (CatBoost, Telco)

Every number below comes from a script in this repository; the command is given
next to it. Regenerate with:

```bash
python ml/training/train.py              # model + calibration + models/training_metadata.json
python ml/training/evaluate.py           # reports/evaluation/model_comparison.md, reports/evaluation/slice_metrics.md, reports/evaluation/reliability_diagram.png, reports/evaluation/evaluation.json
python ml/training/threshold_analysis.py # reports/evaluation/threshold_analysis.json
```

## Intended use

- Rank existing telecom-style subscription customers by their probability of
  churning, so a retention team can decide whom to contact.
- The served score is meant to be read as a probability (it is calibrated, see
  below) and compared with a cost-based threshold (`DECISION_THRESHOLD`, default
  0.38, derived from *assumed* economics).
- Demonstration / portfolio use on a public benchmark. It has never been
  validated against real retention outcomes.

## Must not be used for

- Any decision about a real person (pricing, credit, service eligibility,
  employment, collections). The data is a public benchmark of unknown
  provenance and age, not a sample of any real customer base.
- Any population other than the one in the training data without re-validation.
- Treating the threshold as a business fact. It moves a lot with the assumed
  offer cost and save rate (see the sensitivity table in the README).
- Inferring causes of churn. SHAP explanations describe the model, not the
  customer; nothing here is causal.

## Model

| | |
|---|---|
| Algorithm | CatBoost gradient boosting, depth 4, learning rate 0.03, L2 10 (`params.yaml`) |
| Trees | 299 (early stopping on the validation split chose iteration 298) |
| Class weighting | **None.** The previous recipe used a balanced weight (2.77); it did not improve ranking and made the scores run high (see "Why the class weight was dropped") |
| Calibration | **Identity** (raw CatBoost probability served unchanged), chosen by rule, see below |
| Features | 25: tenure, charges, services, contract, payment method plus 7 engineered features (`models/feature_list.json`). `gender` and `customerID` are excluded. `SeniorCitizen` is a model input |
| Explanations | SHAP TreeExplainer on the raw model (log-odds space). Calibration is monotone, so it does not change which drivers rank highest |

## Data

- IBM Telco Customer Churn, 7,043 rows, 26.5% churned (`data/Telco-Customer-Churn.csv`, tracked with DVC).
- 11 rows have blank `TotalCharges` (all tenure 0); they are kept as missing values.
- Split (stratified, seed 42): train 4,225 / validation 1,409 / test 1,409. The
  test rows are exactly the rows of the project's historical 80/20 test split.
- Train: model fitting. Validation: early stopping, choice of calibration method,
  choice of threshold. Test: reported once, used for nothing else.

## Performance (held-out test split, n = 1,409)

| Metric | Value |
|---|---:|
| ROC-AUC | 0.8464 (bootstrap 95% CI 0.8242 to 0.8677) |
| PR-AUC | 0.6655 |
| Brier score | 0.1350 |
| Log loss | 0.4138 |
| Expected calibration error (10 bins) | 0.018 |
| At threshold 0.38: flagged / precision / recall | 31.4% / 0.580 / 0.687 |

Comparison with alternatives (full tables in [model_comparison.md](../reports/evaluation/model_comparison.md)):

- **Logistic regression is as good.** 5-fold CV ROC-AUC 0.8484 for logistic
  regression vs 0.8476 for CatBoost; the paired bootstrap difference on pooled
  out-of-fold scores is -0.0008 (95% interval -0.0034 to +0.0018). On test the
  shipped model is +0.0015 (-0.0035 to +0.0065). No model in the comparison
  (CatBoost with or without class weight, LightGBM) beats logistic regression;
  LightGBM is slightly worse out of fold (-0.0038, -0.0076 to -0.0001).
- CatBoost is kept because the serving, SHAP and canary code are built around it,
  not because it scores better. Logistic regression (same split, identity calibration)
  runs next to it as a standing challenger in the API's shadow slot; on test the two
  differ by +0.0010 ROC-AUC (-0.0041 to +0.0059) and disagree at the threshold for 3.4%
  of customers. See [ADR 0001](decisions/0001-catboost-active-logreg-challenger.md).

## Calibration

- Candidates (identity, Platt, isotonic) were compared by 5-fold cross-fitting on
  the validation split; the lowest mean log loss wins (rule fixed in
  `params.yaml` before the run). Cross-fitted log loss: identity 0.4218, Platt
  0.4222, isotonic 0.4704. **Identity won**: without the class weight, CatBoost's
  logloss objective already produces calibrated probabilities. For reference,
  Platt fitted on all of validation is a = 0.980, b = 0.014 (a = 1, b = 0 would be
  a no-op).
- Reliability on test: [reliability_diagram.png](../reports/evaluation/reliability_diagram.png).
  ECE: shipped model 0.018, logistic regression 0.017, CatBoost with the old
  balanced class weight 0.146.
- The serving path applies whatever calibration file sits next to the model
  (`catboost_churn.calibration.json`, or `model/calibration.json` inside a
  bundle); here it is the identity.

### Why the class weight was dropped

The balanced weight (negatives / positives) is a common default for imbalanced
classes, but it only shifts scores upward. In CV it changed ROC-AUC by +0.0010
(-0.0016 to +0.0037), i.e. not at all, while Brier got worse by +0.0262 (+0.0223
to +0.0301) and log loss by +0.0645. With a cost-based threshold there is no
reason to distort the probabilities, so the weight was removed.

## Slices (test split, threshold 0.38)

Full table: [slice_metrics.md](../reports/evaluation/slice_metrics.md). Reading it:

- **Calibration holds in every slice.** Mean predicted vs observed churn rate is
  within 0.045 for all 13 slice values (largest: tenure 6-12, +0.045).
- **Within-slice AUC is lower than overall AUC (0.846), as expected.** Slicing on
  Contract or tenure removes the model's strongest signal, so ranking inside a
  slice is harder: Month-to-month 0.756, One year 0.737, Two year 0.791 (wide CI,
  9 churners), tenure 6-12 0.732. SeniorCitizen = 1 has AUC 0.781 (0.721 to 0.839)
  vs 0.849 for non-seniors; that gap is real at this sample size (222 seniors) and
  worth watching, though it does not come with a calibration gap (-0.036).
- **Recall differs by slice because base rates differ.** One threshold on a
  calibrated probability flags customers by risk, so low-churn groups are rarely
  contacted: recall is 0.775 for month-to-month customers and 0.056 for one-year
  contracts (1.3% of them flagged); 0.0 for customers without internet service.
  That is the intended behaviour of an expected-value rule, not a model defect,
  but it means the retention programme will almost never reach long-contract
  churners.
- `gender` is not a model input; no slice check was run on it.

## Limitations

- One public dataset; no measured retention outcomes, offer costs or save rates.
- The threshold depends on assumed economics (offer cost $50, save rate 30%,
  margin 50%, 12-month horizon).
- The promotion gate's default evaluation set is the full CSV, which overlaps the
  training data; it catches broken or regressed models but is not an unbiased
  performance estimate.
- SeniorCitizen is used as a feature. Whether an age-related attribute may be used
  in a real retention decision is a policy question this card cannot answer.
- Fold-based 95% intervals in the CV table are somewhat too narrow (folds share
  training rows); the paired bootstrap intervals are the ones to use.
