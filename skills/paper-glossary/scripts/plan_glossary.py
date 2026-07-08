#!/usr/bin/env python3
"""Propose glossary candidates and triage selected terms from raw paper sections."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from glossary_common import emit, maybe_load_json_record, normalize_whitespace

NON_EVIDENCE_SECTION_KINDS = frozenset({"references"})
SNIPPET_RADIUS = 70
MAX_ANCHORS_PER_TERM = 3
MAX_CANDIDATES = 60

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[+\-][A-Za-z0-9]+)*")
CANDIDATE_STOPWORDS = frozenset({"ID", "OK", "OOD", "DOI", "URL", "PDF"})
PAREN_EXPANSION_RE = re.compile(
    r"([A-Z][A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]+){0,4})\s*\(([A-Za-z][A-Za-z-]+?)s?\)"
)
TITLECASE_RE = re.compile(r"[A-Z][a-z]{2,}(?:[ -][A-Z][a-z]+){1,3}")
KEYWORDS_LINE_RE = re.compile(r"(?im)^[ \t]*(?:keywords|关键词)[ \t]*[:：·]?[ \t]*(.+)$")
GREEK_RE = re.compile(r"[α-ωΑ-Ω]")
TITLECASE_STOP_HEADS = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "We",
        "Our",
        "In",
        "On",
        "For",
        "As",
        "At",
        "By",
        "To",
        "It",
        "Its",
        "If",
        "When",
        "While",
        "However",
        "Moreover",
        "Specifically",
        "Following",
        "Given",
        "Since",
        "Thus",
        "Table",
        "Figure",
        "Fig",
        "Section",
        "Center",
        "Centers",
        "Hospital",
        "Both",
        "Each",
    }
)
CATEGORY_ORDER = {
    "keyword": 0,
    "full-name": 1,
    "acronym-or-model": 2,
    "term-phrase": 3,
    "symbol": 4,
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan glossary")
    p.add_argument("--propose", action="store_true", help="List candidate glossary terms.")
    p.add_argument(
        "--terms",
        default="",
        help="Selected terms as JSON list, file path, comma/newline string, or pipe aliases.",
    )
    p.add_argument("--source-manifest", required=True, help="Manifest JSON path or JSON object.")
    p.add_argument(
        "--raw-sections",
        default="",
        help="Raw sections JSONL path. Defaults to manifest raw_sections_path.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def load_terms(value: str) -> list[str]:
    raw = value.strip()
    parsed = _maybe_json_list(raw)
    if parsed is not None:
        return _clean_terms(parsed)
    path = Path(raw).expanduser()
    if path.exists() and path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        parsed = _maybe_json_list(text.strip())
        if parsed is not None:
            return _clean_terms(parsed)
        return _clean_terms(re.split(r"[\r\n]+", text))
    return _clean_terms(re.split(r"[,\r\n]+", raw))


def _maybe_json_list(text: str) -> list[Any] | None:
    if not text.startswith("["):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _clean_terms(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for item in items:
        term = normalize_whitespace(str(item))
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def load_record(value: str) -> dict[str, Any]:
    record = maybe_load_json_record(value)
    if record is not None:
        return record
    raise SystemExit(f"Expected JSON object or JSON file path for {value!r}.")


def read_raw_sections(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("record_type", "section") == "section":
            records.append(record)
    return records


def load_manifest_and_sections(
    source_manifest: str, raw_sections: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_record(source_manifest)
    raw_path = _resolve_raw_path(manifest, raw_sections)
    return manifest, read_raw_sections(raw_path)


def _resolve_raw_path(manifest: dict[str, Any], explicit: str) -> Path:
    raw_path_value = explicit or str(manifest.get("raw_sections_path", ""))
    if not raw_path_value:
        raise SystemExit("Pass --raw-sections or use a manifest with raw_sections_path.")
    raw_path = Path(raw_path_value).expanduser()
    if not raw_path.is_file():
        raise SystemExit(f"Raw sections file not found: {raw_path}")
    return raw_path


def _evidence_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if str(record.get("kind", "")) not in NON_EVIDENCE_SECTION_KINDS
    ]


def _term_pattern(term: str) -> re.Pattern[str]:
    if re.fullmatch(r"[\x00-\x7f]+", term):
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(term), re.IGNORECASE)


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - SNIPPET_RADIUS)
    right = min(len(text), end + SNIPPET_RADIUS)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return prefix + normalize_whitespace(text[left:right]) + suffix


def find_occurrences(term: str, records: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    pattern = _term_pattern(term)
    total = 0
    anchors: list[dict[str, Any]] = []
    for record in _evidence_records(records):
        text = str(record.get("text", ""))
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        total += len(matches)
        if len(anchors) < MAX_ANCHORS_PER_TERM:
            first = matches[0]
            anchors.append(
                {
                    "section_id": record.get("section_id", ""),
                    "title": record.get("title", ""),
                    "page_start": record.get("page_start"),
                    "page_end": record.get("page_end"),
                    "snippet": _snippet(text, first.start(), first.end()),
                }
            )
    return total, anchors


def triage_terms(terms: list[str], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for raw in terms:
        forms = [form for form in (normalize_whitespace(form) for form in raw.split("|")) if form]
        if not forms:
            continue
        occurrences = 0
        anchors: list[dict[str, Any]] = []
        seen_sections: set[str] = set()
        for form in forms:
            form_occurrences, form_anchors = find_occurrences(form, records)
            occurrences += form_occurrences
            for anchor in form_anchors:
                section_id = str(anchor.get("section_id", ""))
                if section_id not in seen_sections and len(anchors) < MAX_ANCHORS_PER_TERM:
                    seen_sections.add(section_id)
                    anchors.append(anchor)
        found = occurrences > 0
        results.append(
            {
                "term": forms[0],
                "surface_forms": forms,
                "found_in_paper": found,
                "occurrences": occurrences,
                "routing": "anchor_only" if found else "needs_explanation",
                "paper_anchors": anchors,
            }
        )
    return results


def _is_acronym(token: str) -> bool:
    if len(token) < 2 or token in CANDIDATE_STOPWORDS:
        return False
    return sum(1 for ch in token if ch.isupper()) >= 2


def _titlecase_ok(phrase: str) -> bool:
    head = re.split(r"[ -]", phrase, maxsplit=1)[0]
    return head not in TITLECASE_STOP_HEADS


def _extract_keywords(records: list[dict[str, Any]]) -> list[str]:
    for record in records:
        match = KEYWORDS_LINE_RE.search(str(record.get("text", "")))
        if match:
            parts = re.split(r"[·;,、]|\s{2,}", match.group(1))
            return [normalize_whitespace(part) for part in parts if normalize_whitespace(part)]
    return []


def propose_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = _evidence_records(records)
    categories: dict[str, str] = {}

    def add(term: str, category: str) -> None:
        cleaned = normalize_whitespace(term)
        if cleaned and cleaned not in categories:
            categories[cleaned] = category

    for keyword in _extract_keywords(records):
        add(keyword, "keyword")
    for record in evidence:
        for match in PAREN_EXPANSION_RE.finditer(str(record.get("text", ""))):
            if _titlecase_ok(match.group(1)):
                add(match.group(1), "full-name")
            if _is_acronym(match.group(2)):
                add(match.group(2), "acronym-or-model")
    for record in evidence:
        for match in TOKEN_RE.finditer(str(record.get("text", ""))):
            if _is_acronym(match.group(0)):
                add(match.group(0), "acronym-or-model")
    for record in evidence:
        for match in TITLECASE_RE.finditer(str(record.get("text", ""))):
            if _titlecase_ok(match.group(0)):
                add(match.group(0), "term-phrase")
    for record in evidence:
        for match in GREEK_RE.finditer(str(record.get("text", ""))):
            add(match.group(0), "symbol")

    results: list[dict[str, Any]] = []
    for term, category in categories.items():
        occurrences, anchors = find_occurrences(term, records)
        if category == "term-phrase" and occurrences < 2:
            continue
        if occurrences == 0 and category not in ("keyword", "symbol"):
            continue
        anchor = anchors[0] if anchors else {}
        results.append(
            {
                "term": term,
                "category": category,
                "occurrences": occurrences,
                "section_id": anchor.get("section_id", ""),
                "page_start": anchor.get("page_start"),
                "snippet": anchor.get("snippet", ""),
            }
        )
    results.sort(
        key=lambda item: (
            CATEGORY_ORDER.get(str(item["category"]), 9),
            -int(item["occurrences"]),
            str(item["term"]).lower(),
        )
    )
    return results[:MAX_CANDIDATES]


def main() -> None:
    args = parser().parse_args()
    if not args.propose and not args.terms.strip():
        raise SystemExit("plan_glossary.py requires --propose or --terms.")
    manifest, records = load_manifest_and_sections(args.source_manifest, args.raw_sections)
    paper_id = manifest.get("paper_id", "")

    if args.propose:
        candidates = propose_candidates(records)
        emit(
            {
                "status": "ok",
                "script": "plan_glossary.py",
                "mode": "propose",
                "paper_id": paper_id,
                "candidates": candidates,
                "summary": {"total_candidates": len(candidates)},
            },
            args.output,
        )
        return

    triaged = triage_terms(load_terms(args.terms), records)
    anchor_only = sum(1 for item in triaged if item["routing"] == "anchor_only")
    emit(
        {
            "status": "ok",
            "script": "plan_glossary.py",
            "mode": "triage",
            "paper_id": paper_id,
            "terms": triaged,
            "summary": {
                "total": len(triaged),
                "anchor_only": anchor_only,
                "needs_explanation": len(triaged) - anchor_only,
            },
        },
        args.output,
    )


if __name__ == "__main__":
    main()
