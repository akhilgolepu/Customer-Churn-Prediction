# ADR 0005: The promotion gate fails closed, with an audited override

Status: accepted

## Context

`ModelValidationGate` existed and was unit-tested, but `POST /api/v1/models/promote` never
called it: any admin could make any artifact the active model. The canary only protects
the shadow phase, and only against divergence.

## Decision

Promotion scores the candidate and the current active model on a labelled CSV
(`PROMOTION_EVAL_DATA_PATH`) and runs the gate: ROC-AUC >= 0.75, precision/recall/F1
floors at the decision threshold (0.40 / 0.40 / 0.45), single-row latency, schema and
missing-data checks, and non-inferiority (the candidate may not be more than 0.02 AUC
below the active model). Any blocker returns **409 `promotion_blocked`** with the blockers.
**No evaluation data is itself a blocker.** An admin can promote anyway with
`override_gate: true` and a non-empty `override_reason`; that writes a
`model_promotion_gate_overridden` audit event with the actor, reason and blockers. The
retraining job's automatic promotion goes through the same gate.

## Why

- A gate that silently passes when it cannot evaluate is worse than none, because it looks
  like protection. Failing closed makes the missing evidence visible.
- Emergencies happen (a hotfix model, a broken evaluation file), so an override exists, but
  it is explicit, justified and attributable.
- Non-inferiority against the active model on the same rows catches regressions an absolute
  floor would let through.

## Consequences

- The deployed API has no labelled data in its image (the Telco CSV has no clear data
  licence), so promotions there return 409 unless an admin overrides. That is the intended
  behaviour for a demo, not a bug.
- With the default evaluation file (the full Telco CSV) the gate scores rows the candidate
  was trained on, so its AUC is optimistic: it catches broken or regressed models, it is not
  an unbiased estimate. With real data it should evaluate on recent labelled outcomes no
  candidate trained on.
- The retraining job still runs its own pre-check with the gate's default thresholds
  (recall >= 0.65 at 0.5), which differ from the promotion gate's settings; unifying them
  is open work.
