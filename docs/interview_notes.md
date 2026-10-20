# Interview notes

Short, honest answers to the questions this project invites, and resume bullets that use only
measured numbers. Every number links back to the command that produced it; `backend/tests/test_readme_claims.py`
checks them against the generated outputs.

## Resume bullets (each with the command that produced it)

- **Tested whether boosting earns its keep, and reported the answer either way.** On Telco,
  CatBoost ties logistic regression (CV ROC-AUC difference -0.0008, 95% CI -0.0034 to +0.0018); on
  a 10,000-customer bank dataset it wins by +0.109 (95% CI +0.099 to +0.120), and adding two
  non-linear features to the logistic regression cuts that to +0.0225, about four-fifths of the gap.
  `python model/training/evaluate.py` · `python model/training/second_dataset.py`
- **Served calibrated probabilities with a cost-based decision rule.** Dropping a class weight took
  test calibration error (ECE) from 0.146 to 0.018; the threshold (0.38) is chosen on validation
  data from stated economics and matches the closed-form break-even (0.371).
  `python model/training/evaluate.py` · `python model/training/threshold_analysis.py`
- **Built a model lifecycle that refuses bad models automatically.** A candidate trained on
  shuffled labels is blocked by the promotion gate (HTTP 409) and, once shadowed, rolled back by the
  canary after 60 requests at 33.3% disagreement, while a healthy retrain (2.2%) is promoted.
  `python scripts/demo_all.py`
- **Made an untested Postgres mode work and kept it working.** Six defects fixed (one made every
  prediction fail after March 2026); the full suite (197 tests) runs on SQLite and Postgres in CI, and golden
  predictions on a committed 500-row sample pin the real model's output to 1e-6.
  `pytest backend/tests` (and with `DATABASE_BACKEND=postgres`)
- **Measured capacity instead of quoting a load generator's ceiling.** About 290 req/s with 2
  uvicorn workers vs 178 with 1 at saturation, p95 18 ms at 20 users; Prometheus metrics and a
  provisioned Grafana dashboard.
  `python tasks.py loadtest --users 100 --workers 2`

## Questions an interviewer is likely to ask

**Why serve CatBoost if logistic regression ties it?** On this dataset the accuracy argument is
gone, and the repo says so. CatBoost stays for native categoricals, exact TreeSHAP explanations and
the existing serving code; logistic regression runs next to it on every request as a challenger, so
the gap is measured on live traffic (`churn_canary_disagreement_rate`; offline, decisions differ for
3.4% of customers on test). On the bank
dataset the choice reverses: CatBoost is clearly better. [ADR 0001](decisions/0001-catboost-active-logreg-challenger.md)

**How do you know the test numbers are not tuned?** Early stopping, the calibration method and the
threshold are chosen on a separate validation split; the test split is scored once by
`evaluate.py`. The original model had been early-stopped on its own test split; that was the first
thing fixed. Re-running `dvc repro` regenerates every report byte for byte, so the outputs are not hand-edited.

**Is 0.38 really better than 0.5?** Not measurably: +$716 per 1,000 customers on test with a 95%
interval of -$421 to +$1,888. The analysis finds a flat region of good thresholds under assumed
costs; the save rate it depends on can only be measured with a randomised holdout group.
[ADR 0004](decisions/0004-cost-based-threshold.md)

**What does the canary actually detect?** Divergence, not correctness: the share of requests where
the candidate and the active model fall on different sides of the threshold. A better model also
disagrees, so the limit sits above what two equally good models produce; whether a candidate is
better needs labelled outcomes, which is the promotion gate's job.
[ADR 0002](decisions/0002-canary-disagreement-over-compared-requests.md)

**How would you know the model is getting worse without labels?** You partly can't. Input and score
drift fire immediately but only say the population changed; calibration and AUC on outcomes that
arrive later are the real signal, and campaign results against a holdout are the business signal.
[Architecture: real data](architecture.md#how-i-would-run-this-with-real-data)

**Why is the degraded demo model's AUC 0.64 and not 0.5?** A model trained on shuffled labels is
still a function of predictive features, so it can correlate with churn by accident. Twenty
permuted-label models averaged 0.529 with SD 0.125, against SD 0.021 for label-independent scores.
[docs/permutation_check.md](permutation_check.md)

**Why is the CI data synthetic?** The Telco CSV has no clear licence, so real rows are not
committed. The 500-row sample keeps the consistency rules and gets labels from the model itself; it
says nothing about accuracy. Its job is to pin the shipped model's predictions so any change in
preprocessing, serving or library versions fails CI.

**What is the worst bug you found?** Postgres mode had never run: `audit_logs` only had a March 2026
partition, so every prediction (each writes an audit event) would have failed from April. That and
five more fixes are in the [engineering log](engineering_log.md).

**Is the model fair?** Calibration holds in every slice checked, but seniors have lower within-group
AUC (0.781 vs 0.849), and an age-related feature is a model input. Whether that is acceptable is a
policy decision the [model card](model_card.md) flags rather than answers.

**What breaks if you scale this out?** With several workers the loaded model and canary counters
are per process: a promote call switches only the worker that handled it until the others restart.
The demo deployment runs one worker; [ADR 0003](decisions/0003-sqlite-by-default.md) describes
what a multi-worker setup needs.

## Selected bugs

Every bug found while hardening the project is fixed, has a regression test where code changed, and
is written up in [docs/engineering_log.md](engineering_log.md) (32 entries). Four that say the
most about the project:

- **The original model was evaluated on its own early-stopping data.** Its tree count was chosen on
  the same 20% split its test metrics came from. The rebuilt pipeline early-stops, calibrates and picks
  the threshold on a separate validation split and touches the test split once.
- **After a promotion and a restart, the API served a different model than the registry reported.**
  The registry persists; the runtime always booted the default artifact. Startup now loads what the
  registry says and refuses to start if the active model cannot be loaded.
- **The Postgres mode had never run, and could not have.** Six defects stood between the code and a
  working deployment, the worst being that `audit_logs` only had a March 2026 partition, so every
  prediction (each writes an audit event) failed from April on. The suite now runs on Postgres in CI.
- **The drift detector looked tested but never executed.** A dependency upgrade broke its import, a flag
  silently disabled it, and its tests turned the `ImportError` into a skip; its result parsing was also
  wrong. It is now ported, and its tests fail instead of skipping.
