from __future__ import annotations

import sys
from pathlib import Path


# Ensure both repository root and backend directory are importable in tests.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

for path in (str(REPO_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)
