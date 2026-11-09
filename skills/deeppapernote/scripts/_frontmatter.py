"""Read the small YAML subset DeepPaperNote notes use for Obsidian properties.

Supported shapes, one key per line at the top level:

    key: scalar
    key: "quoted scalar"
    key: [a, "b, c", "[[Link]]"]
    key:
      - item
      - "[[Link]]"

Anything else (nested maps, orphan list items, duplicate keys) raises
FrontmatterError, so lint fails closed instead of guessing.
"""

from __future__ import annotations

import re

KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*?))?\s*$")
ITEM_RE = re.compile(r"^\s+-\s+(.*?)\s*$|^\s+-\s*$")


class FrontmatterError(ValueError):
    pass


def frontmatter_block(text: str) -> str | None:
    """Return the text between the opening and closing `---` lines, or None."""
    normalized = text.removeprefix("﻿").replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return None
    end = re.search(r"^---[ \t]*$", normalized[4:], flags=re.MULTILINE)
    if end is None:
        raise FrontmatterError("frontmatter is not closed")
    return normalized[4 : 4 + end.start()]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _flow_list(value: str) -> list[str]:
    inner = value[1:-1]
    items: list[str] = []
    current: list[str] = []
    quote = ""
    for ch in inner:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    if quote:
        raise FrontmatterError("unterminated quote in list")
    items.append("".join(current))
    parsed = [_unquote(item) for item in items]
    return [] if parsed == [""] else parsed


def _scalar_or_list(value: str) -> str | list[str]:
    if value.startswith("["):
        if not value.endswith("]") or value.startswith("[["):
            if value.startswith("[[") and value.endswith("]]"):
                return value  # an unquoted wikilink scalar
            raise FrontmatterError(f"unterminated list: {value}")
        return _flow_list(value)
    return _unquote(value)


def parse_frontmatter(text: str) -> dict[str, str | list[str]] | None:
    block = frontmatter_block(text)
    if block is None:
        return None
    fields: dict[str, str | list[str]] = {}
    current_list: list[str] | None = None
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            item = ITEM_RE.match(line)
            if item is None or current_list is None:
                raise FrontmatterError(f"unsupported line: {line.strip()}")
            current_list.append(_unquote(item.group(1) or ""))
            continue
        match = KEY_RE.match(line)
        if match is None:
            raise FrontmatterError(f"unsupported line: {line.strip()}")
        key, value = match.group(1), match.group(2) or ""
        if key in fields:
            raise FrontmatterError(f"duplicate key: {key}")
        if value:
            fields[key] = _scalar_or_list(value)
            current_list = None
        else:
            current_list = []
            fields[key] = current_list
    return fields
