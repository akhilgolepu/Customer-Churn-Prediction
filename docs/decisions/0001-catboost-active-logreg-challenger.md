# ADR 0001: CatBoost stays active; logistic regression runs as a standing challenger

Status: accepted (2026-10-18)

## Context

The honest evaluation (`python ml/training/evaluate.py`, [model_comparison.md](../../reports/evaluation/model_comparison.md))
shows that CatBoost does not beat logistic regression on this dataset:

- 5-fold CV ROC-AUC 0.8476 (CatBoost) vs 0.8484 (logistic regression); paired bootstrap of the
  difference on pooled out-of-fold scores -0.0008, 95% CI -0.0034 to +0.0018.
- Shipped artifacts on the test split: CatBoost minus logistic regression ROC-AUC +0.0010
  (-0.0041 to +0.0059), Brier -0.0011 (-0.0034 to +0.0010). Both are calibrated (identity calibration
  chosen on validation for each).
- The two models' decisions differ at the 0.38 threshold for 3.4% of test customers; Spearman rank
  correlation of their scores is 0.985.

Options considered: keep CatBoost and just document the tie; switch the served model to logistic
regression; keep CatBoost active and run logistic regression continuously as a challenger.

## Decision

CatBoost remains the active model. A logistic-regression model trained on the same split
(`models/logreg_challenger.json`, written by `ml/training/train.py`) is attached to the
shadow slot at API startup whenever no other candidate is being tested (`CHALLENGER_ENABLED=true`,
default). It is scored on every request; the canary counter (`GET /api/v1/system/canary`) records how
often the two disagree on live traffic.

## Why

- **Accuracy does not decide it**; the comparison says so and we keep saying so.
- CatBoost is kept for engineering reasons that do exist: native categorical handling, exact TreeSHAP
  explanations, and the serving/canary code already built around it.
- Running the simpler model as a live challenger turns "is the complex model worth it?" into a question
  the system keeps measuring, instead of a one-off offline answer. If live disagreement ever comes with
  better outcomes for the challenger, promoting it is one gated API call.
- It also exercises the registry/shadow path continuously, not only during demos.

## Consequences

- The linear model is stored as JSON (coefficients, imputation medians, scaling, one-hot weights) and
  scored with numpy, so no pickles are loaded at runtime. A test checks the export reproduces
  scikit-learn (max difference 3.3e-16 at training time). Its explanations are exact log-odds
  contributions; promoting it changes `/explain` from TreeSHAP to linear contributions.
- The challenger occupies the shadow slot. Shadow-testing a new candidate displaces it; it is
  re-attached at the next startup if the slot is free. A challenger rejected by the canary is not
  re-attached.
- With `CANARY_ENABLED=true` the challenger would also serve `CANARY_TRAFFIC_PERCENT` of responses and
  could be auto-rolled back by the disagreement limit. Canary is off by default.
- Every prediction now pays for a second (cheap) model evaluation, and `/predict` responses include
  `shadowProbability`. The load test was re-run with the challenger attached
  ([load test results](../loadtest_results.md)).

## Update: does the tie generalise? (second dataset)

`python ml/training/second_dataset.py` ([reports/experiments/second_dataset.md](../../reports/experiments/second_dataset.md))
runs the same pipeline on a bank churn dataset (OpenML 46911, 10,000 customers). There
CatBoost beats logistic regression clearly: +0.109 ROC-AUC on pooled out-of-fold scores
(95% CI +0.099 to +0.120). A logistic regression given the two non-linear shapes a tree
finds by itself (one-hot `products_number`, a spline on `age`) closes most of that gap,
leaving CatBoost +0.0225 (+0.018 to +0.027) ahead.

So the Telco tie is a property of the Telco data (its signal is close to linear in the
encoded features), not evidence that boosting is unnecessary for churn. That supports
keeping both models in place: the challenger setup measures the gap on live traffic
instead of assuming it.

