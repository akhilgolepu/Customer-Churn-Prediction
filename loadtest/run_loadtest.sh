#!/usr/bin/env bash
# Start the API on a fresh SQLite DB, run the Locust predict test, stop the API.
# Usage: loadtest/run_loadtest.sh [users] [spawn_rate] [duration]
# Example: loadtest/run_loadtest.sh 20 5 60s
set -euo pipefail

USERS="${1:-20}"
RATE="${2:-5}"
DURATION="${3:-60s}"
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"
OUT="$ROOT/loadtest/results"
mkdir -p "$OUT"

export PYTHONPATH="$ROOT"
export SQLITE_PATH="$OUT/loadtest.db"
rm -f "$SQLITE_PATH"
# Disable the per-IP limiter so we measure the model/API, not the limiter.
export PREDICT_RATE_LIMIT_PER_MINUTE=100000000
# Background schedulers are not part of what we are measuring.
export SCHEDULE_RETRAINING_ENABLED=false

"$PY" -m uvicorn app:app --app-dir "$ROOT/backend" --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/system/health" >/dev/null 2>&1; then break; fi
  sleep 1
done

# Warm-up so the first-request cost (lazy imports, SHAP/CatBoost init) is excluded.
for _ in $(seq 1 20); do
  curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/predictions/predict" \
    -H 'Content-Type: application/json' \
    -d '{"MonthlyCharges":70.35,"tenure":2,"TotalCharges":151.65,"SeniorCitizen":0,"Partner":"No","Dependents":"No","PhoneService":"Yes","MultipleLines":"No","InternetService":"Fiber optic","OnlineSecurity":"No","OnlineBackup":"No","DeviceProtection":"No","TechSupport":"No","StreamingTV":"No","StreamingMovies":"No","Contract":"Month-to-month","PaperlessBilling":"Yes","PaymentMethod":"Electronic check"}' >/dev/null
done

"${LOCUST_PYTHON:-$PY}" -m locust -f "$ROOT/loadtest/locust_predict.py" --headless \
  -u "$USERS" -r "$RATE" -t "$DURATION" \
  --host "http://127.0.0.1:$PORT" --csv "$OUT/predict" --only-summary
