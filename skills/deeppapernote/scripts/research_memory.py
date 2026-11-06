"""Read the user's research directions from the research-memory skill's file.

The file is `<vault>/DeepPaperNote/research-memory.md`; its format is defined in
`skills/research-memory/references/file-contract.md`. DeepPaperNote reads only
the top-level items of My Research Directions, each with its indented details,
and never writes the file. Anything unreadable counts as no memory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _note_paths import configured_obsidian_vault

MEMORY_RELATIVE_PATH = Path("DeepPaperNote") / "research-memory.md"
DIRECTION_HEADINGS = {"我的研究方向", "my research directions"}
HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
ITEM_RE = re.compile(r"^[-*+][ \t]+(.*\S)[ \t]*$")
DETAIL_RE = re.compile(r"^[ \t]+[-*+][ \t]+(.*\S)[ \t]*$")


def _directions(text: str) -> list[dict[str, Any]]:
    directions: list[dict[str, Any]] = []
    inside = False
    previous_was_item_line = False
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            inside = heading.group(1).casefold() in DIRECTION_HEADINGS and not directions
            previous_was_item_line = False
            continue
        if not inside:
            continue
        item = ITEM_RE.match(line)
        detail = DETAIL_RE.match(line)
        if item:
            directions.append({"text": " ".join(item.group(1).split()), "details": []})
            previous_was_item_line = True
        elif detail and previous_was_item_line and directions:
            directions[-1]["details"].append(" ".join(detail.group(1).split()))
        else:
            previous_was_item_line = False
    return directions


def suggested_direction(directions: list[dict[str, Any]], language: str) -> str:
    """One sentence for `reader_research_direction`."""
    parts = []
    for item in directions:
        details = ("；" if language == "zh-CN" else "; ").join(item["details"])
        if not details:
            parts.append(item["text"])
        elif language == "zh-CN":
            parts.append(f"{item['text']}（{details}）")
        else:
            parts.append(f"{item['text']} ({details})")
    return ("；" if language == "zh-CN" else "; ").join(parts)


def read_research_memory(config: dict[str, Any], language: str) -> dict[str, Any]:
    """`{status, path, directions, suggested_reader_research_direction}`.

    status is ok, missing, empty, or workspace.
    """
    result: dict[str, Any] = {
        "status": "workspace", "path": "", "directions": [], "suggested_reader_research_direction": "",
    }
    try:
        vault = configured_obsidian_vault(config)
    except Exception:
        vault = None
    if vault is None:
        return result
    path = (vault / MEMORY_RELATIVE_PATH).resolve()
    result["path"] = str(path)
    if not path.is_file():
        result["status"] = "missing"
        return result
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        result["status"] = "empty"
        return result
    directions = _directions(text)
    result["status"] = "ok" if directions else "empty"
    result["directions"] = directions
    result["suggested_reader_research_direction"] = suggested_direction(directions, language)
    return result
