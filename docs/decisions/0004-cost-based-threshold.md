# ADR 0004: The decision threshold comes from stated economics, not 0.5

Status: accepted

## Context

The API returns a probability and a yes/no decision. Common defaults (0.5, maximum F1,
Youden's J) optimise statistical criteria that have nothing to do with what a retention
contact costs or earns. The previous default, 0.62, had been chosen from costs but on
scores inflated by a class weight.

## Decision

`DECISION_THRESHOLD` (default **0.38**) maximises expected net benefit under a stated cost
model: contacting costs an offer cost ($50), a contacted churner is saved with probability
save rate (30%), and a saved customer is worth 12 months of margin ($449.16). It is chosen
on cross-fitted calibrated **validation** scores (`model/training/threshold_analysis.py`);
the test split only reports it. The closed-form break-even threshold
`offer_cost / (save_rate x value)` = 0.371 is reported next to it.

## Why

- The threshold is a business decision; making the assumptions explicit and versioned
  (`params.yaml`) means a change of economics is a one-line change plus a re-run.
- With calibrated probabilities the closed form is valid, which gives a sanity check that
  needs no optimisation at all; the empirical and closed-form thresholds differ by about
  one grid step.

## Consequences

- The gain over an untuned 0.50 is **not** statistically distinguishable on the test split
  (+$716 per 1,000 customers, 95% CI -$421 to +$1,888); the analysis identifies a region of
  good thresholds (the curve is flat from about 0.35 to 0.50), not a precise optimum. The
  README says so.
- The answer moves a lot with the assumptions (sensitivity table in the README: from 0.06
  to "never contact" across plausible costs and save rates). The save rate in particular
  can only be measured with a randomised holdout group (see
  [architecture: real data](../architecture.md#how-i-would-run-this-with-real-data)).
- The threshold depends on calibration: if a future model is not calibrated, the threshold
  must be re-derived (the analysis runs on whatever calibration the artifact ships with).
- Requests can override it (`?threshold=`); deployments via `DECISION_THRESHOLD`; a test keeps
  `params.yaml` and the API default equal.
