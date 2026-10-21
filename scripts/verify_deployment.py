"""End-to-end smoke test for a deployed backend (stdlib only, no installs).

    python scripts/verify_deployment.py https://your-api.onrender.com \
        --origin https://your-app.vercel.app

Checks, in order, and exits non-zero on the first failure:
  1. GET  /api/v1/system/health            service is up
  2. GET  /api/v1/system/ready             model + dependencies loaded
  3. OPTIONS /api/v1/predictions/predict   CORS preflight allows --origin
  4. POST /api/v1/auth/login               demo login works (viewer by default)
  5. POST /api/v1/predictions/predict      returns a probability in [0, 1]
  6. POST /api/v1/predictions/explain      returns SHAP drivers
  7. GET  /api/v1/predictions/history      authenticated route works

Free Render instances sleep when idle and can take a minute or more to wake, so the
health check is retried for up to --wake seconds (default 180) before it fails; every
other request uses --timeout. A timeout or refused connection is reported as FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

SAMPLE = {
    "MonthlyCharges": 70.35, "tenure": 2, "TotalCharges": 151.65, "SeniorCitizen": 0,
    "Partner": "No", "Dependents": "No", "PhoneService": "Yes", "MultipleLines": "No",
    "InternetService": "Fiber optic", "OnlineSecurity": "No", "OnlineBackup": "No",
    "DeviceProtection": "No", "TechSupport": "No", "StreamingTV": "No", "StreamingMovies": "No",
    "Contract": "Month-to-month", "PaperlessBilling": "Yes", "PaymentMethod": "Electronic check",
}


def call(method, url, body=None, headers=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                parsed = json.loads(raw) if raw else None
            except ValueError:
                parsed = raw  # e.g. the plain-text "OK" body of a CORS preflight
            return resp.status, dict(resp.headers), parsed, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode()[:300], time.perf_counter() - started
    except (urllib.error.URLError, OSError) as exc:  # timeout, refused or reset connection, DNS
        reason = getattr(exc, "reason", exc)
        return None, {}, f"{type(reason).__name__}: {reason}", time.perf_counter() - started


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--origin", help="Frontend origin to test CORS for, e.g. https://your-app.vercel.app")
    ap.add_argument("--user", default="viewer")
    ap.add_argument("--password", default="viewer123")
    ap.add_argument("--timeout", type=int, default=90, help="seconds per request")
    ap.add_argument("--wake", type=int, default=180, help="seconds to keep retrying health while the instance wakes")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    failures = 0

    def check(name, ok, detail=""):
        nonlocal failures
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
        if not ok:
            failures += 1
        return ok

    deadline = time.monotonic() + args.wake
    first = time.perf_counter()
    while True:
        remaining = deadline - time.monotonic()
        status, _, body, _ = call("GET", f"{base}/api/v1/system/health", timeout=max(1, min(args.timeout, remaining)))
        if status == 200 or time.monotonic() >= deadline:
            break
        print(f"  waiting for the instance to wake ({body if status is None else f'HTTP {status}'}) ...", flush=True)
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    took = time.perf_counter() - first
    detail = f"HTTP {status}" if status is not None else str(body)
    if not check("health", status == 200, f"{detail}, {took:.1f}s (includes any cold start)"):
        return 1
    status, _, body, took = call("GET", f"{base}/api/v1/system/ready", timeout=args.timeout)
    if not check("ready", status == 200, f"HTTP {status}, {body}"):
        return 1

    if args.origin:
        status, headers, _, _ = call(
            "OPTIONS",
            f"{base}/api/v1/predictions/predict",
            headers={
                "Origin": args.origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
            timeout=args.timeout,
        )
        allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
        check("CORS preflight", status in (200, 204) and allowed in (args.origin, "*"), f"HTTP {status}, allow-origin={allowed}")

    status, _, body, _ = call("POST", f"{base}/api/v1/auth/login", {"username": args.user, "password": args.password}, timeout=args.timeout)
    if not check("login", status == 200 and isinstance(body, dict) and "access_token" in body, f"HTTP {status}"):
        return 1
    auth = {"Authorization": f"Bearer {body['access_token']}"}

    status, _, body, took = call("POST", f"{base}/api/v1/predictions/predict", SAMPLE, headers=auth, timeout=args.timeout)
    prob = body.get("probability") if isinstance(body, dict) else None
    check("predict", status == 200 and isinstance(prob, float) and 0 <= prob <= 1, f"HTTP {status}, probability={prob}, {took * 1000:.0f} ms")

    status, _, body, _ = call("POST", f"{base}/api/v1/predictions/explain", SAMPLE, headers=auth, timeout=args.timeout)
    drivers = body.get("top_drivers") if isinstance(body, dict) else None
    check("explain", status == 200 and bool(drivers), f"HTTP {status}, top driver={drivers[0]['feature'] if drivers else None}")

    status, _, body, _ = call("GET", f"{base}/api/v1/predictions/history", headers=auth, timeout=args.timeout)
    check("history (auth)", status == 200 and isinstance(body, dict) and body.get("total", 0) >= 1, f"HTTP {status}")

    print("\nALL CHECKS PASSED" if not failures else f"\n{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
