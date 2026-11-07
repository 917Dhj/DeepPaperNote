"""Shared helpers for the organize-wiki tests."""

from __future__ import annotations

from pathlib import Path

PAPERS = "Research/Papers"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def note_text(title: str, tags: list[str] | None, body: str = "Body.\n") -> str:
    if tags is None:
        return f"# {title}\n\n{body}"
    lines = "".join(f"  - {tag}\n" for tag in tags)
    return f"---\ntags:\n{lines}aliases:\n  - {title}\n---\n\n# {title}\n\n## 摘要\n\n{title} abstract.\n\n## 正文\n\n{body}"


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".obsidian" not in path.parts and path.name != ".deeppapernote.lock"
    }
