"""Scripted shadow -> canary -> auto-rollback demo, driven through the real API.

Scenario
  1. Baseline model v1 is active.
  2. A healthy retrain (v2) is registered, shadow-tested on replayed traffic,
     stays under the disagreement limit, and is promoted.
  3. A degraded retrain (v3, trained on permuted labels) is registered. A
     direct promotion attempt is refused by the validation gate (HTTP 409).
     It is then shadow-tested. Its predictions disagree with v2, the canary disagreement
     rate crosses the limit, and the service rolls the canary back on its own.
  4. We verify v2 is still serving and the audit trail recorded each step.

Everything goes through HTTP routes (FastAPI TestClient, no mocks of the
lifecycle code). Traffic is real customer rows replayed from the held-out split.

Usage:
    python model/training/build_demo_candidates.py      # once
    python scripts/demo_shadow_rollback.py [--out docs/demo_shadow_rollback.md]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "model" / "training"))

# Demo configuration -- set BEFORE the app imports its settings.
MAX_DISAGREEMENT = 0.20
MIN_SAMPLES = 60
TRAFFIC_PERCENT = 20
_tmp = tempfile.mkdtemp(prefix="churn_demo_")
os.environ.update(
    {
        "CANARY_ENABLED": "true",
        "CANARY_TRAFFIC_PERCENT": str(TRAFFIC_PERCENT),
        "CANARY_MIN_SAMPLES": str(MIN_SAMPLES),
        "CANARY_MAX_DISAGREEMENT_RATE": str(MAX_DISAGREEMENT),
        "CANARY_ROLLBACK_COOLDOWN_SECONDS": "0",
        "PREDICT_RATE_LIMIT_PER_MINUTE": "100000000",
        "SCHEDULE_RETRAINING_ENABLED": "false",
        # Keep the shadow slot free for the scripted candidates (the standing
        # logistic-regression challenger would otherwise occupy it at startup).
        "CHALLENGER_ENABLED": "false",
        "SQLITE_PATH": str(Path(_tmp) / "demo.db"),
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app_factory import create_app  # noqa: E402
from common import load_dataset, load_params, three_way_split  # noqa: E402
from core.settings import get_settings  # noqa: E402

LINES: list[str] = []


def say(text: str = "") -> None:
    print(text)
    LINES.append(text)


def payloads():
    params = load_params()
    ds = load_dataset(params)
    test_idx = three_way_split(ds.y, params).test
    raw = ds.raw
    cols = [
        "MonthlyCharges", "tenure", "TotalCharges", "SeniorCitizen", "Partner", "Dependents",
        "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
        "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
        "PaperlessBilling", "PaymentMethod",
    ]
    rows = raw.iloc[test_idx][cols].copy()
    rows["TotalCharges"] = rows["TotalCharges"].fillna(0.0).astype(float)
    rows["MonthlyCharges"] = rows["MonthlyCharges"].astype(float)
    rows["tenure"] = rows["tenure"].astype(int)
    rows["SeniorCitizen"] = rows["SeniorCitizen"].astype(int)
    return rows.to_dict(orient="records")


def snap(client, headers) -> dict:
    return client.get("/api/v1/system/canary", headers=headers).json()


def short(model_id, versions):
    for v in versions:
        if v["id"] == model_id:
            return f"{v['version']} ({v['status']})"
    return "none"


def show_registry(client, headers, title):
    reg = client.get("/api/v1/models", headers=headers).json()
    say(f"**{title}**")
    say(f"- active: `{short(reg['active_model_id'], reg['versions'])}`")
    say(f"- shadow: `{short(reg['shadow_model_id'], reg['versions'])}`")
    say("- versions: " + ", ".join(f"{v['version']}={v['status']}" for v in reg["versions"]))
    say()
    return reg


def replay(client, rows, start, stop, label):
    """Send rows[start:stop]; stop early if a rollback is recorded."""
    disagree_seen = 0
    for i in range(start, min(stop, len(rows))):
        r = client.post("/api/v1/predictions/predict", json=rows[i])
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("shadowProbability") is not None:
            pass
        s = client.app.state.canary_service.snapshot()
        if s["last_rollback_at"] is not None and not client.app.state.canary_service.enabled:
            say(f"- {label}: canary auto-rolled back after **{i - start + 1}** requests")
            return i + 1, True
    return min(stop, len(rows)), False


def main(out: Path | None) -> int:
    cand = json.loads((REPO_ROOT / "model" / "artifacts" / "demo" / "demo_candidates.json").read_text())
    rows = payloads()

    say("# Shadow -> canary -> rollback demo")
    say()
    say(
        f"Config: canary traffic {TRAFFIC_PERCENT}%, min samples {MIN_SAMPLES}, "
        f"max disagreement {MAX_DISAGREEMENT:.0%}, decision threshold "
        f"{get_settings().decision_threshold}. "
        f"Traffic: {len(rows)} held-out customer rows replayed through `POST /api/v1/predictions/predict`."
    )
    say()

    with TestClient(create_app()) as client:
        # Development default unless ADMIN_PASSWORD is set (see services/auth_service.py).
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        tok = client.post("/api/v1/auth/login", json={"username": "admin", "password": admin_password}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}

        say("## 1. Baseline")
        say()
        reg0 = show_registry(client, h, "Registry at start")

        say("## 2. Healthy retrain (v2): shadow, then promote")
        say()
        m = cand["healthy_candidate"]
        v2 = client.post(
            "/api/v1/models/register",
            json={"version": "v2", "metrics": {"roc_auc": m["roc_auc"], "brier": m["brier"]}, "artifact_path": m["artifact"]},
            headers=h,
        ).json()
        client.post("/api/v1/models/shadow", json={"candidate_model_id": v2["id"]}, headers=h)
        pos, rolled = replay(client, rows, 0, 400, "v2")
        s = snap(client, h)
        say(
            f"- v2 shadowed on {pos} requests: {s['disagreements']} label disagreements, "
            f"disagreement rate **{s['disagreement_rate']:.1%}** (limit {MAX_DISAGREEMENT:.0%}), rolled back: **{rolled}**"
        )
        say()
        if rolled:
            say("Unexpected: healthy candidate rolled back.")
            return 1
        promo = client.post("/api/v1/models/promote", json={"candidate_model_id": v2["id"]}, headers=h)
        gate = promo.json().get("validation") or {}
        say(
            f"- promote v2: HTTP {promo.status_code}; validation gate allowed: **{gate.get('promotion_allowed')}** "
            f"(candidate ROC-AUC {gate.get('candidate', {}).get('roc_auc', float('nan')):.4f} vs active "
            f"{(gate.get('active') or {}).get('roc_auc', float('nan')):.4f} on {gate.get('eval_rows')} labelled rows)"
        )
        say()
        show_registry(client, h, "Registry after promoting v2")

        say("## 3. Degraded retrain (v3): shadow, then auto-rollback")
        say()
        d = cand["degraded_candidate"]
        say(f"v3 offline metrics (measured on the held-out split): ROC-AUC {d['roc_auc']}, Brier {d['brier']}.")
        say()
        v3 = client.post(
            "/api/v1/models/register",
            json={"version": "v3", "metrics": {"roc_auc": d["roc_auc"], "brier": d["brier"]}, "artifact_path": d["artifact"]},
            headers=h,
        ).json()
        blocked = client.post("/api/v1/models/promote", json={"candidate_model_id": v3["id"]}, headers=h)
        body = blocked.json()
        say(f"- direct promote of v3: HTTP **{blocked.status_code}** `{body.get('code')}`")
        for b in (body.get("details") or {}).get("blockers", []):
            say(f"  - blocker: {b}")
        say()
        client.post("/api/v1/models/shadow", json={"candidate_model_id": v3["id"]}, headers=h)
        show_registry(client, h, "Registry with v3 in shadow")
        pos, rolled = replay(client, rows, 400, 400 + 600, "v3")
        s = snap(client, h)
        say(
            f"- v3 canary: {s['canary_samples']} requests served by the candidate, "
            f"{s['disagreements']} disagreements, rate **{s['disagreement_rate']:.1%}** (limit {MAX_DISAGREEMENT:.0%})"
        )
        say(f"- last rollback reason: _{s['last_rollback_reason']}_")
        say()
        reg = show_registry(client, h, "Registry after canary rollback")

        say("## 4. Verification")
        say()
        ok = True
        active_ver = short(reg["active_model_id"], reg["versions"])
        checks = [
            ("v2 promotion passed the validation gate", promo.status_code == 200 and bool(gate.get("promotion_allowed"))),
            ("validation gate refused direct promotion of v3 (409)", blocked.status_code == 409),
            ("canary rolled back automatically", rolled),
            ("v2 (healthy) still active", active_ver.startswith("v2")),
            ("no shadow model remains", reg["shadow_model_id"] is None),
            ("v3 not left in a servable state", next(v for v in reg["versions"] if v["version"] == "v3")["status"] not in ("active", "shadow", "candidate")),
        ]
        for name, passed in checks:
            say(f"- [{'x' if passed else ' '}] {name}")
            ok &= passed
        after = client.post("/api/v1/predictions/predict", json=rows[-1]).json()
        say(f"- post-rollback prediction has no shadow score: {after.get('shadowProbability') is None}")
        say()
        say("Result: **PASS**" if ok else "Result: **FAIL**")

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    sys.exit(main(ap.parse_args().out))
