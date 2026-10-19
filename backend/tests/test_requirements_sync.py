"""The API image installs requirements-runtime.txt; CI tests requirements.txt.
They must pin the same versions, or production runs code the tests never saw
(Dependabot once bumped only the runtime file)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = re.sub(r"\[.*\]", "", name)  # psycopg[binary] -> psycopg
        pins[re.sub(r"[-_.]+", "-", name).lower()] = version.strip()
    return pins


def test_runtime_pins_match_the_tested_lock():
    lock = _pins(REPO_ROOT / "requirements.txt")
    runtime = _pins(REPO_ROOT / "requirements-runtime.txt")
    missing = sorted(set(runtime) - set(lock))
    mismatched = {name: (runtime[name], lock[name]) for name in runtime if name in lock and runtime[name] != lock[name]}
    assert not missing, f"runtime packages not in requirements.txt: {missing}"
    assert not mismatched, f"runtime vs requirements.txt versions differ: {mismatched}"


def test_dev_requirements_do_not_repin_the_lock():
    lock = _pins(REPO_ROOT / "requirements.txt")
    dev = _pins(REPO_ROOT / "requirements-dev.txt")
    assert not (set(dev) & set(lock)), f"pinned twice: {sorted(set(dev) & set(lock))}"
