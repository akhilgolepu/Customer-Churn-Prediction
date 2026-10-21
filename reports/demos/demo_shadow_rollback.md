# Shadow -> canary -> rollback demo

Server: in-process TestClient. Config: canary traffic 20%, min samples 60, max disagreement 20%, decision threshold 0.38. Traffic: 1409 held-out customer rows replayed through `POST /api/v1/predictions/predict`.

## 1. Baseline

**Registry at start**
- active: `v1 (active)`
- shadow: `none`
- versions: v1=active

## 2. Healthy retrain (v2): shadow, then promote

- v2 shadowed on 400 requests: 9 label disagreements, disagreement rate **2.2%** (limit 20%), rolled back: **False**

- promote v2: HTTP 200; validation gate allowed: **True** (candidate ROC-AUC 0.8574 vs active 0.8562 on 7043 labelled rows)

**Registry after promoting v2**
- active: `v2 (active)`
- shadow: `none`
- versions: v1=archived, v2=active

## 3. Degraded retrain (v3): shadow, then auto-rollback

v3 offline metrics (measured on the held-out split): ROC-AUC 0.6424, Brier 0.1938.

- direct promote of v3: HTTP **409** `promotion_blocked`
  - blocker: Model quality metrics below thresholds
  - blocker: Candidate ROC-AUC 0.6154 is 0.2420 below the active model (0.8574); allowed drop is 0.0200

**Registry with v3 in shadow**
- active: `v2 (active)`
- shadow: `v3 (candidate)`
- versions: v1=archived, v2=active, v3=candidate

- v3: canary auto-rolled back after **60** requests
- v3 canary: 8 requests served by the candidate, 20 disagreements, rate **33.3%** (limit 20%)
- last rollback reason: _Canary disagreement rate 0.333 exceeded threshold 0.200_

**Registry after canary rollback**
- active: `v2 (active)`
- shadow: `none`
- versions: v1=archived, v2=active, v3=rejected

## 4. Verification

- [x] v2 promotion passed the validation gate
- [x] validation gate refused direct promotion of v3 (409)
- [x] canary rolled back automatically
- [x] v2 (healthy) still active
- [x] no shadow model remains
- [x] v3 not left in a servable state
- post-rollback prediction has no shadow score: True

Result: **PASS**
