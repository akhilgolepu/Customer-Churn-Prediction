"""scripts/deploy/verify_deployment.py must report an unreachable or silent server as a failure.

A cold Render instance that took longer than the timeout to answer made the
script crash with a TimeoutError traceback instead of printing a FAIL line.
"""

from __future__ import annotations

import importlib.util
import socket
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("verify_deployment", REPO_ROOT / "scripts" / "deploy" / "verify_deployment.py")
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)


_HELD: list = []  # accepted connections stay open (a collected socket would close and abort the request)


def _silent_server() -> tuple[socket.socket, str]:
    """Accepts connections and never answers, like a sleeping instance behind a proxy."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def accept_forever():
        while True:
            try:
                _HELD.append(srv.accept())
            except OSError:  # server closed at the end of the test
                return

    threading.Thread(target=accept_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.getsockname()[1]}"


def test_call_reports_a_timeout_instead_of_raising():
    srv, base = _silent_server()
    try:
        status, headers, body, _ = verify.call("GET", f"{base}/api/v1/system/health", timeout=1)
    finally:
        srv.close()
    assert status is None
    assert headers == {}
    assert "timed out" in body.lower()


def test_main_fails_cleanly_when_the_server_never_answers(monkeypatch, capsys):
    srv, base = _silent_server()
    monkeypatch.setattr("sys.argv", ["verify_deployment.py", base, "--timeout", "1", "--wake", "2"])
    try:
        code = verify.main()
    finally:
        srv.close()
    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] health" in out


def test_main_fails_cleanly_when_nothing_listens(monkeypatch, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]  # closed again: connections are refused
    monkeypatch.setattr("sys.argv", ["verify_deployment.py", f"http://127.0.0.1:{port}", "--timeout", "1", "--wake", "1"])
    assert verify.main() == 1
    assert "[FAIL] health" in capsys.readouterr().out
