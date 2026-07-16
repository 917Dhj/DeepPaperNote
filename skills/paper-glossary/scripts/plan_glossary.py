#!/usr/bin/env python3
"""Propose glossary candidates and triage selected terms from raw paper sections."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_common import (
    canonical_sha256,
    elapsed_ms,
    emit,
    load_json_file,
    maybe_load_json_record,
    normalize_whitespace,
    proposal_sha256,
    review_sha256,
    selection_sha256,
)
from link_glossary_terms import (
    _fenced_code_spans,
    _inline_code_spans,
    _markdown_link_spans,
    _scan_markdown_label,
)

NON_EVIDENCE_SECTION_KINDS = frozenset({"references"})
SNIPPET_RADIUS = 70
MAX_ANCHORS_PER_TERM = 3
MAX_EMPHASIS_WORDS = 6
POOL_BUFFER = 10

EMPHASIS_CONNECTORS = frozenset(
    {"and", "by", "for", "from", "in", "of", "on", "or", "the", "to", "via", "with"}
)
CHINESE_SENTENCE_PREFIXES = (
    "我们",
    "本文",
    "本研究",
    "本方法",
    "本模型",
    "该方法",
    "该模型",
    "这种方法",
    "这种模型",
)
CHINESE_SENTENCE_PREDICATES = ("提出", "表明", "证明", "显示", "可以", "能够")

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[+\-][A-Za-z0-9]+)*")
CANDIDATE_STOPWORDS = frozenset({"ID", "OK", "OOD", "DOI", "URL", "PDF"})
PAREN_EXPANSION_RE = re.compile(
    r"([A-Z][A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]+){0,4})\s*\(([A-Za-z][A-Za-z-]+?)s?\)"
)
TITLECASE_RE = re.compile(r"[A-Z][a-z]{2,}(?:[ -][A-Z][a-z]+){1,3}")
KEYWORDS_LINE_RE = re.compile(r"(?im)^[ \t]*(?:keywords|关键词)[ \t]*[:：·]?[ \t]*(.+)$")
GREEK_RE = re.compile(r"[α-ωΑ-Ω]")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
CAPITALIZED_TERM_TOKEN_RE = re.compile(r"[A-Z0-9][A-Za-z0-9+./-]*")
URL_RE = re.compile(r"https?://\S+")
REFERENCE_TAIL_RE = re.compile(
    r"(?ims)^#{1,6}\s*(?:references|参考文献|引用)\s*$.*\Z"
)
EMPHASIS_RE = re.compile(
    r"(?:(?:\*\*|__)([^\n*_]{2,80})(?:\*\*|__)|"
    r"(?:\*|_)([^\n*_]{2,80})(?:\*|_))"
)
STRONG_RE = re.compile(r"(?is)<strong>([^<]{2,80})</strong>")
UNRESOLVED_SELECTION_RE = re.compile(
    r"^\s*[#（(\[]?\s*\d+\s*[）)\]]?[.。]?"
    r"(?:\s*[-,，、;；/\s]\s*[#（(\[]?\s*\d+\s*[）)\]]?[.。]?)*\s*$"
)
WRITE_ALL_SELECTION_RE = re.compile(r"^全部写入\s*[。.!！]?\s*$")
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
    "emphasis": 1,
    "full-name": 2,
    "acronym-or-model": 3,
    "term-phrase": 4,
    "symbol": 5,
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan glossary")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--propose", action="store_true", help="List candidate glossary terms.")
    mode.add_argument(
        "--review-proposal",
        default="",
        help="Saved proposal JSON path to bind a host-reviewed shortlist.",
    )
    mode.add_argument(
        "--reviewed-shortlist",
        default="",
        help="Saved reviewed-shortlist JSON path required for triage.",
    )
    p.add_argument(
        "--terms",
        default="",
        help="Exact selected names from a reviewed shortlist.",
    )
    p.add_argument(
        "--reviewed-terms",
        default="",
        help="Exact host-reviewed proposal names in display order.",
    )
    p.add_argument("--source-manifest", required=True, help="Manifest JSON path or JSON object.")
    p.add_argument(
        "--raw-sections",
        default="",
        help="Raw sections JSONL path. Defaults to manifest raw_sections_path.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def _load_exact_names(
    value: str, label: str, *, allow_empty: bool = False
) -> list[str]:
    raw = value.strip()
    if not raw:
        raise SystemExit(f"{label} requires at least one exact candidate name.")
    path = Path(raw).expanduser()
    text = path.read_text(encoding="utf-8-sig").strip() if path.is_file() else raw
    parsed = _maybe_json_list(text) if text.startswith("[") else None
    items: list[Any] = parsed if parsed is not None else re.split(r"[,\r\n]+", text)
    names: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise SystemExit(f"{label} must contain exact candidate name strings.")
        if not item or normalize_whitespace(item) != item:
            raise SystemExit(f"{label} contains a malformed exact candidate name.")
        names.append(item)
    if not names and not allow_empty:
        raise SystemExit(f"{label} requires at least one exact candidate name.")
    _reject_unresolved_selection(names)
    return names


def load_terms(value: str) -> list[str]:
    raw = value.strip()
    _reject_unresolved_selection([raw])
    parsed = _maybe_json_list(raw)
    if parsed is not None:
        terms = _clean_terms(parsed)
        _reject_unresolved_selection(terms)
        return terms
    path = Path(raw).expanduser()
    if path.exists() and path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        parsed = _maybe_json_list(text.strip())
        if parsed is not None:
            terms = _clean_terms(parsed)
        else:
            terms = _clean_terms(re.split(r"[\r\n]+", text))
    else:
        terms = _clean_terms(re.split(r"[,\r\n]+", raw))
    _reject_unresolved_selection(terms)
    return terms


def _reject_unresolved_selection(terms: list[str]) -> None:
    if any(
        WRITE_ALL_SELECTION_RE.fullmatch(term) or UNRESOLVED_SELECTION_RE.fullmatch(term)
        for term in terms
    ):
        raise SystemExit(
            "Resolve shortlist numbers or 全部写入 to candidate names before passing --terms."
        )


def _maybe_json_list(text: str) -> list[Any] | None:
    if not text.startswith("["):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid terms JSON list: {exc.msg}") from exc
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
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"Invalid raw sections JSONL at {path}:{line_number}: {exc.msg}"
            ) from exc
        if isinstance(record, dict) and record.get("record_type", "section") == "section":
            records.append(record)
    return records


def _record_path(value: str) -> Path | None:
    raw = value.strip()
    if raw.startswith("{"):
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.is_file() else None


def load_manifest_and_sections(
    source_manifest: str, raw_sections: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_record(source_manifest)
    manifest_path = _record_path(source_manifest)
    raw_path = _resolve_raw_path(
        manifest, raw_sections, manifest_path.parent if manifest_path else None
    )
    return manifest, read_raw_sections(raw_path)


def _resolve_raw_path(
    manifest: dict[str, Any], explicit: str, manifest_dir: Path | None = None
) -> Path:
    raw_path_value = explicit or str(manifest.get("raw_sections_path", ""))
    if not raw_path_value:
        raise SystemExit("Pass --raw-sections or use a manifest with raw_sections_path.")
    raw_path = Path(raw_path_value).expanduser()
    if not explicit and manifest_dir is not None and not raw_path.is_absolute():
        raw_path = manifest_dir / raw_path
    raw_path = raw_path.resolve()
    if not raw_path.is_file():
        raise SystemExit(f"Raw sections file not found: {raw_path}")
    return raw_path


def _evidence_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if str(record.get("kind", "")) not in NON_EVIDENCE_SECTION_KINDS
    ]


def _mask_span(characters: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if characters[index] not in "\r\n":
            characters[index] = " "


@lru_cache(maxsize=256)
def _candidate_prose_with_offsets(text: str) -> str:
    characters = list(text)
    fenced = _fenced_code_spans(text)
    inline = _inline_code_spans(text, fenced)
    protected = sorted([*fenced, *inline])
    links = _markdown_link_spans(text, protected)
    for start, end in links:
        label_start = start + 1 if text[start] == "!" else start
        label = _scan_markdown_label(text, label_start)
        if label is None:
            _mask_span(characters, start, end)
            continue
        _, label_end = label
        _mask_span(characters, start, label_start + 1)
        _mask_span(characters, label_end - 1, end)
    for start, end in [*fenced, *inline]:
        _mask_span(characters, start, end)
    for pattern in (URL_RE, REFERENCE_TAIL_RE):
        for match in pattern.finditer(text):
            _mask_span(characters, match.start(), match.end())
    return "".join(characters)


def _candidate_prose(text: str) -> str:
    return _candidate_prose_with_offsets(text)


def effective_prose_text(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        _candidate_prose(str(record.get("text", "")))
        for record in _evidence_records(records)
    )


def shortlist_limit(effective_characters: int) -> int:
    if effective_characters < 10_000:
        return 10
    if effective_characters < 30_000:
        return 18
    if effective_characters < 60_000:
        return 25
    return 35


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


def _non_overlapping_matches(forms: list[str], text: str) -> list[tuple[int, int]]:
    spans = {
        (match.start(), match.end())
        for form in forms
        for match in _term_pattern(form).finditer(text)
    }
    selected: list[tuple[int, int]] = []
    for start, end in sorted(
        spans, key=lambda span: (span[0], -(span[1] - span[0]), span[1])
    ):
        if any(
            start < selected_end and selected_start < end
            for selected_start, selected_end in selected
        ):
            continue
        selected.append((start, end))
    return selected


def _find_occurrences_for_forms(
    forms: list[str], records: list[dict[str, Any]]
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    anchors: list[dict[str, Any]] = []
    for record in _evidence_records(records):
        text = str(record.get("text", ""))
        matches = _non_overlapping_matches(forms, _candidate_prose_with_offsets(text))
        if not matches:
            continue
        total += len(matches)
        if len(anchors) < MAX_ANCHORS_PER_TERM:
            first_start, first_end = matches[0]
            anchors.append(
                {
                    "section_id": record.get("section_id", ""),
                    "title": record.get("title", ""),
                    "page_start": record.get("page_start"),
                    "page_end": record.get("page_end"),
                    "snippet": _snippet(text, first_start, first_end),
                }
            )
    return total, anchors


def find_occurrences(term: str, records: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    return _find_occurrences_for_forms([term], records)


def triage_terms(terms: list[str], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for term in terms:
        if (
            not isinstance(term, str)
            or not term
            or normalize_whitespace(term) != term
            or "|" in term
        ):
            raise SystemExit("Triage terms must contain exact names without alias syntax.")
        candidates.append({"term": term, "surface_forms": [term]})
    return _triage_candidates(candidates, records)


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


def _english_emphasis_term_shape(candidate: str) -> bool:
    words = candidate.split()
    if len(words) == 1:
        return True
    if words[0].casefold() in EMPHASIS_CONNECTORS or words[-1].casefold() in EMPHASIS_CONNECTORS:
        return False
    return all(
        word.casefold() in EMPHASIS_CONNECTORS
        or CAPITALIZED_TERM_TOKEN_RE.fullmatch(word)
        or CJK_RE.search(word)
        for word in words
    )


def _chinese_emphasis_term_shape(candidate: str) -> bool:
    compact = "".join(candidate.split())
    for prefix in CHINESE_SENTENCE_PREFIXES:
        if compact.startswith(prefix) and any(
            predicate in compact[len(prefix) :]
            for predicate in CHINESE_SENTENCE_PREDICATES
        ):
            return False
    return True


def _emphasis_candidate(value: str) -> str:
    candidate = normalize_whitespace(value)
    if (
        not candidate
        or len(candidate) > 80
        or len(candidate.split()) > MAX_EMPHASIS_WORDS
        or re.search(r"[.!?。！？,:;；]", candidate)
        or not re.search(r"[A-Za-z\u0080-\uffff]", candidate)
    ):
        return ""
    if re.search(r"[A-Za-z]", candidate) and not _english_emphasis_term_shape(candidate):
        return ""
    if CJK_RE.search(candidate) and not _chinese_emphasis_term_shape(candidate):
        return ""
    return candidate


def propose_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = _evidence_records(records)
    cleaned_evidence = [
        {**record, "text": _candidate_prose(str(record.get("text", "")))}
        for record in evidence
    ]
    categories: dict[str, tuple[str, str, list[str]]] = {}

    def add(term: str, category: str) -> None:
        cleaned = normalize_whitespace(term)
        if not cleaned:
            return
        key = unicodedata.normalize("NFKC", cleaned).casefold()
        existing = categories.get(key)
        if existing is None:
            categories[key] = (cleaned, category, [cleaned])
        elif cleaned not in existing[2]:
            existing[2].append(cleaned)

    for keyword in _extract_keywords(cleaned_evidence):
        add(keyword, "keyword")
    for record in cleaned_evidence:
        for match in EMPHASIS_RE.finditer(str(record.get("text", ""))):
            candidate = _emphasis_candidate(match.group(1) or match.group(2) or "")
            if candidate:
                add(candidate, "emphasis")
        for match in STRONG_RE.finditer(str(record.get("text", ""))):
            candidate = _emphasis_candidate(match.group(1))
            if candidate:
                add(candidate, "emphasis")
    for record in cleaned_evidence:
        for match in PAREN_EXPANSION_RE.finditer(str(record.get("text", ""))):
            if _titlecase_ok(match.group(1)):
                add(match.group(1), "full-name")
            if _is_acronym(match.group(2)):
                add(match.group(2), "acronym-or-model")
    for record in cleaned_evidence:
        for match in TOKEN_RE.finditer(str(record.get("text", ""))):
            if _is_acronym(match.group(0)):
                add(match.group(0), "acronym-or-model")
    for record in cleaned_evidence:
        for match in TITLECASE_RE.finditer(str(record.get("text", ""))):
            if _titlecase_ok(match.group(0)):
                add(match.group(0), "term-phrase")
    for record in cleaned_evidence:
        for match in GREEK_RE.finditer(str(record.get("text", ""))):
            add(match.group(0), "symbol")

    results: list[dict[str, Any]] = []
    for term, category, surface_forms in categories.values():
        occurrences, anchors = _find_occurrences_for_forms(surface_forms, records)
        if category == "term-phrase" and occurrences < 2:
            continue
        if occurrences == 0 and category not in ("keyword", "symbol"):
            continue
        anchor = anchors[0] if anchors else {}
        results.append(
            {
                "term": term,
                "surface_forms": surface_forms,
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
    effective_characters = sum(
        1 for character in effective_prose_text(records) if not character.isspace()
    )
    return results[: shortlist_limit(effective_characters) + POOL_BUFFER]


def _proposal_summary(
    records: list[dict[str, Any]], candidates: list[dict[str, Any]]
) -> dict[str, int]:
    effective_characters = sum(
        1 for character in effective_prose_text(records) if not character.isspace()
    )
    return {
        "effective_body_characters": effective_characters,
        "shortlist_limit": shortlist_limit(effective_characters),
        "pool_candidates": len(candidates),
    }


def _proposal_artifact(
    manifest: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    paper_id = str(manifest.get("paper_id", ""))
    candidates = propose_candidates(records)
    summary = _proposal_summary(records, candidates)
    source_sha256 = canonical_sha256(
        {"paper_id": paper_id, "manifest": manifest, "records": records}
    )
    proposal_digest = proposal_sha256(paper_id, source_sha256, candidates, summary)
    proposal_provenance = {
        "paper_id": paper_id,
        "source_sha256": source_sha256,
        "candidates": candidates,
        "summary": summary,
        "proposal_sha256": proposal_digest,
    }
    has_candidates = bool(candidates)
    return {
        "status": "ok",
        "script": "plan_glossary.py",
        "mode": "propose",
        "workflow_state": "awaiting_semantic_review" if has_candidates else "no_candidates",
        "next_action": (
            "record_reviewed_shortlist_then_present_and_wait"
            if has_candidates
            else "report_no_candidates"
        ),
        "paper_id": paper_id,
        "candidates": candidates,
        "summary": summary,
        "provenance": proposal_provenance,
    }


def _validated_proposal(
    proposal: dict[str, Any], manifest: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    expected = _proposal_artifact(manifest, records)
    fields = (
        "status",
        "script",
        "mode",
        "workflow_state",
        "next_action",
        "paper_id",
        "candidates",
        "summary",
        "provenance",
    )
    if any(proposal.get(field) != expected[field] for field in fields):
        raise SystemExit("Invalid proposal artifact for the current paper and source data.")
    return expected


def _review_artifact(
    proposal: dict[str, Any], reviewed_names: list[str]
) -> dict[str, Any]:
    if len(reviewed_names) != len(set(reviewed_names)):
        raise SystemExit("Host-reviewed candidate names must not contain duplicates.")
    limit = int(proposal["summary"]["shortlist_limit"])
    if len(reviewed_names) > limit:
        raise SystemExit(f"Host-reviewed candidate names exceed shortlist limit {limit}.")
    by_name = {candidate["term"]: candidate for candidate in proposal["candidates"]}
    unknown = [name for name in reviewed_names if name not in by_name]
    if unknown:
        raise SystemExit(
            f"Host-reviewed name must exactly match a proposal term: {unknown[0]}"
        )
    reviewed = [by_name[name] for name in reviewed_names]
    proposal_provenance = proposal["provenance"]
    review_digest = review_sha256(proposal_provenance, reviewed)
    has_reviewed_candidates = bool(reviewed)
    return {
        "status": "ok",
        "script": "plan_glossary.py",
        "mode": "review",
        "workflow_state": (
            "awaiting_user_selection" if has_reviewed_candidates else "no_candidates"
        ),
        "next_action": (
            "present_numbered_shortlist_and_wait"
            if has_reviewed_candidates
            else "report_no_candidates"
        ),
        "paper_id": proposal["paper_id"],
        "proposal_provenance": proposal_provenance,
        "reviewed_shortlist": reviewed,
        "summary": {"shortlist_limit": limit, "reviewed_candidates": len(reviewed)},
        "provenance": {
            **proposal_provenance,
            "reviewed_shortlist": reviewed,
            "review_sha256": review_digest,
        },
    }


def _validated_review(
    review: dict[str, Any], manifest: dict[str, Any], records: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal = _proposal_artifact(manifest, records)
    reviewed = review.get("reviewed_shortlist")
    if not isinstance(reviewed, list) or any(not isinstance(item, dict) for item in reviewed):
        raise SystemExit("Invalid reviewed-shortlist artifact.")
    names = [item.get("term") for item in reviewed]
    if any(not isinstance(name, str) for name in names):
        raise SystemExit("Invalid reviewed candidate name.")
    expected = _review_artifact(proposal, names)
    fields = (
        "status",
        "script",
        "mode",
        "workflow_state",
        "next_action",
        "paper_id",
        "proposal_provenance",
        "reviewed_shortlist",
        "summary",
        "provenance",
    )
    if any(review.get(field) != expected[field] for field in fields):
        raise SystemExit("Invalid reviewed-shortlist artifact identity or proposal binding.")
    return expected, proposal


def _triage_candidates(
    candidates: list[dict[str, Any]], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        forms = candidate["surface_forms"]
        occurrences, anchors = _find_occurrences_for_forms(forms, records)
        found = occurrences > 0
        results.append(
            {
                "term": candidate["term"],
                "surface_forms": forms,
                "found_in_paper": found,
                "occurrences": occurrences,
                "routing": "anchor_only" if found else "needs_explanation",
                "paper_anchors": anchors,
            }
        )
    return results


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    if not (args.propose or args.review_proposal or args.reviewed_shortlist):
        if args.terms.strip():
            raise SystemExit("Triage requires --reviewed-shortlist with exact selected names.")
        raise SystemExit(
            "plan_glossary.py requires --propose, --review-proposal, or --reviewed-shortlist."
        )
    manifest, records = load_manifest_and_sections(args.source_manifest, args.raw_sections)

    if args.propose:
        if args.terms.strip() or args.reviewed_terms.strip():
            raise SystemExit("Proposal mode does not accept selected terms.")
        emit({**_proposal_artifact(manifest, records), "elapsed_ms": elapsed_ms(started)}, args.output)
        return

    if args.review_proposal:
        if args.terms.strip() or not args.reviewed_terms.strip():
            raise SystemExit("Review mode requires --reviewed-terms and does not accept --terms.")
        proposal = _validated_proposal(
            load_json_file(Path(args.review_proposal).expanduser().resolve()),
            manifest,
            records,
        )
        reviewed_names = _load_exact_names(
            args.reviewed_terms, "--reviewed-terms", allow_empty=True
        )
        emit(
            {
                **_review_artifact(proposal, reviewed_names),
                "elapsed_ms": elapsed_ms(started),
            },
            args.output,
        )
        return

    if not args.terms.strip() or args.reviewed_terms.strip():
        raise SystemExit("Triage requires --terms and does not accept --reviewed-terms.")
    review, proposal = _validated_review(
        load_json_file(Path(args.reviewed_shortlist).expanduser().resolve()),
        manifest,
        records,
    )
    selected_names = _load_exact_names(args.terms, "--terms")
    if len(selected_names) != len(set(selected_names)):
        raise SystemExit("Selected shortlist names must not contain duplicates.")
    reviewed_by_name = {
        candidate["term"]: candidate for candidate in review["reviewed_shortlist"]
    }
    unknown = [name for name in selected_names if name not in reviewed_by_name]
    if unknown:
        raise SystemExit(
            f"Selected name must exactly match the reviewed shortlist: {unknown[0]}"
        )
    selected_candidates = [reviewed_by_name[name] for name in selected_names]
    triaged = _triage_candidates(selected_candidates, records)
    anchor_only = sum(1 for item in triaged if item["routing"] == "anchor_only")
    emit(
        {
            "status": "ok",
            "script": "plan_glossary.py",
            "mode": "triage",
            "paper_id": proposal["paper_id"],
            "terms": triaged,
            "provenance": {
                "proposal": proposal["provenance"],
                "review": review["provenance"],
                "selection_sha256": selection_sha256(
                    review["provenance"]["review_sha256"], triaged
                ),
            },
            "summary": {
                "total": len(triaged),
                "anchor_only": anchor_only,
                "needs_explanation": len(triaged) - anchor_only,
            },
            "elapsed_ms": elapsed_ms(started),
        },
        args.output,
    )


if __name__ == "__main__":
    main()
