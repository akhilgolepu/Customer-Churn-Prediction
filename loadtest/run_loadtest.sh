#!/usr/bin/env bash
# Thin wrapper kept for compatibility; the implementation is `python tasks.py loadtest`
# (cross-platform: starts the API on a fresh SQLite DB with the limiter off, warms it
# up, runs Locust, stops the API and its workers).
# Usage: loadtest/run_loadtest.sh [users] [spawn_rate] [duration]   (WORKERS=2 for two workers)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "${PYTHON:-python}" "$ROOT/tasks.py" loadtest --users "${1:-20}" --spawn-rate "${2:-5}"   --duration "${3:-60s}" --workers "${WORKERS:-1}"
