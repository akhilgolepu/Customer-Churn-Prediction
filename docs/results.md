# Results

Detailed results moved out of the README. Every number comes from the command named next to it.

## Model comparison

Dataset: IBM Telco Customer Churn, 7,043 rows, 26.54% churn, 11 blank `TotalCharges` values (all
tenure 0). Split: stratified 60/20/20, seed 42 (4,225 / 1,409 / 1,409 rows). The test rows are exactly
the historical 80/20 test split. Model: CatBoost (depth 4, learning rate 0.03, L2 10, no class weight,
299 trees chosen by early stopping on validation). All settings live in `params.yaml`.

```bash
python ml/training/train.py              # fit on train, early-stop + calibrate on validation
python ml/training/evaluate.py           # CV comparison, test once, reliability, slices (~4 min)
python ml/training/threshold_analysis.py # cost-based threshold on calibrated validation scores
```

Cross-validation on train+validation (5 stratified folds, 5,634 rows), mean with 95% interval:

| Model | ROC-AUC | PR-AUC | Brier | Log loss |
|---|---|---|---|---|
| Dummy (predict base rate) | 0.500 | 0.265 | 0.195 | 0.579 |
| Logistic regression (one-hot + scaling) | 0.848 [0.837, 0.859] | 0.665 [0.640, 0.689] | 0.134 [0.129, 0.139] | 0.413 [0.401, 0.426] |
| CatBoost, no class weight (shipped recipe) | 0.848 [0.835, 0.860] | 0.667 [0.640, 0.694] | 0.134 [0.129, 0.139] | 0.414 [0.400, 0.427] |
| CatBoost, balanced class weight (old recipe) | 0.849 [0.837, 0.862] | 0.669 [0.639, 0.700] | 0.160 [0.153, 0.167] | 0.478 [0.463, 0.493] |
| LightGBM | 0.845 [0.831, 0.859] | 0.661 [0.638, 0.685] | 0.136 [0.130, 0.141] | 0.418 [0.402, 0.434] |

Held-out test split, scored once (1,409 rows): shipped artifact ROC-AUC 0.8464, PR-AUC 0.6655,
Brier 0.1350, log loss 0.4138; logistic regression refit on train+validation 0.8449 / 0.6492 / 0.1365 /
0.4165. Full tables, including the paired bootstraps: [reports/evaluation/model_comparison.md](../reports/evaluation/model_comparison.md).

What this does and does not say:

- **Nothing beats logistic regression.** Paired bootstrap on pooled out-of-fold scores, CatBoost minus
  logistic regression: ROC-AUC -0.0008 [-0.0034, +0.0018], Brier +0.0002 [-0.0011, +0.0013]. LightGBM:
  ROC-AUC -0.0038 [-0.0076, -0.0001]. CatBoost stays because the serving, SHAP and canary code are built
  around it, not because it scores better, and logistic regression is kept running next to it as a live
  challenger (see [below](#active-model-and-standing-challenger)).
- **The score is a calibrated probability.** The old recipe's balanced class weight (2.77) bought no
  ranking (+0.0010 [-0.0016, +0.0037] AUC) and pushed scores up (Brier +0.026, ECE 0.146 on test), so it
  was dropped. Calibration was then chosen on validation by 5-fold cross-fitting (lowest log loss among
  identity, Platt and isotonic): identity 0.4218, Platt 0.4222, isotonic 0.4704. The unweighted model
  needed no correction (Platt fit a = 0.980, b = 0.014), so the shipped calibration file is the
  identity. Test ECE 0.018 ([diagram](../reports/evaluation/reliability_diagram.png)).
- **No test-set tuning.** The previous model was early-stopped on the same rows it was evaluated on;
  that is fixed. The test fingerprint is recorded in `models/training_metadata.json`.
- **One public, widely used dataset.** Nothing here is validated against real retention outcomes. See
  the [model card](model_card.md) for intended use, slices and limitations.

## Decision threshold

`POST /predict` uses `DECISION_THRESHOLD` (default **0.38**) when the request does not pass
`?threshold=`. The value comes from `ml/training/threshold_analysis.py`, which:

1. scores the validation split and calibrates it out of fold (each row by a calibrator that did not see it),
2. picks the grid threshold with the highest expected net benefit on those scores (the test split is
   never used to pick it),
3. reports the closed-form break-even threshold next to it, and
4. reports everything once on the held-out test split.

**Stated assumptions** (not measured business data; edit `params.yaml` -> `threshold`): contacting a
customer costs an offer cost; a contacted churner is saved with some probability; a saved customer is
worth 12 months of the mean churner's monthly charge ($74.86, computed on train+validation only) times
a margin.

With a calibrated probability p, contacting pays off when `p x save_rate x value > offer_cost`, so the
break-even threshold is `offer_cost / (save_rate x value)`. Two scenarios are reported on purpose:

| Scenario | Offer cost | Save rate | Value of saved customer | Empirical (validation) | Closed form |
|---|---:|---:|---:|---:|---:|
| `margin_with_incentive` (**primary**) | $50 | 30% | $449.16 (12 x $74.86 x 50%) | **0.38** | 0.371 |
| `revenue_cheap` | $20 | 30% | $898.32 (12 x $74.86) | 0.06 | 0.074 |

Net benefit per 1,000 customers on the held-out split (primary scenario):

| Policy | Flagged | Precision | Recall | Net benefit |
|---|---:|---:|---:|---:|
| Contact nobody | 0% | n/a | 0 | $0 |
| Contact everybody | 100% | 0.265 | 1.00 | -$14,233 |
| Threshold 0.50 | 20.4% | 0.667 | 0.513 | $8,142 |
| Threshold 0.62 (previous default) | 11.4% | 0.752 | 0.324 | $5,858 |
| Threshold 0.38 (new default) | 31.4% | 0.580 | 0.687 | **$8,858** |
| Closed form 0.371 | 32.0% | 0.581 | 0.701 | $9,052 |

- **Gain over the untuned baseline is not significant.** Against a plain 0.50 cut-off, 0.38 earns
  +$716 per 1,000 customers on test (95% bootstrap CI -$421 to +$1,888). With 1,409 test rows that is
  indistinguishable from zero; the curve is flat between roughly 0.35 and 0.50. What the analysis
  establishes is the *region* of good thresholds under the stated economics, not a precise optimum.
- 0.62 (the previous default) is not a fair baseline: it was tuned on the old class-weighted model's
  upward-biased scores. On calibrated scores it flags too few customers; 0.38 beats it by +$2,999 per
  1,000 (95% CI +$1,431 to +$4,682), which mostly measures that mismatch.
- **Empirical vs closed form.** The closed-form threshold assumes perfectly calibrated scores and an
  infinite sample; the empirical one maximises a step function on 1,409 validation rows. The net-benefit
  curve is flat around the optimum (validation: $8,732 at 0.35, $9,392 at 0.40, $8,843 at 0.45 per 1,000),
  so the two differ by about one grid step and are indistinguishable on test (closed form minus empirical
  +$194, 95% CI -$71 to +$506). Calibration is what makes the closed form usable at all: on the old
  weighted scores it would have pointed at the wrong place.
- In the cheap-outreach scenario contacting almost everyone is right (empirical 0.06, closed form 0.074).
  **The right threshold is a business decision**, and it moves a lot with the economics (validation-chosen
  threshold, closed form, and test net benefit per 1,000 at the empirical threshold):

| Offer cost | Save rate | Empirical | Closed form | Model $/1,000 | Contact-everyone $/1,000 |
|---:|---:|---:|---:|---:|---:|
| $25 | 10% | 0.52 | 0.557 | $1,057 | -$13,078 |
| $25 | 30% | 0.24 | 0.186 | $18,313 | $10,767 |
| $25 | 50% | 0.06 | 0.111 | $40,470 | $34,612 |
| $50 | 10% | 0.94 (grid edge: contact nobody) | 1.113 (> 1: never contact) | $0 | -$38,078 |
| $50 | 30% | **0.38** | 0.371 | $8,858 | -$14,233 |
| $50 | 50% | 0.25 | 0.223 | $26,861 | $9,612 |
| $100 | 10% | 0.94 (grid edge) | 2.226 (> 1: never contact) | $0 | -$88,078 |
| $100 | 30% | 0.72 | 0.742 | $739 | -$64,233 |
| $100 | 50% | 0.38 | 0.445 | $9,522 | -$40,388 |

Override per request (`?threshold=0.4`) or per deployment (`DECISION_THRESHOLD=0.4`). `params.yaml`
`evaluation.decision_threshold` must equal the API default (a test enforces it). The UI's
low/medium/high risk tiers use fixed cut-offs (0.33 / 0.66) and are independent of this threshold.

## Active model and standing challenger

Because the two models tie, the simpler one is not thrown away: `train.py` also trains logistic
regression on the same split (calibration chosen the same way; identity won again) and exports it as
JSON (`models/logreg_challenger.json`: coefficients, imputation medians, scaling and one-hot
weights, scored with numpy, no pickles). At startup the API attaches it to the shadow slot whenever no
other candidate is being tested (`CHALLENGER_ENABLED=true`, default), so every `/predict` also returns
the challenger's `shadowProbability` and `GET /api/v1/system/canary` counts how often the two disagree
on live traffic. Shipped artifacts on the test split (`python ml/training/evaluate.py`):

| | ROC-AUC | PR-AUC | Brier | Log loss |
|---|---:|---:|---:|---:|
| CatBoost (active) | 0.8464 | 0.6655 | 0.1350 | 0.4138 |
| Logistic regression (challenger) | 0.8454 | 0.6517 | 0.1361 | 0.4159 |
| Active minus challenger [95% CI] | +0.0010 [-0.0041, +0.0059] | +0.0138 [-0.0024, +0.0297] | -0.0011 [-0.0034, +0.0010] | -0.0022 [-0.0082, +0.0041] |

Their decisions differ at threshold 0.38 for 3.4% of test customers (Spearman 0.985). Promoting the
challenger is one gated `POST /models/promote`; `/explain` then returns exact linear log-odds
contributions instead of TreeSHAP. Shadow-testing another candidate displaces the challenger until the
next startup; a challenger rejected by the canary is not re-attached. Rationale and trade-offs:
[ADR 0001](decisions/0001-catboost-active-logreg-challenger.md).
