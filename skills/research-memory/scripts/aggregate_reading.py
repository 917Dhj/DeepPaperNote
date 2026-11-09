#!/usr/bin/env python3
"""Summarize what the user has read, as evidence for the research-memory interview.

Deterministic counts only: which methods, datasets, tasks, domains, and paper
types the vault's paper notes record, when they were read, and what the user
wrote in their own notes. The interview draws its candidates from this output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import memory_format
from memory_vault import (
    as_list,
    h1_title,
    link_text,
    locate,
    memory_path,
    parse_frontmatter,
    sha256_file,
    split_frontmatter,
)

PROPERTY_FIELDS = ("methods", "datasets", "tasks")
LANG_SUFFIX_RE = re.compile(r"\.(zh-CN|en)$")
MY_NOTES_RE = re.compile(r"(?m)^##[ \t]+(?:我的笔记|My Notes)[ \t]*$")
TAKEAWAYS_RE = re.compile(r"(?m)^##[ \t]+(?:阅读收获|Takeaways)[ \t]*$")
JUDGMENT_RE = re.compile(r"^\s*[-*+]\s+\**((?:判断：|Judgment:).*?)\**\s*$")
GUIDANCE_LINES = {
    "> [!note] 这一节留给你自己：写下你的判断、它和你研究的联系、想验证的点。重新生成这篇笔记时，这一节会原样保留。",
    "> [!note] This section is yours: write down your own judgments, how the paper connects to your "
    "research, and what you want to verify. When this note is regenerated, this section is kept exactly as it is.",
}
MAX_MY_NOTES_CHARS = 1500
RECENT_DAYS = 90
ENOUGH_PAPERS = 5


def _user_notes(body: str) -> str:
    match = MY_NOTES_RE.search(body)
    if match is None:
        return ""
    lines = [line for line in body[match.end() :].splitlines() if line.strip() not in GUIDANCE_LINES]
    return "\n".join(lines).strip()[:MAX_MY_NOTES_CHARS]


def _judgments(body: str) -> list[str]:
    match = TAKEAWAYS_RE.search(body)
    if match is None:
        return []
    section = re.split(r"(?m)^##[ \t]+", body[match.end() :], maxsplit=1)[0]
    return [found.group(1).strip() for line in section.splitlines() if (found := JUDGMENT_RE.match(line))]


def _read_note(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    block, body = split_frontmatter(text)
    if block is None:
        return None
    fields = parse_frontmatter(block)
    if "research-memory" in as_list(fields.get("tags")):
        return None
    return {"path": path, "fields": fields, "body": body}


def _note_language(path: Path) -> str:
    match = LANG_SUFFIX_RE.search(path.stem)
    return match.group(1) if match else ""


def _domain(fields: dict, path: Path, base: Path) -> str:
    for tag in as_list(fields.get("tags")):
        if tag.startswith("papers/") and tag[len("papers/") :].strip():
            return tag[len("papers/") :].strip()
    parts = path.relative_to(base).parts
    return parts[0] if len(parts) > 1 else ""


def _merge(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        if value and value.casefold() not in seen:
            seen[value.casefold()] = value
    return list(seen.values())


def _papers(vault: Path, papers_dir: str, language: str) -> list[dict]:
    base = (vault / papers_dir).resolve()
    if not base.is_dir():
        return []
    memory = memory_path(vault).resolve()
    groups: dict[tuple[Path, str], list[dict]] = {}
    for path in sorted(base.rglob("*.md")):
        if path.resolve() == memory or any(part.startswith(".") for part in path.relative_to(base).parts):
            continue
        note = _read_note(path)
        if note is not None:
            groups.setdefault((path.parent, LANG_SUFFIX_RE.sub("", path.stem)), []).append(note)

    papers = []
    for notes in groups.values():
        chosen = next((note for note in notes if _note_language(note["path"]) == language), notes[0])
        fields = chosen["fields"]
        structured = any("paper_type" in note["fields"] for note in notes) and any(
            field in note["fields"] for note in notes for field in PROPERTY_FIELDS
        )
        read_dates = [str(note["fields"].get("read_date", "")) for note in notes]
        papers.append(
            {
                "target": chosen["path"].stem,
                "title": h1_title(chosen["body"]) or chosen["path"].stem,
                "domain": _domain(fields, chosen["path"], base),
                "paper_type": next(
                    (str(note["fields"]["paper_type"]) for note in notes if note["fields"].get("paper_type")), ""
                ),
                **{
                    field: _merge([link_text(v) for note in notes for v in as_list(note["fields"].get(field))])
                    for field in PROPERTY_FIELDS
                },
                "read_date": next((value for value in read_dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), ""),
                "structured": structured,
                "my_notes": "\n\n".join(text for note in notes if (text := _user_notes(note["body"]))),
                "judgments": [judgment for note in notes for judgment in _judgments(note["body"])],
            }
        )
    return sorted(papers, key=lambda paper: paper["target"])


def _counts(papers: list[dict], values_of) -> list[dict]:
    targets: dict[str, tuple[str, list[str]]] = {}
    for paper in papers:
        for value in values_of(paper):
            label, members = targets.setdefault(value.casefold(), (value, []))
            members.append(paper["target"])
    rows = [{"value": label, "count": len(members), "targets": sorted(members)} for label, members in targets.values()]
    return sorted(rows, key=lambda row: (-row["count"], row["value"].casefold()))


def _memory_state(vault: Path) -> dict:
    path = memory_path(vault)
    state = {"path": str(path), "exists": path.is_file(), "sha256": sha256_file(path)}
    parsed = memory_format.parse(path.read_text(encoding="utf-8")) if path.is_file() else memory_format.parse("")
    return {**state, **parsed}


def aggregate(vault: Path, papers_dir: str, *, language: str, today: str) -> dict:
    vault = Path(vault).resolve()
    papers = _papers(vault, papers_dir, language)
    cutoff = (date.fromisoformat(today) - timedelta(days=RECENT_DAYS)).isoformat()
    by_month: dict[str, int] = {}
    for paper in papers:
        if paper["read_date"]:
            month = paper["read_date"][:7]
            by_month[month] = by_month.get(month, 0) + 1
    recent = sorted(paper["target"] for paper in papers if paper["read_date"] and paper["read_date"] >= cutoff)
    return {
        "status": "ok",
        "vault": str(vault),
        "papers_dir": papers_dir,
        "language": language,
        "today": today,
        "memory": _memory_state(vault),
        "paper_count": len(papers),
        "structured_count": sum(paper["structured"] for paper in papers),
        "legacy_count": sum(not paper["structured"] for paper in papers),
        "legacy_targets": [paper["target"] for paper in papers if not paper["structured"]],
        "enough_reading": len(papers) >= ENOUGH_PAPERS,
        "aggregates": {
            **{field: _counts(papers, lambda paper, f=field: paper[f]) for field in PROPERTY_FIELDS},
            "domains": _counts(papers, lambda paper: [paper["domain"]] if paper["domain"] else []),
            "paper_types": _counts(papers, lambda paper: [paper["paper_type"]] if paper["paper_type"] else []),
            "by_month": dict(sorted(by_month.items())),
            "recent_90_days": {"count": len(recent), "targets": recent},
            "with_my_notes": sorted(paper["target"] for paper in papers if paper["my_notes"]),
        },
        "papers": papers,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="Obsidian vault; defaults to DeepPaperNote's configuration.")
    parser.add_argument("--papers-dir", default="", help="Paper folder inside the vault.")
    parser.add_argument("--language", default="", help="zh-CN or en; defaults to DeepPaperNote's output language.")
    parser.add_argument("--today", default=date.today().isoformat(), help="YYYY-MM-DD, for the recent window.")
    parser.add_argument("--output", default="", help="Write the JSON here instead of stdout.")
    args = parser.parse_args()
    located = locate(vault=args.vault or None, papers_dir=args.papers_dir or None)
    if located["status"] != "ok":
        payload = located
    else:
        language = args.language or located["language"]
        payload = aggregate(Path(located["vault"]), located["papers_dir"], language=language, today=args.today)
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        # ASCII JSON reads back under any console encoding, such as cp1252 on Windows.
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
