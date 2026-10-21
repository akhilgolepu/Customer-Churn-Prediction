# ADR 0002: Canary disagreement is measured over every compared request

Status: accepted

## Context

A candidate in the shadow slot is scored on every request; a share of responses
(`CANARY_TRAFFIC_PERCENT`) is actually served from it. The canary must decide, without
labels, when a candidate behaves so differently from the active model that it should be
pulled. The original implementation counted disagreements on every request but divided
by the number of requests *served* by the candidate, so at 10% traffic the "rate" was
inflated tenfold and could exceed 100% (see the
[engineering log](../engineering_log.md)).

## Decision

- Disagreement = the two models land on different sides of the decision threshold for the
  same request. The rate is disagreements / **all compared requests** (every request the
  shadow scored), not / requests the shadow served.
- After `CANARY_MIN_SAMPLES` compared requests, a rate above
  `CANARY_MAX_DISAGREEMENT_RATE` triggers `abort_canary()`: the candidate is marked
  `rejected` and unloaded, and the active model is left alone.

## Why

- Both models score every request, so every request is evidence. Using only the served
  share throws away most of the data and, as implemented, broke the arithmetic.
- Decision disagreement (not a score distance) is what a customer would experience: a
  different retention action.
- The canary's traffic share and its detection power become independent settings.

## Consequences

- Measured in the demos (`scripts/demos/demo_shadow_rollback.py`, limit 20%, 60 minimum
  samples): a healthy retrain disagreed on 2.2% of 400 requests and stayed; a candidate
  trained on permuted labels hit 33.3% and was rolled back after 60 requests, in-process,
  against the Docker container and on Postgres. The standing logistic-regression
  challenger disagreed with CatBoost on 2.97% of live requests in the load-test run.
- Disagreement detects *divergence*, not *wrongness*. A candidate that is better than the
  active model also disagrees with it; the limit has to be set above the disagreement two
  equally good models produce (3.4% offline for CatBoost vs logistic regression). Whether a
  candidate is better needs labelled outcomes (promotion gate, monitoring).
- Users in the canary share see the candidate's scores until rollback.
