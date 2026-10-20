"""Every relative link and #anchor in README.md and docs/*.md must resolve.

The README was restructured into docs/; this keeps links from rotting silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _anchors(md: Path) -> set[str]:
    """GitHub-style heading anchors."""
    anchors = set()
    in_code = False
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code or not line.startswith("#"):
            continue
        text = line.lstrip("#").strip().lower()
        text = re.sub(r"[^\w\- ]", "", text)
        anchors.add(text.replace(" ", "-"))
    return anchors


def _links(md: Path):
    in_code = False
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            yield from LINK.findall(line)


@pytest.mark.parametrize("md", DOCS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_links_resolve(md):
    broken = []
    for target in _links(md):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        dest = md if not path_part else (md.parent / path_part).resolve()
        if not dest.exists():
            broken.append(f"{target} (missing file)")
            continue
        if anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
            broken.append(f"{target} (missing anchor)")
    assert not broken, broken
