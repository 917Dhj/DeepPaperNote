"""Find the vault and read paper notes, tolerantly, for the research-memory skill.

The vault and paper folder come from DeepPaperNote's user configuration
(`~/.deeppapernote/config.json`, or `DEEPPAPERNOTE_CONFIG_PATH`), read as plain
JSON. Explicit arguments win. Nothing here ever fails on one malformed note.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

MEMORY_RELATIVE_PATH = Path("DeepPaperNote") / "research-memory.md"
DEFAULT_PAPERS_DIR = "Research/Papers"
LANGUAGE_ALIASES = {"zh": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN", "en": "en", "en-us": "en"}
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(.*?))?[ \t]*$")
ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.*?)[ \t]*$")
H1_RE = re.compile(r"(?m)^#[ \t]+(.+?)[ \t]*$")


def default_config_path() -> Path:
    override = os.environ.get("DEEPPAPERNOTE_CONFIG_PATH", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".deeppapernote" / "config.json"


def normalize_language(value: object) -> str:
    return LANGUAGE_ALIASES.get(str(value or "").strip().lower(), "zh-CN")


def locate(
    *, vault: str | None = None, papers_dir: str | None = None, config_path: Path | None = None
) -> dict:
    """`{status, vault, papers_dir, language}`; status is ok, needs_vault, or not_a_vault."""
    try:
        config = json.loads(Path(config_path or default_config_path()).read_text(encoding="utf-8-sig"))
        config = config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        config = {}
    chosen = (vault or str(config.get("obsidian_vault") or "")).strip()
    folder = (papers_dir or str(config.get("papers_dir") or "")).strip() or DEFAULT_PAPERS_DIR
    language = normalize_language(config.get("output_language"))
    if not chosen:
        return {"status": "needs_vault", "vault": "", "papers_dir": folder, "language": language}
    root = Path(chosen).expanduser().resolve()
    if not (root / ".obsidian").is_dir():
        return {"status": "not_a_vault", "vault": str(root), "papers_dir": folder, "language": language}
    return {"status": "ok", "vault": str(root), "papers_dir": folder, "language": language}


def memory_path(vault: Path) -> Path:
    return vault / MEMORY_RELATIVE_PATH


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


# --- frontmatter -------------------------------------------------------------


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _flow_list(value: str) -> list[str]:
    items, current, quote = [], [], ""
    for ch in value[1:-1]:
        if quote:
            current.append(ch)
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [item for item in (_unquote(part) for part in items) if item]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """(frontmatter block or None, body)."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    end = re.search(r"^---[ \t]*$", text[4:], flags=re.MULTILINE)
    if end is None:
        return None, text
    return text[4 : 4 + end.start()], text[4 + end.end() :]


def parse_frontmatter(block: str) -> dict[str, str | list[str]]:
    """Top-level scalars and lists; anything unexpected is skipped, never raised."""
    fields: dict[str, str | list[str]] = {}
    current: list[str] | None = None
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = ITEM_RE.match(line)
        if item and current is not None:
            current.append(_unquote(item.group(1)))
            continue
        match = KEY_RE.match(line)
        if match is None:
            current = None
            continue
        key, value = match.group(1), (match.group(2) or "").strip()
        if not value:
            current = []
            fields[key] = current
        elif value.startswith("[") and value.endswith("]") and not value.startswith("[["):
            current = None
            fields[key] = _flow_list(value)
        else:
            current = None
            fields[key] = _unquote(value)
    return fields


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if isinstance(value, str) and value.strip() else []


def link_text(value: str) -> str:
    """`[[target|label]]` -> label, `[[target]]` -> target, plain text unchanged."""
    match = re.fullmatch(r"\[\[([^\[\]]+)\]\]", value.strip())
    if match is None:
        return " ".join(value.split())
    target, _, label = match.group(1).partition("|")
    return " ".join((label or target.split("#", 1)[0]).split())


def h1_title(body: str) -> str:
    match = H1_RE.search(body)
    return " ".join(match.group(1).split()) if match else ""
