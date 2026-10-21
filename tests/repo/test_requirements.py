"""requirements.txt is the single dependency file (API image, CI, training, dev).

Every third-party package the code imports must be declared in it with an exact
pin, so the image cannot run a package the tests never installed explicitly.
"""

from __future__ import annotations

import ast
import re
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_DIRS = ("backend", "ml", "scripts", "loadtest", "tests")
LOCAL = {"backend", "ml", "app", "app_factory", "core", "db", "middleware", "repositories", "routers",
         "schemas", "services", "storage", "tests", "conftest", "model_loader", "feature_engineering", "schema",
         "common", "train", "evaluate", "dataset_registry", "preprocessing", "pipeline_bundle", "tasks"}
# Imported lazily, only when an S3 / Azure model store is configured; not installed by default.
OPTIONAL = {"boto3", "azure"}


def _declared() -> dict[str, str]:
    pins = {}
    for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, _, version = line.partition("==")
            pins[re.sub(r"[-_.]+", "-", re.sub(r"\[.*\]", "", name)).lower()] = version
    return pins


def _imported_modules() -> set[str]:
    mods = set()
    for d in CODE_DIRS:
        for path in (REPO_ROOT / d).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    mods.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods.add(node.module.split(".")[0])
    return mods - set(sys.stdlib_module_names) - LOCAL - OPTIONAL - {"__future__"}


def test_every_requirement_is_pinned_exactly():
    loose = [name for name, version in _declared().items() if not version]
    assert not loose, f"unpinned: {loose}"


def test_every_imported_package_is_declared():
    dists = packages_distributions()
    declared = set(_declared())
    missing = {}
    for mod in sorted(_imported_modules()):
        names = {re.sub(r"[-_.]+", "-", d).lower() for d in dists.get(mod, [mod])}
        if not names & declared:
            missing[mod] = sorted(names)
    assert not missing, f"imported but not in requirements.txt: {missing}"
