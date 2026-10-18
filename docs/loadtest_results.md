# Load test results: `/predict` and `/explain`

Measured with Locust against a local uvicorn process on the final Tier 2 code: calibrated CatBoost
active **and** the logistic-regression challenger in the shadow slot, so every request scores two
models. These numbers describe **this machine only**; re-run before quoting them elsewhere.

```bash
python tasks.py loadtest --users 20 --spawn-rate 5 --duration 60s --workers 1 --explain-weight 0   # predict only
python tasks.py loadtest --users 20 --spawn-rate 5 --duration 60s --workers 1                      # 4 predict : 1 explain
python tasks.py loadtest --users 20 --spawn-rate 5 --duration 60s --workers 2
python tasks.py loadtest --users 100 --spawn-rate 20 --duration 60s --workers 1
python tasks.py loadtest --users 100 --spawn-rate 20 --duration 60s --workers 2
# CSVs: loadtest/results/u<users>_w<workers>_stats.csv
```

## Setup

| Item | Value |
|---|---|
| Hardware | Desktop, Intel Core i5-14400F (16 logical CPUs), 32 GB RAM, Windows 11 |
| Server | `uvicorn`, 1 or 2 workers, Python 3.13, fresh SQLite DB, schedulers off, rate limiter disabled (`PREDICT_RATE_LIMIT_PER_MINUTE=100000000`; with the default 30/min per IP a single-IP test measures the limiter) |
| Load generator | Locust 2.46.7 on the same machine; each user waits 0.05 to 0.2 s between requests |
| Payloads | Real rows sampled from the Telco data (`loadtest/locust_predict.py`; the synthetic CI sample when the CSV is absent) |
| Mix | `--explain-weight 1`: 4 `/predict` : 1 `/explain` (SHAP); `0`: `/predict` only |
| Warm-up | 10 `/predict` + 10 `/explain` per worker before measurement |
| Numbers | From Locust's CSV (`*_stats.csv`), latencies in ms |

## Results

| Users | Workers | Mix | Requests | Failures | Throughput | p50 | p95 | p99 | Max |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 20 | 1 | predict only | 8,022 | 0 | 137.6 req/s | 11 | 22 | 41 | 140 |
| 20 | 1 | 4:1 | 8,011 | 0 | 137.5 req/s | 11 | 25 | 42 | 160 |
| 20 | 2 | 4:1 | 8,211 | 0 | 140.9 req/s | 8 | 18 | 26 | 120 |
| 100 | 1 | 4:1 | 10,353 | 0 | 177.8 req/s | 400 | 600 | 730 | 1,100 |
| 100 | 2 | 4:1 | 16,855 | 0 | 289.9 req/s | 200 | 370 | 470 | 580 |

Per endpoint, 4:1 mix:

| Users | Workers | `/predict` p50 / p95 / p99 | `/explain` p50 / p95 / p99 |
|---:|---:|---|---|
| 20 | 1 | 11 / 25 / 42 | 11 / 24 / 42 |
| 20 | 2 | 8 / 18 / 26 | 10 / 19 / 26 |
| 100 | 1 | 410 / 610 / 730 | 390 / 580 / 710 |
| 100 | 2 | 200 / 370 / 470 | 190 / 350 / 420 |

How to read it:

- **At 20 users the throughput is set by the load generator, not the API.** Each user thinks for
  0.125 s on average, so 20 users cannot send more than about 20 / (0.125 + 0.011) = 147 req/s. That is
  why all three 20-user rows sit at 137 to 141 req/s, and why this table's 20-user row looks like the
  previous version of this file (135 req/s on a 2-vCPU VM): both measured the client, not the server.
  What the 20-user rows do show is latency at a comfortable load.
- **Capacity shows at 100 users**, where the API saturates: about 178 req/s with one worker (requests
  queue, p95 600 ms) and about 290 req/s with two (+63%, p95 370 ms). Both are overloaded at that
  concurrency; size for the throughput, not the 100-user latency.
- **`/explain` costs about the same as `/predict`** here: TreeSHAP on a 299-tree, depth-4 CatBoost model
  is cheap, and both endpoints also pay for feature engineering, the challenger and request handling.
- No request failed in any run.

## Not measured

- Anything over a network or on the deployed host (a free Render instance has far less CPU than this
  desktop), Postgres or Redis under load, or a load generator on a separate machine.
- Memory was not measured in these runs. (The earlier version of this file reported about 320 MB
  resident for one worker on Linux.)
