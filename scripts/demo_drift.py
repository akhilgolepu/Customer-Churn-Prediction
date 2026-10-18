"""Scripted drift demo, driven through the real API.

  1. Baseline traffic: 300 held-out customer rows replayed through
     POST /api/v1/predictions/predict. The live monitor (GET /system/monitoring)
     shows no alerts and the retraining trigger does nothing.
  2. Shifted traffic: 300 more rows with a deliberate distribution shift
     (tenure x 0.3, MonthlyCharges x 1.3, TotalCharges recomputed). The monitor's
     input and prediction drift alerts fire.
  3. Evidently (services/drift_detector.py) compares the two windows feature by
     feature with statistical tests.
  4. One scheduler poll (SchedulerService.check_retraining_trigger, normally every
     SCHEDULE_RETRAIN_POLL_SECONDS) enqueues a retraining job with reason
     "drift_alert"; the job worker runs it and registers a candidate, which still
     has to pass the promotion gate (auto_promote is off).

Rows come from the held-out test split when the DVC dataset is present,
otherwise from the synthetic CI sample.

Usage:
    python scripts/demo_drift.py [--out docs/demo_drift.md]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "model" / "training"))

_tmp = tempfile.mkdtemp(prefix="churn_drift_demo_")
os.environ.update(
    {
        "SQLITE_PATH": str(Path(_tmp) / "demo.db"),
        "PREDICT_RATE_LIMIT_PER_MINUTE": "100000000",
        "CHALLENGER_ENABLED": "false",
        "SCHEDULE_RETRAINING_ENABLED": "true",
        "SCHEDULE_RETRAIN_COOLDOWN_SECONDS": "0",
        # keep the background loops quiet; the demo calls the trigger itself
        "SCHEDULE_RETRAIN_POLL_SECONDS": "86400",
        "SCHEDULE_QUALITY_CHECK_SECONDS": "86400",
        "SCHEDULE_DRIFT_REPORT_SECONDS": "86400",
        # the retraining job writes its model and bundle here, not into the repo
        "RETRAINING_OUTPUT_DIR": str(Path(_tmp) / "retrained"),
    }
)

import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app_factory  # noqa: E402
from app_factory import create_app  # noqa: E402
from core.settings import get_settings  # noqa: E402
from services.drift_detector import EvidentiallyDriftDetector  # noqa: E402

N_WINDOW = 300
NUMERIC = ["tenure", "MonthlyCharges", "TotalCharges"]
REQUEST_FIELDS = [
    "MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "Partner", "Dependents", "PhoneService",
    "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
    "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod",
]
LINES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    LINES.append(text)


def load_rows() -> tuple[pd.DataFrame, str]:
    full = REPO_ROOT / "data" / "Telco-Customer-Churn.csv"
    if full.exists():
        from common import load_dataset, load_params, three_way_split

        params = load_params()
        ds = load_dataset(params)
        rows = ds.raw.iloc[three_way_split(ds.y, params).test]
        source = "held-out test split of the Telco data"
    else:
        rows = pd.read_csv(REPO_ROOT / "data" / "ci_sample.csv")
        source = "synthetic CI sample (data/ci_sample.csv)"
    rows = rows[REQUEST_FIELDS].copy()
    rows["TotalCharges"] = pd.to_numeric(rows["TotalCharges"], errors="coerce").fillna(0.0)
    return rows.reset_index(drop=True), source


def shift(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["tenure"] = (out["tenure"] * 0.3).round().astype(int)
    out["MonthlyCharges"] = (out["MonthlyCharges"] * 1.3).round(2)
    out["TotalCharges"] = (out["tenure"] * out["MonthlyCharges"]).round(2)
    return out


def replay(client, frame: pd.DataFrame) -> list[float]:
    probs = []
    for record in frame.to_dict(orient="records"):
        payload = {k: (v.item() if hasattr(v, "item") else v) for k, v in record.items()}
        r = client.post("/api/v1/predictions/predict", json=payload)
        assert r.status_code == 200, r.text
        probs.append(r.json()["probability"])
    return probs


def show_monitor(client, headers, title) -> dict:
    snap = client.get("/api/v1/system/monitoring", headers=headers).json()
    say(f"**{title}**")
    say()
    say("| Signal | Older half | Newer half | Relative change | Threshold | Alert |")
    say("|---|---:|---:|---:|---:|---|")
    for row in snap["input_drift"] + [snap["prediction_drift"]]:
        say(f"| {row['metric']} | {row['baseline']:.3f} | {row['recent']:.3f} | {row['delta']:+.3f} | "
            f"{row['threshold']:.2f} | {'**yes**' if row['alert'] else 'no'} |")
    say()
    say(f"Alerts: {snap['alerts'] or 'none'}")
    say()
    return snap


def main(out: Path | None) -> int:
    rows, source = load_rows()
    baseline, shifted = rows.iloc[:N_WINDOW], shift(rows.iloc[N_WINDOW:2 * N_WINDOW])
    s = get_settings()

    say("# Drift demo: shifted traffic -> drift alerts -> retraining trigger")
    say()
    say(f"Traffic: {source}. Windows of {N_WINDOW} requests through `POST /api/v1/predictions/predict`. "
        f"Live monitor thresholds: input drift {s.input_drift_alert_threshold:.2f}, prediction drift "
        f"{s.prediction_drift_alert_threshold:.2f} (relative change of the mean between the older and newer half "
        "of recent predictions).")
    say()

    with TestClient(create_app()) as client:
        tok = client.post("/api/v1/auth/login", json={"username": "admin",
                          "password": os.environ.get("ADMIN_PASSWORD", "admin123")}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        scheduler = app_factory.app_state.scheduler_service
        loop = asyncio.new_event_loop()

        say("## 1. Baseline traffic only")
        say()
        p_base = replay(client, baseline)
        snap0 = show_monitor(client, h, f"Monitor after {N_WINDOW} baseline requests")
        trigger0 = loop.run_until_complete(scheduler.check_retraining_trigger())
        say(f"Scheduler poll: {'no retraining job' if trigger0 is None else trigger0}")
        say()

        say("## 2. Shifted traffic")
        say()
        say("Shift applied to the next window: tenure x 0.3, MonthlyCharges x 1.3, TotalCharges = tenure x "
            "MonthlyCharges (all other fields unchanged, so the rows still pass validation).")
        say()
        p_shift = replay(client, shifted)
        snap1 = show_monitor(client, h, f"Monitor after {N_WINDOW} more, shifted requests")
        say(f"Mean served churn probability: baseline window {sum(p_base) / len(p_base):.3f}, "
            f"shifted window {sum(p_shift) / len(p_shift):.3f}.")
        say()

        say("## 3. Evidently: per-feature drift tests (baseline window vs shifted window)")
        say()
        detector = EvidentiallyDriftDetector(reference_data=baseline, feature_names=REQUEST_FIELDS,
                                             numerical_features=NUMERIC, drift_threshold=0.05)
        report = detector.detect_data_drift(shifted)
        say("| Feature | Test | Score | Threshold | Drift |")
        say("|---|---|---:|---:|---|")
        for col, info in sorted(report.metrics["per_feature"].items(), key=lambda kv: not kv[1]["drift_detected"]):
            say(f"| {col} | {info['test']} | {info['score']:.3g} | {info['threshold']:.2f} | "
                f"{'**yes**' if info['drift_detected'] else 'no'} |")
        say()
        say(f"Drifted features: {report.metrics['n_features_drifted']} of {report.metrics['n_features']} "
            f"(dataset drift: {report.metrics['dataset_drift']}); detector severity: {report.alerts_severity}; "
            f"should_retrain: {detector.should_retrain(report)}.")
        say()

        say("## 4. Retraining trigger")
        say()
        trigger1 = loop.run_until_complete(scheduler.check_retraining_trigger())
        say(f"Scheduler poll: enqueued a retraining job with reason **{trigger1['reason'] if trigger1 else None}**.")
        say()
        job = None
        deadline = time.time() + 300
        while time.time() < deadline:
            jobs = client.get("/api/v1/jobs?job_type=retraining", headers=h).json()
            items = jobs.get("items") or jobs.get("jobs") or []
            job = items[0] if items else None
            if job and job.get("status") in ("completed", "failed"):
                break
            time.sleep(2)
        if job is None:
            say("No retraining job found.")
        else:
            say(f"- retraining job status: **{job.get('status')}** (attempts: {job.get('attempts')})")
            result = job.get("result") or {}
            if result.get("version"):
                gate = (result.get("registry") or {}).get("validation") or {}
                say(f"- candidate `{result['version']}` registered from {result.get('rows_used')} rows; "
                    f"holdout AUC {result.get('metrics', {}).get('auc', float('nan')):.4f}; "
                    f"validation gate allowed: {gate.get('promotion_allowed')}; promoted: {result.get('promoted')}")
            if job.get("error"):
                say(f"- error: {job['error']}")
        say()

        say("## 5. Verification")
        say()
        input_alerts = [r["metric"] for r in snap1["input_drift"] if r["alert"]]
        checks = [
            ("no alerts on baseline-only traffic", not snap0["alerts"]),
            ("no retraining job before the shift", trigger0 is None),
            ("live monitor flags tenure, MonthlyCharges and TotalCharges", {"tenure", "MonthlyCharges", "TotalCharges"} <= set(input_alerts)),
            ("prediction drift alert fires", snap1["prediction_drift"]["alert"]),
            ("Evidently flags the shifted features", {"tenure", "MonthlyCharges", "TotalCharges"} <= set(report.drifted_features)),
            ("drift alert enqueues a retraining job", bool(trigger1) and trigger1["reason"] == "drift_alert"),
        ]
        ok = True
        for name, passed in checks:
            say(f"- [{'x' if passed else ' '}] {name}")
            ok &= bool(passed)
        say()
        say("Result: **PASS**" if ok else "Result: **FAIL**")
        loop.close()

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    sys.exit(main(ap.parse_args().out))
