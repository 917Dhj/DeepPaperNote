#!/usr/bin/env python3
"""Create or update central term-library Markdown notes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from glossary_common import emit, maybe_load_json_record, normalize_whitespace
from glossary_contracts import (
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_DISCLAIMER,
    GLOSSARY_OCCURRENCE_HEADING,
    GLOSSARY_TERM_TAG,
)

ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "write glossary terms")
    p.add_argument("--glossary", required=True, help="Glossary JSON path or JSON object.")
    p.add_argument("--terms-dir", required=True, help="Destination central term folder.")
    p.add_argument("--paper-link", required=True, help="Paper note stem for backlink lines.")
    p.add_argument("--output", default="", help="Output JSON status path.")
    return p


def safe_term_filename(name: str) -> str:
    cleaned = ILLEGAL_FILENAME_CHARS.sub(" ", name)
    cleaned = normalize_whitespace(cleaned).strip(" .")
    return cleaned or "term"


def _unique_term_path(terms_dir: Path, stem: str) -> Path:
    path = terms_dir / f"{stem}.md"
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = terms_dir / f"{stem}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def _alias_forms(entry: dict[str, Any]) -> list[str]:
    forms = [normalize_whitespace(str(entry.get("name", "")))]
    aliases = entry.get("aliases", [])
    if isinstance(aliases, list):
        forms.extend(normalize_whitespace(str(alias)) for alias in aliases)
    seen: set[str] = set()
    ordered: list[str] = []
    for form in forms:
        key = form.lower()
        if form and key not in seen:
            seen.add(key)
            ordered.append(form)
    return ordered


def _read_frontmatter_aliases(text: str) -> list[str]:
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    block = text[3:end]
    inline = re.search(r"(?m)^aliases:\s*\[(.*?)\]\s*$", block)
    if inline:
        return [
            normalize_whitespace(item).strip("\"'")
            for item in inline.group(1).split(",")
            if item.strip()
        ]
    aliases: list[str] = []
    in_block = False
    for line in block.splitlines():
        if re.match(r"^aliases:\s*$", line):
            in_block = True
            continue
        if in_block:
            item = re.match(r"^\s*-\s*(.+?)\s*$", line)
            if item:
                aliases.append(normalize_whitespace(item.group(1)).strip("\"'"))
            elif line.strip() and not line.startswith(" "):
                break
    return aliases


def build_alias_index(terms_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not terms_dir.is_dir():
        return index
    for path in sorted(terms_dir.glob("*.md")):
        keys = {path.stem.lower()}
        try:
            keys.update(
                alias.lower()
                for alias in _read_frontmatter_aliases(path.read_text(encoding="utf-8-sig"))
            )
        except OSError:
            pass
        for key in keys:
            index.setdefault(key, path)
    return index


def _concept_zone(entry: dict[str, Any]) -> list[str]:
    lines = [f"## {GLOSSARY_CONCEPT_HEADING}", f"- 定义：{entry.get('definition', '')}"]
    for label, key in (("详解", "elaboration"), ("直觉", "intuition"), ("与相邻概念的区别", "distinction")):
        value = normalize_whitespace(str(entry.get(key, "")))
        if value:
            lines.append(f"- {label}：{value}")
    lines.append(f"- 置信度：{entry.get('confidence', '')}")
    return lines


def occurrence_line(entry: dict[str, Any], paper_link: str) -> str:
    note = normalize_whitespace(str(entry.get("occurrence", "")))
    suffix = f"：{note}" if note else ""
    return f"- [[{paper_link}]]{suffix}"


def render_term_file(entry: dict[str, Any], paper_link: str) -> str:
    name = normalize_whitespace(str(entry.get("name", "")))
    aliases = [alias for alias in _alias_forms(entry) if alias.lower() != name.lower()]
    front = ["---", "aliases:"]
    front.extend(f"  - {alias}" for alias in aliases)
    front.extend([f"tags: [{GLOSSARY_TERM_TAG}]", "---", ""])
    body = [f"# {name}", "", GLOSSARY_DISCLAIMER, ""]
    body.extend(_concept_zone(entry))
    body.extend(["", f"## {GLOSSARY_OCCURRENCE_HEADING}", occurrence_line(entry, paper_link), ""])
    return "\n".join(front + body)


def append_occurrence(text: str, entry: dict[str, Any], paper_link: str) -> str:
    if f"[[{paper_link}]]" in text:
        return text
    line = occurrence_line(entry, paper_link)
    heading = f"## {GLOSSARY_OCCURRENCE_HEADING}"
    if heading in text:
        return text.rstrip("\n") + "\n" + line + "\n"
    return text.rstrip("\n") + f"\n\n{heading}\n{line}\n"


def upsert_term_file(
    entry: dict[str, Any], paper_link: str, terms_dir: Path, index: dict[str, Path]
) -> dict[str, Any]:
    existing = None
    for form in _alias_forms(entry):
        existing = index.get(form.lower())
        if existing is not None:
            break
    if existing is not None and existing.is_file():
        text = existing.read_text(encoding="utf-8-sig")
        updated = append_occurrence(text, entry, paper_link)
        if updated != text:
            existing.write_text(updated, encoding="utf-8")
        return {
            "name": entry.get("name", ""),
            "file": str(existing),
            "action": "updated" if updated != text else "unchanged",
            "link_stem": existing.stem,
        }

    name = normalize_whitespace(str(entry.get("name", "")))
    terms_dir.mkdir(parents=True, exist_ok=True)
    path = _unique_term_path(terms_dir, safe_term_filename(name))
    path.write_text(render_term_file(entry, paper_link), encoding="utf-8")
    for form in _alias_forms(entry):
        index.setdefault(form.lower(), path)
    index.setdefault(path.stem.lower(), path)
    return {"name": name, "file": str(path), "action": "created", "link_stem": path.stem}


def main() -> None:
    args = parser().parse_args()
    glossary = maybe_load_json_record(args.glossary)
    if glossary is None:
        raise SystemExit(f"Expected JSON object or JSON file path for --glossary: {args.glossary}")
    entries = glossary.get("entries", [])
    if not isinstance(entries, list):
        raise SystemExit("Glossary 'entries' must be a list.")

    terms_dir = Path(args.terms_dir).expanduser().resolve()
    index = build_alias_index(terms_dir)
    results = [
        upsert_term_file(entry, args.paper_link, terms_dir, index)
        for entry in entries
        if isinstance(entry, dict) and normalize_whitespace(str(entry.get("name", "")))
    ]
    emit(
        {
            "status": "ok",
            "script": "write_glossary_terms.py",
            "terms_dir": str(terms_dir),
            "paper_link": args.paper_link,
            "results": results,
            "links": [f"[[{result['link_stem']}]]" for result in results],
        },
        args.output,
    )


if __name__ == "__main__":
    main()
