#!/usr/bin/env python3
"""Best-effort reference extraction and the matching helpers vault_connections uses."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _identity import extract_arxiv_id, extract_doi
from common import fitz, normalize_whitespace


# Up to three digits: a four-digit "2023." opening an author-year line is a year, not a number.
NUMBERED_REF_RE = re.compile(r"^(?:\[(\d{1,3})\]|(\d{1,3})\.)\s+(.+)$")
MAX_ENTRY_CHARS = 1500
REFERENCE_HEADINGS = {"references", "bibliography", "参考文献"}
APPENDIX_HEADING_RE = re.compile(
    r"^(?:appendix|appendices|supplementary|supplemental|附录)\b|^A\.?$", flags=re.IGNORECASE
)
# "Surname, ...", "A B and C", or a single author "First Last. 2020".
AUTHOR_START_RE = re.compile(
    r"^[A-Z\u00C0-\u024F][\w'’.\-]*(?:\s+[A-Z\u00C0-\u024F][\w'’.\-]*){0,3}"
    r"(?:,|\s+and\s|\.\s+(?:19|20)\d{2})"
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", flags=re.IGNORECASE)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*", flags=re.DOTALL)
FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")


def _empty_candidate(raw_text: str, page_hint: str = "") -> dict[str, Any]:
    display_text = _display_text(raw_text)
    return {
        "raw_text": normalize_whitespace(raw_text),
        "display_text": display_text,
        "page_hint": page_hint,
        "doi": extract_doi(raw_text) or "",
        "arxiv_id": extract_arxiv_id(raw_text) or "",
        "wikilink": "",
        "vault_target": "",
        "match_status": "no_vault_match",
        "match_reason": "none",
    }


def _display_text(raw_text: str, *, max_chars: int = 320) -> str:
    text = normalize_whitespace(raw_text)
    text = re.sub(r"^(?:\[\d{1,4}\]|\d{1,4}\.)\s+", "", text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _reference_lines_from_pdf(pdf_path: Path, references_start_page: int, max_pages: int) -> list[tuple[str, int]]:
    """Lines from the References heading up to the first appendix heading."""
    if fitz is None or references_start_page < 1 or max_pages < 1:
        return []
    doc = fitz.open(pdf_path)
    try:
        start_index = max(0, references_start_page - 1)
        stop_index = min(len(doc), start_index + max_pages)
        lines: list[tuple[str, int]] = []
        for page_index in range(start_index, stop_index):
            page_number = page_index + 1
            page_lines = [
                line for raw in doc[page_index].get_text("text").splitlines()
                if (line := normalize_whitespace(raw))
            ]
            if page_index == start_index:
                headings = [i for i, line in enumerate(page_lines) if line.lower() in REFERENCE_HEADINGS]
                if headings:
                    page_lines = page_lines[headings[0] + 1:]
            for line in page_lines:
                if APPENDIX_HEADING_RE.match(line):
                    return lines
                if line.lower() in REFERENCE_HEADINGS:
                    continue
                lines.append((line, page_number))
        return lines
    finally:
        doc.close()


def _group_numbered_references(lines: list[tuple[str, int]]) -> list[tuple[str, int]]:
    grouped: list[tuple[list[str], int]] = []
    current: list[str] = []
    current_page = 0

    for line, page_number in lines:
        if NUMBERED_REF_RE.match(line):
            if current:
                grouped.append((current, current_page))
            current = [line]
            current_page = page_number
            continue
        if current:
            previous = current[-1]
            starts_like_continuation = bool(
                re.match(r"^(?:https?://|doi\b|10\.|[a-z,;:)])", line.strip())
            )
            previous_looks_complete = previous.rstrip().endswith((".", "。", "!", "?", ";"))
            if not previous_looks_complete or starts_like_continuation:
                current.append(line)

    if current:
        grouped.append((current, current_page))

    return [(normalize_whitespace(" ".join(parts)), page_number) for parts, page_number in grouped]


def _group_author_year_references(lines: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Split an unnumbered bibliography where a finished entry meets an author list."""
    grouped: list[tuple[list[str], int]] = []
    for line, page_number in lines:
        current = grouped[-1][0] if grouped else []
        finished = bool(current) and current[-1].rstrip().endswith((".", ")")) and bool(
            YEAR_RE.search(" ".join(current))
        )
        if not current or (finished and AUTHOR_START_RE.match(line)):
            grouped.append(([line], page_number))
        else:
            current.append(line)
    return [(normalize_whitespace(" ".join(parts)), page_number) for parts, page_number in grouped]


def _fallback_year_lines(lines: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return [(line, page_number) for line, page_number in lines if YEAR_RE.search(line)]


def extract_reference_candidates_from_pdf(
    pdf_path: str | Path,
    references_start_page: int | None,
    *,
    max_pages: int = 3,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Extract best-effort reference candidates from the PDF reference section."""
    if references_start_page is None:
        return []
    path = Path(pdf_path).expanduser()
    if not path.is_file():
        return []

    try:
        lines = _reference_lines_from_pdf(path, int(references_start_page), max_pages)
    except Exception:
        return []

    if lines and NUMBERED_REF_RE.match(lines[0][0]):
        references = _group_numbered_references(lines)
    else:
        references = _group_author_year_references(lines)
        if any(len(text) > MAX_ENTRY_CHARS for text, _ in references):
            references = _fallback_year_lines(lines)  # entry boundaries were not found

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_text, page_number in references:
        raw_text = normalize_whitespace(raw_text)
        if not raw_text or raw_text in seen:
            continue
        seen.add(raw_text)
        candidates.append(_empty_candidate(raw_text, page_hint=f"p. {page_number}"))
        if len(candidates) >= max_items:
            break
    return candidates


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _parse_inline_aliases(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
        return [_strip_wrapping_quotes(part) for part in value.split(",") if _strip_wrapping_quotes(part)]
    alias = _strip_wrapping_quotes(value)
    return [alias] if alias else []


def _frontmatter_fields(text: str) -> dict[str, Any] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None

    fields: dict[str, Any] = {"aliases": []}
    lines = match.group(1).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        key_match = FRONTMATTER_KEY_RE.match(stripped)
        if not key_match:
            index += 1
            continue

        key = key_match.group(1).strip().lower().replace("-", "_")
        inline_value = key_match.group(2).strip()
        if key == "aliases":
            if inline_value:
                fields["aliases"] = _parse_inline_aliases(inline_value)
                index += 1
                continue

            aliases: list[str] = []
            index += 1
            while index < len(lines):
                item = lines[index].strip()
                if not item.startswith("- "):
                    break
                alias = _strip_wrapping_quotes(item[2:])
                if alias:
                    aliases.append(alias)
                index += 1
            fields["aliases"] = aliases
            continue

        if key in {"doi", "arxiv", "arxiv_id", "title"} and inline_value:
            fields[key] = _strip_wrapping_quotes(inline_value)
        index += 1

    return fields


def _h1_title(text: str) -> str:
    match = FRONTMATTER_RE.match(text)
    body = text[match.end() :] if match else text
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return normalize_whitespace(stripped[2:].strip().strip("#"))
    return ""


def _normalize_doi(value: str) -> str:
    doi = extract_doi(value) or ""
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def _normalize_arxiv_id(value: str) -> str:
    arxiv_id = extract_arxiv_id(value) or ""
    return re.sub(r"^arxiv:\s*", "", arxiv_id, flags=re.IGNORECASE).strip().lower()


def _short_acronym_like(value: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]", "", value)
    if len(compact) > 6:
        return False
    key = _match_key(value)
    return bool(compact and " " not in key)


def _safe_text_key(value: str) -> str:
    key = normalize_whitespace(value)
    if not key or _short_acronym_like(key):
        return ""
    if len(re.sub(r"\s+", "", _match_key(key))) < 8:
        return ""
    return key


def _candidate_doi(candidate: dict[str, Any], candidate_text: str) -> str:
    return _normalize_doi(str(candidate.get("doi", "")) or candidate_text)


def _candidate_arxiv_ids(candidate: dict[str, Any], candidate_text: str) -> set[str]:
    values = [
        str(candidate.get("arxiv_id", "")),
        str(candidate.get("doi", "")),
        candidate_text,
    ]
    return {_normalize_arxiv_id(value) for value in values if _normalize_arxiv_id(value)}


def _match_key(value: str) -> str:
    text = normalize_whitespace(value).casefold()
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"[^\w\s\u3400-\u9fff]", " ", text, flags=re.UNICODE)
    return normalize_whitespace(text)


def _contains_key(raw_text: str, key: str) -> bool:
    raw_key = _match_key(raw_text)
    needle = _match_key(key)
    if not raw_key or not needle:
        return False
    if re.search(r"[\w]", needle):
        return bool(re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", raw_key))
    return needle in raw_key
