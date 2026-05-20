#!/usr/bin/env python3
"""Best-effort reference extraction and Obsidian note matching helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from common import configured_obsidian_vault, extract_arxiv_id, extract_doi, fitz, normalize_whitespace


NUMBERED_REF_RE = re.compile(r"^(?:\[(\d{1,4})\]|(\d{1,4})\.)\s+(.+)$")
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
    if fitz is None or references_start_page < 1 or max_pages < 1:
        return []
    doc = fitz.open(pdf_path)
    try:
        start_index = max(0, references_start_page - 1)
        stop_index = min(len(doc), start_index + max_pages)
        lines: list[tuple[str, int]] = []
        for page_index in range(start_index, stop_index):
            page_number = page_index + 1
            for raw_line in doc[page_index].get_text("text").splitlines():
                line = normalize_whitespace(raw_line)
                if not line:
                    continue
                if line.lower() in {"references", "bibliography", "参考文献"}:
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

    references = _group_numbered_references(lines)
    if not references:
        references = _fallback_year_lines(lines)

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


def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = normalize_whitespace(value)
        if not cleaned:
            continue
        folded = cleaned.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        deduped.append(cleaned)
    return deduped


def _note_text_keys(note: dict[str, Any]) -> list[str]:
    values = [
        str(note.get("stem", "")),
        str(note.get("frontmatter_title", "")),
        str(note.get("h1_title", "")),
    ]
    values.extend(str(alias) for alias in note.get("aliases", []) or [])
    keys = [_safe_text_key(value) for value in values]
    return _dedupe_values([key for key in keys if key])


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


def _note_wikilink(target: str, display_text: str) -> str:
    display = normalize_whitespace(display_text)
    if display:
        return f"[[{target}|{display}]]"
    return f"[[{target}]]"


def build_vault_note_index(config: dict[str, Any]) -> dict[str, Any]:
    """Build a limited note index under the configured papers directory."""
    try:
        vault_path = configured_obsidian_vault(config)
    except Exception:
        return {"status": "vault_unavailable", "notes": []}
    if vault_path is None:
        return {"status": "vault_unavailable", "notes": []}

    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    base_dir = (vault_path / Path(papers_dir)).resolve()
    try:
        base_dir.relative_to(vault_path)
    except ValueError:
        return {"status": "vault_unavailable", "notes": []}
    if not base_dir.exists() or not base_dir.is_dir():
        return {"status": "vault_unavailable", "notes": []}

    notes: list[dict[str, Any]] = []
    for path in sorted(base_dir.glob("**/*.md")):
        try:
            relative_path = path.relative_to(vault_path)
        except ValueError:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            text = ""
        frontmatter = _frontmatter_fields(text)
        if frontmatter is None:
            continue
        aliases = frontmatter.get("aliases", [])
        doi = normalize_whitespace(str(frontmatter.get("doi", "")))
        arxiv_id = normalize_whitespace(
            str(frontmatter.get("arxiv_id", "") or frontmatter.get("arxiv", ""))
        )
        normalized_arxiv_ids = {
            _normalize_arxiv_id(value)
            for value in [arxiv_id, doi]
            if _normalize_arxiv_id(value)
        }
        notes.append(
            {
                "stem": path.stem,
                "aliases": aliases if isinstance(aliases, list) else [],
                "frontmatter_title": normalize_whitespace(str(frontmatter.get("title", ""))),
                "h1_title": _h1_title(text),
                "doi": doi,
                "doi_norm": _normalize_doi(doi) if doi else "",
                "arxiv_id": arxiv_id,
                "arxiv_ids": sorted(normalized_arxiv_ids),
                "text_keys": [],
                "vault_target": path.stem,
                "vault_relative_path": str(relative_path),
            }
        )
        notes[-1]["text_keys"] = _note_text_keys(notes[-1])
    return {"status": "ok", "notes": notes}


def resolve_reference_links(candidates: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach exact Obsidian wikilink matches to extracted reference candidates."""
    index = build_vault_note_index(config)
    if index.get("status") != "ok":
        return [
            {
                **candidate,
                "wikilink": "",
                "vault_target": "",
                "match_status": "vault_unavailable",
                "match_reason": "none",
            }
            for candidate in candidates
            if isinstance(candidate, dict)
        ]

    notes = [note for note in index.get("notes", []) if isinstance(note, dict)]

    matched: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw_text = str(candidate.get("raw_text", "") or candidate.get("display_text", ""))
        display_text = normalize_whitespace(str(candidate.get("display_text", ""))) or raw_text
        candidate_text = normalize_whitespace(f"{raw_text} {display_text}")
        resolved = dict(candidate)
        resolved.setdefault("match_status", "no_vault_match")
        resolved.setdefault("match_reason", "none")
        resolved.setdefault("wikilink", "")
        resolved.setdefault("vault_target", "")

        priority_matches: list[tuple[str, list[dict[str, Any]]]] = []
        doi = _candidate_doi(candidate, candidate_text)
        if doi:
            priority_matches.append(
                ("doi", [note for note in notes if doi and doi == str(note.get("doi_norm", ""))])
            )
        arxiv_ids = _candidate_arxiv_ids(candidate, candidate_text)
        if arxiv_ids:
            priority_matches.append(
                (
                    "arxiv_id",
                    [
                        note
                        for note in notes
                        if arxiv_ids.intersection(set(note.get("arxiv_ids", []) or []))
                    ],
                )
            )
        priority_matches.append(
            (
                "basename_or_title_or_alias",
                [
                    note
                    for note in notes
                    if any(
                        _contains_key(candidate_text, key)
                        for key in note.get("text_keys", []) or []
                    )
                ],
            )
        )

        for reason, matches in priority_matches:
            if not matches:
                continue
            if len(matches) == 1:
                target = normalize_whitespace(str(matches[0].get("vault_target", "")))
                resolved["wikilink"] = _note_wikilink(target, display_text)
                resolved["vault_target"] = target
                resolved["match_status"] = "vault_match"
                resolved["match_reason"] = reason
            else:
                resolved["wikilink"] = ""
                resolved["vault_target"] = ""
                resolved["match_status"] = "ambiguous_match"
                resolved["match_reason"] = reason
                resolved["match_candidates"] = [
                    {
                        "wikilink": _note_wikilink(
                            normalize_whitespace(str(note.get("vault_target", ""))),
                            display_text,
                        ),
                        "vault_target": normalize_whitespace(str(note.get("vault_target", ""))),
                        "match_status": "vault_match",
                        "match_reason": reason,
                    }
                    for note in matches
                ]
            break

        matched.append(resolved)
    return matched
