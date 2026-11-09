from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    return root


@pytest.fixture
def note(vault: Path) -> Callable[..., Path]:
    """Write a paper note under <vault>/Papers/<rel_dir>/<stem>.md."""

    def write(rel_dir: str, stem: str, *, title: str, frontmatter: str = "", body: str = "") -> Path:
        path = vault / "Papers" / rel_dir / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{frontmatter}---\n\n# {title}\n\n{body}", encoding="utf-8")
        return path

    return write
