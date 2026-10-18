# Load test results: `POST /api/v1/predictions/predict`

Measured with Locust against a local single-worker uvicorn process. These numbers
describe **this setup only**; re-run `loadtest/run_loadtest.sh` on your own machine
(or against a deployed URL) before quoting them anywhere else.

## Setup

| Item | Value |
|---|---|
| Hardware | Cloud VM, 2 vCPU Intel Xeon @ 2.10 GHz, 8 GB RAM, Linux 6.18 |
| Server | `uvicorn` with **1 worker**, Python 3.13.16, dependencies pinned as in `requirements-runtime.txt` (the Docker image's set) |
| Load generator | Locust 2.46.7, **on the same 2-vCPU machine** (so server and generator compete for CPU; a separate load-generator host would read somewhat better) |
| Model | shipped CatBoost (`catboost_churn.cbm`), SQLite storage, in-process prediction history |
| Payloads | Real rows sampled at random from the Telco dataset (not one repeated request) |
| Rate limiter | Disabled for the run (`PREDICT_RATE_LIMIT_PER_MINUTE=100000000`). With the default of 30/min per IP, a single-IP load test measures the limiter, not the model |
| Warm-up | 20 requests before measurement |
| Duration | 60 s per run, after ramp-up |

## Results

| Concurrent users | Requests | Failures | Throughput | p50 | p95 | p99 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 (ramp 5/s) | 8,119 | 0 (0.00%) | **135 req/s** | 14 ms | **41 ms** | 62 ms | 231 ms |
| 50 (ramp 10/s) | 10,635 | 0 (0.00%) | 177 req/s | 140 ms | 320 ms | 420 ms | 463 ms |

Reading the two rows together: throughput tops out around 135 to 180 requests/s on
this machine with one worker, and at 50 users the extra concurrency only adds queueing
delay (latency rises about 8x for a 30% throughput gain). The 20-user row is the
representative "comfortable load" number.

Server resident memory was about 320 MB after serving traffic (CatBoost + SHAP +
pandas loaded). That fits a 512 MB instance but with limited headroom.

## Not measured

- `/explain` (SHAP) is slower than `/predict` and was not load tested.
- No multi-worker, no Postgres, no Redis, no network latency, and nothing on the
  production host. A free Render instance has less CPU than this VM, so expect lower
  throughput there.

## Reproduce

```bash
pip install -r requirements-runtime.txt locust
# data/Telco-Customer-Churn.csv is tracked with DVC: run `dvc pull` first
loadtest/run_loadtest.sh 20 5 60s      # users, spawn rate, duration
# results land in loadtest/results/ (CSV)
```
