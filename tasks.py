"""Cross-platform task runner (Windows has no make). The Makefile delegates here.

    python tasks.py setup      # .venv + Python deps (+ frontend deps with --frontend)
    python tasks.py test       # backend test suite with coverage
    python tasks.py lint       # ruff + mypy (non-strict, backend/)
    python tasks.py train      # dvc repro: validate -> train -> evaluate -> threshold (needs the dataset)
    python tasks.py demo       # shadow/rollback demo + drift demo, transcripts in docs/
    python tasks.py loadtest [--users 20 --spawn-rate 5 --duration 60s --workers 1 --explain-weight 1]
    python tasks.py up         # docker compose up --build (API :8000, frontend :5173)
    python tasks.py up --observability   # + Prometheus :9090, Grafana :3000
    python tasks.py down

Every task after `setup` uses the interpreter in .venv when it exists. Set
CHURN_NO_VENV=1 to use the current interpreter instead (the devcontainer does:
the repo is bind-mounted, and a host .venv may belong to another OS).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
DATASET = ROOT / "data" / "Telco-Customer-Churn.csv"
NO_VENV = bool(os.environ.get("CHURN_NO_VENV"))


def py() -> str:
    return str(VENV_PY) if VENV_PY.exists() and not NO_VENV else sys.executable


def run(cmd: list[str], env: dict | None = None, cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    merged = {**os.environ, "PYTHONPATH": str(ROOT), "MLFLOW_ALLOW_FILE_STORE": "true", **(env or {})}
    result = subprocess.run(cmd, cwd=cwd, env=merged)
    if result.returncode != 0:
        sys.exit(result.returncode)


def setup(args) -> None:
    if not VENV_PY.exists() and not NO_VENV:
        run([sys.executable, "-m", "venv", str(VENV)])
    run([py(), "-m", "pip", "install", "--upgrade", "pip"])
    run([py(), "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"])
    if args.frontend:
        npm = shutil.which("npm")
        if not npm:
            sys.exit("npm not found; install Node 18+ or run without --frontend")
        run([npm, "ci"], cwd=ROOT / "frontend")
    if not DATASET.exists():
        print("\nNote: data/Telco-Customer-Churn.csv is not present (DVC-tracked, no remote configured).\n"
              "Tests use the committed synthetic sample; `train` and the full demos need the CSV.")


def test(args) -> None:
    run([py(), "-m", "pytest", "-q", "backend/tests", "--disable-warnings", "--cov", "--cov-report=term"])


def lint(args) -> None:
    run([py(), "-m", "ruff", "check", "backend", "model", "scripts", "loadtest"])
    run([py(), "-m", "mypy", "backend"])


def train(args) -> None:
    if not DATASET.exists():
        sys.exit("data/Telco-Customer-Churn.csv is required (place the IBM Telco CSV there).")
    dvc = [py(), "-m", "dvc"]
    run(dvc + ["repro"] + (["-f"] if args.force else []))
    run(dvc + ["metrics", "show"])


def demo(args) -> None:
    if not DATASET.exists():
        sys.exit("The demos replay held-out rows and build candidates from data/Telco-Customer-Churn.csv.")
    run([py(), "model/training/build_demo_candidates.py"])
    run([py(), "scripts/demo_shadow_rollback.py", "--out", "docs/demo_shadow_rollback.md"])
    run([py(), "scripts/demo_drift.py", "--out", "docs/demo_drift.md"])


def _wait_for(url: str, seconds: int = 90) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(1)
    sys.exit(f"{url} did not become ready")


def _stop_tree(proc: subprocess.Popen) -> None:
    """Stop uvicorn and its worker processes. terminate() alone stops only the parent
    on Windows; the orphaned workers kept the port and the output pipe open."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        import signal

        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def loadtest(args) -> None:
    """Start the API (fresh SQLite, limiter off, schedulers off), warm up, run Locust, stop."""
    out = ROOT / "loadtest" / "results"
    out.mkdir(parents=True, exist_ok=True)
    db = out / "loadtest.db"
    db.unlink(missing_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SQLITE_PATH": str(db),
        "PREDICT_RATE_LIMIT_PER_MINUTE": "100000000",
        "SCHEDULE_RETRAINING_ENABLED": "false",
        "EXPLAIN_WEIGHT": str(args.explain_weight),
    }
    if args.workers > 1:
        prom_dir = out / "prometheus_multiproc"
        shutil.rmtree(prom_dir, ignore_errors=True)
        prom_dir.mkdir()
        env["PROMETHEUS_MULTIPROC_DIR"] = str(prom_dir)
    base = f"http://127.0.0.1:{args.port}"
    server = subprocess.Popen(
        [py(), "-m", "uvicorn", "app:app", "--app-dir", "backend", "--host", "127.0.0.1",
         "--port", str(args.port), "--workers", str(args.workers), "--log-level", "warning"],
        cwd=ROOT, env=env,
        start_new_session=(os.name != "nt"),  # own process group, so the whole tree can be stopped
    )
    try:
        _wait_for(f"{base}/api/v1/system/health")
        sample = (b'{"MonthlyCharges":70.35,"tenure":2,"TotalCharges":151.65,"SeniorCitizen":0,"Partner":"No",'
                  b'"Dependents":"No","PhoneService":"Yes","MultipleLines":"No","InternetService":"Fiber optic",'
                  b'"OnlineSecurity":"No","OnlineBackup":"No","DeviceProtection":"No","TechSupport":"No",'
                  b'"StreamingTV":"No","StreamingMovies":"No","Contract":"Month-to-month","PaperlessBilling":"Yes",'
                  b'"PaymentMethod":"Electronic check"}')
        for path in ("predict", "explain") * (10 * args.workers):  # warm every worker's lazy init
            req = urllib.request.Request(f"{base}/api/v1/predictions/{path}", data=sample,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=60).read()
        tag = f"u{args.users}_w{args.workers}"
        run([py(), "-m", "locust", "-f", "loadtest/locust_predict.py", "--headless",
             "-u", str(args.users), "-r", str(args.spawn_rate), "-t", args.duration,
             "--host", base, "--csv", str(out / tag), "--only-summary"], env=env)
        print(f"\nCSV results: loadtest/results/{tag}_stats.csv")
    finally:
        _stop_tree(server)


def up(args) -> None:
    cmd = ["docker", "compose"] + (["--profile", "observability"] if args.observability else []) + ["up", "-d", "--build"]
    run(cmd)
    _wait_for("http://localhost:8000/api/v1/system/health", 180)
    print("API http://localhost:8000/docs  |  frontend http://localhost:5173"
          + ("  |  Grafana http://localhost:3000  |  Prometheus http://localhost:9090" if args.observability else ""))


def down(args) -> None:
    run(["docker", "compose", "--profile", "observability", "--profile", "postgres", "down"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="task", required=True)
    p = sub.add_parser("setup")
    p.add_argument("--frontend", action="store_true", help="also npm ci in frontend/")
    sub.add_parser("test")
    sub.add_parser("lint")
    p = sub.add_parser("train")
    p.add_argument("--force", action="store_true", help="dvc repro -f (rebuild every stage)")
    sub.add_parser("demo")
    p = sub.add_parser("loadtest")
    p.add_argument("--users", type=int, default=20)
    p.add_argument("--spawn-rate", type=int, default=5)
    p.add_argument("--duration", default="60s")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--explain-weight", type=int, default=1, help="explain:predict = weight:4 (0 = predict only)")
    p.add_argument("--port", type=int, default=8001)
    p = sub.add_parser("up")
    p.add_argument("--observability", action="store_true")
    sub.add_parser("down")
    args = parser.parse_args()
    globals()[args.task](args)


if __name__ == "__main__":
    main()
