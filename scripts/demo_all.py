"""End-to-end demo in one command: predict, explain, gate + shadow + rollback, drift.

  1. predict + explain one held-out customer through the API (active CatBoost and the
     standing logistic-regression challenger in shadow);
  2. scripts/demo_shadow_rollback.py: a healthy retrain is shadowed and promoted
     through the validation gate, a degraded one is refused by the gate and then
     rolled back automatically by the canary;
  3. scripts/demo_drift.py: shifted traffic fires the live drift alerts and
     Evidently's tests, and the scheduler enqueues a retraining job.

Steps 2 and 3 run as subprocesses because each configures the API differently
(canary, challenger, scheduler). Everything runs in-process against the real
routes (FastAPI TestClient); nothing is mocked. Writes one transcript.

Usage:
    python scripts/demo_all.py [--out docs/demo_all.md]     # also: python tasks.py demo
Needs data/Telco-Customer-Churn.csv (held-out rows, demo candidates).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "model" / "training"))

_tmp = Path(tempfile.mkdtemp(prefix="churn_demo_all_"))
os.environ.update({
    "SQLITE_PATH": str(_tmp / "demo.db"),
    "SCHEDULE_RETRAINING_ENABLED": "false",
    "CHALLENGER_ENABLED": "true",
    "CANARY_ENABLED": "false",
})


def predict_and_explain() -> tuple[list[str], bool]:
    from fastapi.testclient import TestClient

    from app_factory import create_app
    from common import load_dataset, load_params, three_way_split
    from core.settings import get_settings

    params = load_params()
    ds = load_dataset(params)
    test_idx = three_way_split(ds.y, params).test
    fields = ["MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "Partner", "Dependents", "PhoneService",
              "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
              "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod"]
    row = ds.raw.iloc[test_idx[0]][fields].to_dict()
    row["TotalCharges"] = float(row["TotalCharges"]) if row["TotalCharges"] == row["TotalCharges"] else 0.0
    payload = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
    actual = "churned" if ds.y.iloc[test_idx[0]] == 1 else "stayed"

    lines = ["## 1. Predict and explain one held-out customer", ""]
    with TestClient(create_app()) as client:
        pred = client.post("/api/v1/predictions/predict", json=payload)
        expl = client.post("/api/v1/predictions/explain", json=payload)
    ok = pred.status_code == 200 and expl.status_code == 200
    p = pred.json()
    lines += [
        f"Customer: {payload['Contract']}, tenure {payload['tenure']} months, {payload['InternetService']} internet, "
        f"{payload['PaymentMethod']}, ${payload['MonthlyCharges']:.2f}/month (actually {actual}).",
        "",
        f"- `POST /api/v1/predictions/predict`: HTTP {pred.status_code}; churn probability **{p['probability']:.3f}** "
        f"(calibrated CatBoost), decision at threshold {get_settings().decision_threshold}: "
        f"**{'contact' if p['isChurn'] else 'no action'}**; challenger (logistic regression, shadow) "
        f"{p.get('shadowProbability', float('nan')):.3f}.",
        f"- `POST /api/v1/predictions/explain`: HTTP {expl.status_code}; top drivers (log-odds contributions):",
        "",
        "| Feature | Value | Impact |",
        "|---|---|---:|",
    ]
    lines += [f"| {d['feature']} | {d['value']} | {d['impact']:+.3f} |" for d in expl.json()["top_drivers"][:5]]
    lines.append("")
    return lines, ok


def run_demo(script: str, out: Path) -> tuple[list[str], bool, float]:
    started = time.time()
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "MLFLOW_ALLOW_FILE_STORE": "true"}
    for key in ("SQLITE_PATH", "CHALLENGER_ENABLED", "CANARY_ENABLED", "SCHEDULE_RETRAINING_ENABLED"):
        env.pop(key, None)  # each demo sets its own configuration
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), "--out", str(out)],
                            cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    text = out.read_text(encoding="utf-8") if out.exists() else result.stderr[-2000:]
    body = text.split("\n", 1)[1] if text.startswith("# ") else text  # drop the sub-demo's H1
    passed = result.returncode == 0 and "Result: **PASS**" in text
    return [body.replace("\n## ", "\n### ")], passed, time.time() - started


def main(out: Path) -> int:
    if not (REPO_ROOT / "data" / "Telco-Customer-Churn.csv").exists():
        sys.exit("data/Telco-Customer-Churn.csv is required (held-out rows, demo candidates).")
    if not (REPO_ROOT / "model" / "artifacts" / "demo" / "demo_candidates.json").exists():
        subprocess.run([sys.executable, str(REPO_ROOT / "model" / "training" / "build_demo_candidates.py")],
                       cwd=REPO_ROOT, check=True, env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})

    started = time.time()
    part1, ok1 = predict_and_explain()
    part2, ok2, t2 = run_demo("demo_shadow_rollback.py", _tmp / "rollback.md")
    part3, ok3, t3 = run_demo("demo_drift.py", _tmp / "drift.md")

    lines = [
        "# End-to-end demo",
        "",
        "Generated by `python scripts/demo_all.py` (or `python tasks.py demo`). Everything goes through the "
        "API's real routes (FastAPI TestClient), with held-out rows of the Telco data; nothing is mocked.",
        "",
        "| Step | Result |",
        "|---|---|",
        f"| 1. Predict + explain | {'PASS' if ok1 else 'FAIL'} |",
        f"| 2. Gate, shadow, canary rollback | {'PASS' if ok2 else 'FAIL'} ({t2:.0f} s) |",
        f"| 3. Drift alert and retraining trigger | {'PASS' if ok3 else 'FAIL'} ({t3:.0f} s) |",
        "",
        f"Total {time.time() - started:.0f} s.",
        "",
        *part1,
        "## 2. Validation gate, shadow, canary rollback",
        "",
        *part2,
        "",
        "## 3. Drift alert and retraining trigger",
        "",
        *part3,
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    ok = ok1 and ok2 and ok3
    print("\n".join(lines[:12]))
    print(f"\nTranscript: {out}  ->  {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "demo_all.md")
    sys.exit(main(ap.parse_args().out))
