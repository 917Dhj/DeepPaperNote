#!/usr/bin/env python3
"""Shared helpers for DeepPaperNote scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any

from user_configuration import (
    inspect_configuration,
    resolve_preferences,
    resolve_run_overrides,
)

ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
DEFAULT_USER_AGENT = "DeepPaperNote/0.1"
PROVENANCE_FIELDS = (
    "title",
    "translated_title",
    "authors",
    "affiliations",
    "year",
    "venue",
    "doi",
    "arxiv_id",
    "zotero_key",
    "abstract",
    "source_url",
    "pdf_url",
    "local_pdf_path",
)
SHELL_CONFIG_FILES = [
    Path.home() / ".zshenv",
    Path.home() / ".zprofile",
    Path.home() / ".zshrc",
    Path.home() / ".bash_profile",
    Path.home() / ".bashrc",
]

try:
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None

try:
    import certifi  # type: ignore
except ImportError:  # pragma: no cover
    certifi = None


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", help="Primary input path, JSON artifact, or identifier.")
    parser.add_argument("--output", help="Output path for JSON or Markdown.")
    parser.add_argument("--paper-id", help="Canonical paper id if already known.")
    return parser


def ensure_parent(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def file_sha256(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        return ""
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_input_sha256(value: str | Path) -> str:
    text = str(value)
    if text.lstrip().startswith("{"):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return file_sha256(value)


def emit(payload: dict[str, Any], output_path: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        ensure_parent(output_path)
        Path(output_path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def load_json_file(path: str | Path) -> dict[str, Any]:
    # utf-8-sig transparently strips a UTF-8 BOM (e.g. files written by
    # PowerShell Out-File / Notepad on Windows) that would otherwise make
    # json.loads raise "Unexpected UTF-8 BOM". It is a no-op for BOM-less files.
    data = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("Expected a JSON object.")
    return data


def maybe_load_json_record(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    path = Path(stripped).expanduser()
    if path.exists() and path.is_file() and path.suffix.lower() == ".json":
        return load_json_file(path)
    return None


def require_ok_input_artifact(record: dict[str, Any], consumer: str) -> dict[str, Any]:
    status = normalize_whitespace(str(record.get("status", ""))).lower()
    if status and status != "ok":
        producer = normalize_whitespace(str(record.get("script", ""))) or "unknown producer"
        message = f"{consumer} refuses non-ok input artifact from {producer}: status={status}"
        raise SystemExit(message)
    return record


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def strip_tags(text: str) -> str:
    return normalize_whitespace(re.sub(r"<[^>]+>", " ", text or ""))


def normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", normalize_whitespace(text).lower()).strip()


LOCAL_PDF_PREFIX_PATTERN = re.compile(r"^(?:[^-]{1,120})\s+-\s+(?:19|20)\d{2}\s+-\s+")
LOCAL_PDF_SUFFIX_ID_PATTERN = re.compile(r"\s*-\s*\d{4,}\s*$")
PREPRINT_HINTS = ("medrxiv", "biorxiv", "preprint", "arxiv", "10.1101/", "10.21203/rs.", "preprints.org")
PDF_LIGATURE_MAP = {
    "\u00df": "ss",
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}


def clean_local_pdf_stem(stem: str) -> str:
    raw = normalize_whitespace((stem or "").replace("_", " "))
    if not raw:
        return ""
    cleaned = LOCAL_PDF_PREFIX_PATTERN.sub("", raw)
    cleaned = LOCAL_PDF_SUFFIX_ID_PATTERN.sub("", cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned or raw


def is_probable_local_pdf_artifact_title(title: str) -> bool:
    normalized = normalize_whitespace(title)
    if not normalized:
        return False
    if LOCAL_PDF_PREFIX_PATTERN.match(normalized):
        return True
    if LOCAL_PDF_SUFFIX_ID_PATTERN.search(normalized):
        return True
    return bool(re.search(r"\b(?:et al\.?|等)\b", normalized, flags=re.IGNORECASE) and re.search(r"\b(?:19|20)\d{2}\b", normalized))


def _dedupe_string_list(value: Any) -> list[str]:
    if value in ("", None, [], {}):
        return []
    values = value if isinstance(value, list) else [value]
    deduped: list[str] = []
    for item in values:
        cleaned = normalize_whitespace(str(item))
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _append_reason(reasons: list[str], reason: str) -> None:
    cleaned = normalize_whitespace(reason)
    if cleaned and cleaned not in reasons:
        reasons.append(cleaned)


def apply_identity_confidence(record: dict[str, Any]) -> dict[str, Any]:
    reasons = _dedupe_string_list(record.get("identity_confidence_reasons", []))
    confidence = normalize_whitespace(str(record.get("identity_confidence", ""))).lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = ""

    if record.get("doi"):
        _append_reason(reasons, "doi_present")
        confidence = "high"
    if record.get("arxiv_id"):
        _append_reason(reasons, "arxiv_id_present")
        confidence = "high"
    if record.get("zotero_key"):
        _append_reason(reasons, "zotero_key_present")
        confidence = "high"

    source_type = normalize_whitespace(str(record.get("source_type", "")))
    metadata_sources = set(_dedupe_string_list(record.get("metadata_sources", [])))
    has_local_pdf = source_type == "local_pdf" or "local_pdf" in metadata_sources
    has_title_query = source_type == "title_query" or "title_query" in metadata_sources
    external_sources = metadata_sources - {"local_pdf", "title_query"}

    title_source_reason = normalize_whitespace(str(record.get("local_pdf_title_source", "")))
    if has_local_pdf and title_source_reason:
        _append_reason(reasons, title_source_reason)
    if has_local_pdf and record.get("local_pdf_artifact_title"):
        _append_reason(reasons, "local_pdf_artifact_title")

    if confidence != "high":
        if has_local_pdf and record.get("title_corrected_from_external_metadata"):
            _append_reason(reasons, "external_metadata_title_match")
            confidence = "medium"
        elif has_title_query:
            if external_sources:
                _append_reason(reasons, "external_metadata_title_match")
                confidence = "medium"
            else:
                _append_reason(reasons, "title_query_unmatched")
                confidence = "low"
        elif has_local_pdf:
            if is_probable_local_pdf_artifact_title(str(record.get("title", ""))):
                _append_reason(reasons, "local_pdf_artifact_title")
            confidence = "low"

    if confidence:
        record["identity_confidence"] = confidence
        record["identity_confidence_reasons"] = reasons
    return record


def normalize_pdf_text_artifacts(text: str) -> str:
    normalized = text or ""
    for original, replacement in PDF_LIGATURE_MAP.items():
        normalized = normalized.replace(original, replacement)
    return normalized


def slugify_filename(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text or "paper_note"


def shell_config_value(name: str) -> str:
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}=(.*)$")
    for path in SHELL_CONFIG_FILES:
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except Exception:
            continue
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = pattern.match(line)
            if not match:
                continue
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value.strip()
    return ""


def env_config_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    disable_shell_fallback = os.environ.get("DEEPPAPERNOTE_DISABLE_SHELL_CONFIG", "").strip().lower()
    if disable_shell_fallback in {"1", "true", "yes", "on"}:
        return default
    for name in names:
        value = shell_config_value(name)
        if value:
            return value
    return default


def title_similarity(a: str, b: str) -> float:
    a_identity = normalize_identity_title(a)
    b_identity = normalize_identity_title(b)
    if a_identity and a_identity == b_identity:
        return 1.0
    a_norm = normalize_title(a)
    b_norm = normalize_title(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    words_a = set(a_norm.split())
    words_b = set(b_norm.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def publication_quality_score(record: dict[str, Any]) -> int:
    venue = normalize_whitespace(str(record.get("venue", ""))).lower()
    source_url = normalize_whitespace(str(record.get("source_url", ""))).lower()
    source = normalize_whitespace(str(record.get("source", ""))).lower()
    doi = normalize_whitespace(str(record.get("doi", ""))).lower()
    joined = " ".join([venue, source_url, source, doi])
    if any(token in joined for token in PREPRINT_HINTS):
        return 0
    if venue or source == "crossref":
        return 2
    return 1


def candidate_priority_score(record: dict[str, Any]) -> int:
    source = normalize_whitespace(str(record.get("source", ""))).lower()
    source_url = normalize_whitespace(str(record.get("source_url", ""))).lower()
    doi = normalize_whitespace(str(record.get("doi", ""))).lower()
    joined = " ".join([source, source_url, doi])

    if "10.20944/preprints" in joined or any(token in joined for token in PREPRINT_HINTS):
        return 0

    if record.get("doi") and publication_quality_score(record) >= 2:
        return 4

    if record.get("arxiv_id") or source == "arxiv" or "arxiv.org" in source_url:
        return 3

    if record.get("pdf_url"):
        return 2

    return 1


def extract_arxiv_id(paper_ref: str) -> str | None:
    paper_ref = (paper_ref or "").strip()
    patterns = [
        r"arxiv:(\d{4}\.\d{4,5})(?:v\d+)?",
        r"arxiv[./]\s*(\d{4}\.\d{4,5})(?:v\d+)?",
        r"abs/(\d{4}\.\d{4,5})(?:v\d+)?",
        r"pdf/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?",
        r"(?<![A-Za-z0-9./-])(\d{4}\.\d{4,5})(?:v\d+)?(?![A-Za-z0-9./-])",
    ]
    for pattern in patterns:
        match = re.search(pattern, paper_ref, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_doi(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).rstrip(").,;]")


def is_probable_url(text: str) -> bool:
    return bool(re.match(r"^https?://", (text or "").strip(), flags=re.IGNORECASE))


def is_probable_zotero_key(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{8}", (text or "").strip()))


def infer_source_type(value: str) -> str:
    stripped = (value or "").strip()
    if not stripped:
        return "unknown"
    path = Path(stripped).expanduser()
    if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
        return "local_pdf"
    if is_probable_url(stripped):
        if "arxiv.org" in stripped.lower() and extract_arxiv_id(stripped):
            return "arxiv_url"
        if extract_doi(stripped):
            return "doi_url"
        if stripped.lower().endswith(".pdf"):
            return "pdf_url"
        return "url"
    if extract_doi(stripped):
        return "doi"
    if extract_arxiv_id(stripped):
        return "arxiv_id"
    if is_probable_zotero_key(stripped):
        return "zotero_key"
    return "title"


def paper_id_for_record(record: dict[str, Any]) -> str:
    if record.get("paper_id"):
        return str(record["paper_id"])
    if record.get("doi"):
        return f"doi:{str(record['doi']).lower()}"
    if record.get("arxiv_id"):
        return f"arxiv:{record['arxiv_id']}"
    if record.get("zotero_key"):
        return f"zotero:{record['zotero_key']}"
    if record.get("title"):
        digest = hashlib.sha1(normalize_title(str(record["title"])).encode("utf-8")).hexdigest()[:12]
        return f"title:{digest}"
    source = str(record.get("source_url") or record.get("local_pdf_path") or "unknown")
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    return f"paper:{digest}"


def _string_field(record: dict[str, Any], key: str) -> str:
    return normalize_whitespace(str(record.get(key, "")))


def _path_string(path_value: str) -> str:
    value = normalize_whitespace(path_value)
    if not value:
        return ""
    return str(Path(value).expanduser().resolve())


def _artifact_path(path_value: str) -> str:
    value = normalize_whitespace(path_value)
    if not value:
        return ""
    path = Path(value).expanduser()
    return str(path.resolve()) if path.exists() else str(path)


def selected_identity_evidence(
    record: dict[str, Any],
    source_record: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def append(kind: str, value: str, trust: str, source: str) -> None:
        cleaned = normalize_whitespace(value)
        marker = (kind, cleaned, source)
        if cleaned and marker not in seen:
            seen.add(marker)
            evidence.append(
                {
                    "kind": kind,
                    "value": cleaned,
                    "trust": trust,
                    "source": source,
                }
            )

    append("doi", _string_field(record, "doi"), "strong", "metadata")
    append("arxiv_id", _string_field(record, "arxiv_id"), "strong", "metadata")
    append("zotero_key", _string_field(record, "zotero_key"), "strong", "metadata")
    append("title", _string_field(record, "title"), "metadata", "metadata")
    local_pdf = _string_field(record, "local_pdf_path")
    if local_pdf:
        append("trusted_source_path", _path_string(local_pdf), "strong", "source_manifestation")
    pdf_url = _string_field(record, "pdf_url")
    if pdf_url:
        append("pdf_url", pdf_url, "source_manifestation", "metadata")
    source_url = _string_field(record, "source_url")
    if source_url and source_url != pdf_url:
        append("source_url", source_url, "source_manifestation", "metadata")
    if source_record and source_record is not record:
        local_pdf = _string_field(source_record, "local_pdf_path")
        if local_pdf:
            append("trusted_source_path", _path_string(local_pdf), "strong", "source_manifestation")
        pdf_url = _string_field(source_record, "pdf_url")
        if pdf_url:
            append("pdf_url", pdf_url, "source_manifestation", "source_manifestation")
        source_url = _string_field(source_record, "source_url")
        if source_url and source_url != pdf_url:
            append("source_url", source_url, "source_manifestation", "source_manifestation")
    return evidence


def work_level_identity_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _string_field(record, "title"),
        "translated_title": _string_field(record, "translated_title"),
        "authors": _dedupe_string_list(record.get("authors", [])),
        "year": _string_field(record, "year"),
        "venue": _string_field(record, "venue"),
        "doi": _string_field(record, "doi"),
        "arxiv_id": _string_field(record, "arxiv_id"),
        "zotero_key": _string_field(record, "zotero_key"),
    }


def source_manifestation_from_record(
    record: dict[str, Any],
    work_record: dict[str, Any] | None = None,
) -> dict[str, str]:
    work_record = work_record or {}
    local_pdf = _string_field(record, "local_pdf_path")
    if not local_pdf:
        local_pdf = _string_field(work_record, "local_pdf_path")
    source_kind = _string_field(record, "source_type")
    if not source_kind:
        source_kind = _string_field(work_record, "source_type")
    if local_pdf:
        source_kind = "local_pdf"
    elif _string_field(record, "pdf_url") or _string_field(work_record, "pdf_url"):
        source_kind = source_kind or "pdf_url"
    elif _string_field(record, "source_url") or _string_field(work_record, "source_url"):
        source_kind = source_kind or "source_url"
    source_url = _string_field(record, "source_url")
    if not source_url and local_pdf:
        source_url = _path_string(local_pdf)
    return {
        "source_kind": source_kind or "unknown",
        "title": _string_field(record, "title") or _string_field(work_record, "title"),
        "year": _string_field(record, "year"),
        "venue": _string_field(record, "venue"),
        "source_url": source_url or _string_field(work_record, "source_url"),
        "pdf_url": _string_field(record, "pdf_url") or _string_field(work_record, "pdf_url"),
        "local_pdf_path": _path_string(local_pdf),
        "doi": _string_field(record, "doi"),
        "arxiv_id": _string_field(record, "arxiv_id"),
        "zotero_key": _string_field(record, "zotero_key"),
    }


def _normalized_identifier(record: dict[str, Any], key: str) -> str:
    value = _string_field(record, key)
    if key == "doi":
        value = extract_doi(value) or value
    if key == "arxiv_id":
        value = extract_arxiv_id(value) or value
    return value.lower()


def _record_arxiv_id(record: dict[str, Any]) -> str:
    for key in ("arxiv_id", "doi", "source_url", "pdf_url"):
        arxiv_id = extract_arxiv_id(_string_field(record, key))
        if arxiv_id:
            return arxiv_id.lower()
    return ""


def _author_key(name: str) -> str:
    raw = normalize_whitespace(name)
    if not raw:
        return ""
    if "," in raw:
        raw = raw.split(",", 1)[0]
    parts = normalize_title(raw).split()
    if not parts:
        return ""
    return parts[-1]


def normalize_identity_title(title: str) -> str:
    return normalize_whitespace(unicodedata.normalize("NFKC", title).casefold())


def _author_identity_parts(name: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", normalize_whitespace(name)).casefold()
    if "," in normalized:
        family, given = normalized.split(",", 1)
        normalized = f"{given} {family}"
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def _full_leading_author_matches(
    source_record: dict[str, Any],
    work_record: dict[str, Any],
) -> bool:
    source_authors = _dedupe_string_list(source_record.get("authors", []))
    work_authors = _dedupe_string_list(work_record.get("authors", []))
    if not source_authors or not work_authors:
        return False
    source_normalized = normalize_identity_title(source_authors[0])
    work_normalized = normalize_identity_title(work_authors[0])
    if source_normalized == work_normalized:
        return True
    source_parts = _author_identity_parts(source_authors[0])
    work_parts = _author_identity_parts(work_authors[0])
    if len(source_parts) < 2 or len(work_parts) < 2:
        return False
    if source_parts[-1] != work_parts[-1]:
        return False
    source_given = source_parts[:-1]
    work_given = work_parts[:-1]
    return len(source_given) == len(work_given) and all(
        left == right
        for left, right in zip(source_given, work_given)
    )


def _leading_author_status(
    source_record: dict[str, Any],
    work_record: dict[str, Any],
) -> dict[str, Any] | None:
    source_authors = _dedupe_string_list(source_record.get("authors", []))
    work_authors = _dedupe_string_list(work_record.get("authors", []))
    if not source_authors or not work_authors:
        return None
    source_normalized = normalize_identity_title(source_authors[0])
    work_normalized = normalize_identity_title(work_authors[0])
    source_key = _author_key(source_authors[0])
    work_key = _author_key(work_authors[0])
    status = (
        "match"
        if source_normalized == work_normalized
        or (source_key and source_key == work_key)
        else "conflict"
    )
    return {
        "kind": "leading_author",
        "status": status,
        "source_value": source_authors[0],
        "work_value": work_authors[0],
    }


def _record_abstract(record: dict[str, Any]) -> str:
    for key in ("abstract", "first_paragraph", "first_page_text", "summary"):
        value = _string_field(record, key)
        if value:
            return value
    return ""


def _shared_identifier_evidence(
    source_record: dict[str, Any],
    work_record: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shared: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    source_doi = _normalized_identifier(source_record, "doi")
    work_doi = _normalized_identifier(work_record, "doi")
    source_arxiv = _record_arxiv_id(source_record)
    work_arxiv = _record_arxiv_id(work_record)
    source_zotero = _normalized_identifier(source_record, "zotero_key")
    work_zotero = _normalized_identifier(work_record, "zotero_key")

    if source_doi and work_doi and source_doi == work_doi:
        shared.append({"kind": "shared_identifier", "value": f"doi:{work_doi}"})
    elif source_doi and work_doi:
        conflicts.append(
            {
                "kind": "identifier",
                "status": "conflict",
                "source_value": f"doi:{source_doi}",
                "work_value": f"doi:{work_doi}",
            }
        )

    if source_arxiv and work_arxiv and source_arxiv == work_arxiv:
        shared.append({"kind": "shared_identifier", "value": f"arxiv_id:{work_arxiv}"})
    elif source_arxiv and work_arxiv:
        conflicts.append(
            {
                "kind": "identifier",
                "status": "conflict",
                "source_value": f"arxiv_id:{source_arxiv}",
                "work_value": f"arxiv_id:{work_arxiv}",
            }
        )

    if source_zotero and work_zotero and source_zotero == work_zotero:
        shared.append({"kind": "shared_identifier", "value": f"zotero_key:{work_zotero}"})
    elif source_zotero and work_zotero:
        conflicts.append(
            {
                "kind": "identifier",
                "status": "conflict",
                "source_value": f"zotero_key:{source_zotero}",
                "work_value": f"zotero_key:{work_zotero}",
            }
        )
    return shared, conflicts


def manifestation_equivalence_decision(
    work_record: dict[str, Any],
    source_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_record = source_record or work_record
    source_title = _string_field(source_record, "title")
    work_title = _string_field(work_record, "title")
    title_score = title_similarity(source_title, work_title)
    evidence: list[dict[str, Any]] = []

    shared_identifiers, identifier_conflicts = _shared_identifier_evidence(
        source_record,
        work_record,
    )
    evidence.extend(shared_identifiers)
    evidence.extend(identifier_conflicts)
    if source_title and work_title:
        title_status = "match" if title_score >= 0.82 else "weak_match"
        evidence.append(
            {
                "kind": "title_similarity",
                "status": title_status,
                "score": round(title_score, 3),
                "source_value": source_title,
                "work_value": work_title,
            }
        )

    author_evidence = _leading_author_status(source_record, work_record)
    author_conflict = False
    author_match = False
    if author_evidence:
        evidence.append(author_evidence)
        author_match = author_evidence["status"] == "match"
        author_conflict = author_evidence["status"] == "conflict"

    source_abstract = _record_abstract(source_record)
    work_abstract = _record_abstract(work_record)
    abstract_score = title_similarity(source_abstract, work_abstract)
    abstract_conflict = bool(source_abstract and work_abstract and abstract_score < 0.25)
    abstract_match = bool(source_abstract and work_abstract and abstract_score >= 0.45)
    if source_abstract and work_abstract:
        evidence.append(
            {
                "kind": "abstract_similarity",
                "status": "match" if abstract_match else "weak_match",
                "score": round(abstract_score, 3),
            }
        )

    if identifier_conflicts:
        status = "ambiguous"
        reason = "competing_identity_evidence"
    elif title_score < 0.55 and (author_conflict or abstract_conflict):
        status = "ambiguous"
        reason = "competing_identity_evidence"
    elif shared_identifiers:
        status = "equivalent"
        reason = "shared_work_identifier"
    elif title_score >= 0.82 and (author_match or abstract_match):
        status = "equivalent"
        reason = "title_author_or_abstract_supports_equivalence"
    elif title_score >= 0.9:
        status = "equivalent"
        reason = "minor_title_variation_only"
    else:
        status = "equivalent"
        reason = "uncontested_manifestation"

    return {
        "status": status,
        "reason": reason,
        "location_binding": "source_manifestation",
        "evidence": evidence,
    }


def identity_verdict_from_equivalence(equivalence_decision: dict[str, Any]) -> str:
    if _string_field(equivalence_decision, "status") == "ambiguous":
        return "ambiguous"
    return "accepted"


def identity_provenance(
    *,
    resolve_artifact_path: str = "",
    metadata_artifact_path: str = "",
) -> dict[str, str]:
    return {
        "resolve_artifact_path": _artifact_path(resolve_artifact_path),
        "metadata_artifact_path": _artifact_path(metadata_artifact_path),
    }


PROVIDER_IDENTITY_SOURCES = {
    "arxiv",
    "crossref",
    "doi",
    "openalex",
    "semantic_scholar",
    "zotero",
    "zotero_key",
}
CHALLENGEABLE_IDENTITY_SOURCES = {"local_pdf", "pdf_url", "title_query"}
STRONG_ANCHOR_SOURCE_TYPES = {
    "doi": {"doi", "doi_url"},
    "arxiv_id": {"arxiv_id", "arxiv_url"},
    "zotero_key": {"zotero_key"},
}
ACCEPTED_IDENTITY_VERDICTS = {"accepted", "accepted_with_warnings"}
IDENTITY_FAILURE_SUMMARIES = {
    "ambiguous_competing_identities": (
        "Identity repair exhausted: multiple plausible papers remain. Provide a "
        "stronger identifier such as a DOI, arXiv ID, Zotero key, or trusted source PDF."
    ),
    "insufficient_evidence": (
        "Identity repair exhausted: there is not enough trusted evidence to choose the "
        "paper. Provide a stronger identifier such as a DOI, arXiv ID, Zotero key, or "
        "trusted source PDF."
    ),
    "provider_unavailable": (
        "Identity repair exhausted: metadata providers were unavailable, so the paper "
        "could not be verified. Retry later or provide a stronger identifier."
    ),
    "metadata_contradiction": (
        "Identity repair exhausted: trusted identity metadata contradicts other "
        "acquisition evidence. Provide a stronger identifier or a trusted source PDF."
    ),
    "source_pdf_mismatch": (
        "Identity repair exhausted: the selected PDF appears to describe a different "
        "paper. Provide the correct PDF or a stronger identifier."
    ),
}


def _metadata_source_set(record: dict[str, Any]) -> set[str]:
    sources = set()
    source_type = _string_field(record, "source_type").lower()
    if source_type:
        sources.add(source_type)
    for source in _dedupe_string_list(record.get("metadata_sources", [])):
        sources.add(source.lower())
    return sources


def _boolish_field(record: dict[str, Any], key: str) -> bool:
    value = record.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "unavailable"}
    return bool(value)


def _has_provider_unavailable(record: dict[str, Any]) -> bool:
    if _boolish_field(record, "provider_unavailable") or _boolish_field(
        record, "metadata_provider_unavailable"
    ):
        return True
    if record.get("provider_errors") or record.get("provider_failures"):
        return True
    status = _string_field(record, "provider_status").lower()
    return status in {"unavailable", "failed", "timeout"}


def _has_metadata_contradiction(record: dict[str, Any]) -> bool:
    contradiction_keys = (
        "identity_contradictions",
        "metadata_contradictions",
        "unresolved_metadata_contradictions",
    )
    return any(bool(record.get(key)) for key in contradiction_keys)


def _has_trusted_source_manifestation(record: dict[str, Any]) -> bool:
    if _string_field(record, "local_pdf_path"):
        return True
    if _string_field(record, "pdf_url"):
        return True
    source_url = _string_field(record, "source_url")
    source_type = _string_field(record, "source_type").lower()
    return bool(source_url and source_type not in {"", "title", "title_query"})


def _has_minimum_identity_evidence(
    record: dict[str, Any],
    source_record: dict[str, Any] | None,
) -> bool:
    if _has_stronger_identity_evidence(record):
        return True
    if _has_trusted_source_manifestation(record):
        return True
    if source_record and source_record is not record:
        return _has_stronger_identity_evidence(source_record) or _has_trusted_source_manifestation(
            source_record
        )
    return False


def _normalized_anchor_value(key: str, value: Any) -> str:
    cleaned = normalize_whitespace(str(value or ""))
    if not cleaned:
        return ""
    if key == "doi":
        return (extract_doi(cleaned) or cleaned).lower()
    if key == "arxiv_id":
        return (extract_arxiv_id(cleaned) or cleaned).lower()
    if key == "zotero_key":
        return cleaned.upper()
    return cleaned.lower()


def _paper_id_for_effective_identity(record: dict[str, Any]) -> str:
    without_stale_id = dict(record)
    without_stale_id.pop("paper_id", None)
    return paper_id_for_record(without_stale_id)


def _has_stronger_identity_evidence(record: dict[str, Any]) -> bool:
    if any(_string_field(record, key) for key in ("doi", "arxiv_id", "zotero_key")):
        return True
    return bool(_metadata_source_set(record) & PROVIDER_IDENTITY_SOURCES)


def _repair_evidence_used(record: dict[str, Any]) -> list[dict[str, str]]:
    evidence = selected_identity_evidence(record)
    metadata_sources = _dedupe_string_list(record.get("metadata_sources", []))
    if metadata_sources:
        trust = (
            "provider"
            if _metadata_source_set(record) & PROVIDER_IDENTITY_SOURCES
            else "metadata"
        )
        evidence.append(
            {
                "kind": "metadata_sources",
                "value": ", ".join(metadata_sources),
                "trust": trust,
                "source": "metadata",
            }
        )
    return evidence


def _challengeable_title_replacement_reason(record: dict[str, Any]) -> str:
    title = _string_field(record, "title")
    sources = _metadata_source_set(record)
    title_source = _string_field(record, "local_pdf_title_source").lower()
    reasons = {
        reason.lower()
        for reason in _dedupe_string_list(record.get("identity_confidence_reasons", []))
    }

    if not title and sources & CHALLENGEABLE_IDENTITY_SOURCES:
        return "blank_challengeable_title_filled_by_stronger_identity_evidence"
    if title_source == "first_page_title_used" or "first_page_title_used" in reasons:
        return "challengeable_first_page_title_replaced_by_stronger_identity_evidence"
    if (
        title_source == "local_pdf_stem_used"
        or record.get("local_pdf_artifact_title")
        or "local_pdf_stem_used" in reasons
        or "local_pdf_artifact_title" in reasons
    ):
        return "challengeable_filename_title_replaced_by_stronger_identity_evidence"
    if title_source == "pdf_metadata_title_used" or "pdf_metadata_title_used" in reasons:
        return "challengeable_pdf_metadata_title_replaced_by_stronger_identity_evidence"
    if "title_query" in sources:
        return "challengeable_title_query_replaced_by_stronger_identity_evidence"
    if "pdf_url" in sources:
        return "challengeable_pdf_url_title_replaced_by_stronger_identity_evidence"
    return ""


def _title_was_replaced(original: dict[str, Any], accepted: dict[str, Any]) -> bool:
    original_title = _string_field(original, "title")
    accepted_title = _string_field(accepted, "title")
    if not accepted_title:
        return False
    if not original_title:
        return True
    return normalize_title(original_title) != normalize_title(accepted_title)


def _resolve_anchor_is_strong(resolve_record: dict[str, Any], key: str) -> bool:
    if not _string_field(resolve_record, key):
        return False
    source_type = _string_field(resolve_record, "source_type").lower()
    if source_type in STRONG_ANCHOR_SOURCE_TYPES.get(key, set()):
        return True
    sources = _metadata_source_set(resolve_record)
    if key == "doi":
        return bool(sources & {"doi", "crossref"})
    if key == "arxiv_id":
        return "arxiv" in sources
    if key == "zotero_key":
        return bool(sources & {"zotero", "zotero_key"})
    return False


def _strong_anchor_conflicts(
    metadata: dict[str, Any],
    resolve_record: dict[str, Any],
) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for key in ("doi", "arxiv_id", "zotero_key"):
        if not _resolve_anchor_is_strong(resolve_record, key):
            continue
        resolve_value = _normalized_anchor_value(key, resolve_record.get(key))
        metadata_value = _normalized_anchor_value(key, metadata.get(key))
        if metadata_value and resolve_value and metadata_value != resolve_value:
            conflicts.append(
                {
                    "kind": key,
                    "accepted_value": _string_field(resolve_record, key),
                    "rejected_value": _string_field(metadata, key),
                }
            )
    return conflicts


def _apply_strong_anchor_protection(
    effective: dict[str, Any],
    resolve_record: dict[str, Any],
    conflicts: list[dict[str, str]],
) -> dict[str, Any]:
    rejected_candidate = work_level_identity_from_record(effective)
    protected_fields = (
        "title",
        "translated_title",
        "authors",
        "year",
        "venue",
        "doi",
        "arxiv_id",
        "zotero_key",
        "source_type",
        "source_url",
        "pdf_url",
        "local_pdf_path",
    )
    removable_fields = {
        "title",
        "translated_title",
        "authors",
        "year",
        "venue",
        "source_url",
        "pdf_url",
    }
    for key in protected_fields:
        if resolve_record.get(key) not in ("", None, [], {}):
            effective[key] = deepcopy(resolve_record[key])
        elif key in removable_fields:
            effective.pop(key, None)
    effective["paper_id"] = _paper_id_for_effective_identity(effective)
    return {
        "attempt": 1,
        "action": "protect_strong_identity_anchor",
        "status": "accepted",
        "evidence_used": _repair_evidence_used(resolve_record),
        "rejected_candidate_identity": rejected_candidate,
        "accepted_correction": work_level_identity_from_record(effective),
        "replacement_reason": "strong_identity_anchor_protected_from_unrelated_provider_evidence",
        "conflicting_anchors": conflicts,
    }


WARNING_SCOPED_METADATA_FIELDS = {
    "year": {
        "reason": "source_manifestation_year_differs_from_work_identity",
        "impact": "avoid_over_specific_year_claims",
    },
    "venue": {
        "reason": "source_manifestation_venue_differs_from_work_identity",
        "impact": "avoid_over_specific_venue_claims",
    },
}


def _metadata_values_differ(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return normalize_title(left) != normalize_title(right)


def _warning_scoped_metadata_uncertainty(
    work_record: dict[str, Any],
    source_record: dict[str, Any],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for field, config in WARNING_SCOPED_METADATA_FIELDS.items():
        work_value = _string_field(work_record, field)
        source_value = _string_field(source_record, field)
        if not _metadata_values_differ(work_value, source_value):
            continue
        warnings.append(
            {
                "reason": config["reason"],
                "scope": "metadata",
                "impact": config["impact"],
                "field": field,
                "work_value": work_value,
                "source_value": source_value,
            }
        )
    return warnings


def _identity_observation_record(observation: dict[str, Any]) -> dict[str, Any]:
    record = observation.get("record")
    if isinstance(record, dict):
        return deepcopy(record)
    return {
        key: deepcopy(value)
        for key, value in observation.items()
        if key not in {"provider", "retrieved_by", "diagnostics", "relation"}
    }


def _identity_observation_summary(
    observation: dict[str, Any],
    *,
    status: str,
    reason: str,
) -> dict[str, Any]:
    record = _identity_observation_record(observation)
    summary = {
        "provider": _string_field(observation, "provider")
        or _string_field(record, "source_type")
        or "unknown",
        "retrieved_by": deepcopy(observation.get("retrieved_by", {}) or {}),
        "status": status,
        "reason": reason,
        "record": record,
    }
    for key in ("relation", "diagnostics"):
        value = observation.get(key)
        if value not in (None, "", [], {}):
            summary[key] = deepcopy(value)
    return summary


def _append_bound_source(
    sources: list[dict[str, str]],
    *,
    kind: str,
    value: str,
    provider: str,
    binding_reason: str,
) -> None:
    cleaned = normalize_whitespace(value)
    if not cleaned or any(item["kind"] == kind and item["value"] == cleaned for item in sources):
        return
    sources.append(
        {
            "kind": kind,
            "value": cleaned,
            "provider": provider or "unknown",
            "binding_reason": binding_reason,
        }
    )


def _bound_sources_from_record(
    record: dict[str, Any],
    *,
    provider: str,
    binding_reason: str,
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    local_pdf = _string_field(record, "local_pdf_path")
    if local_pdf:
        _append_bound_source(
            sources,
            kind="local_pdf",
            value=_path_string(local_pdf),
            provider=provider,
            binding_reason=binding_reason,
        )
    pdf_url = _string_field(record, "pdf_url")
    if pdf_url:
        _append_bound_source(
            sources,
            kind="pdf_url",
            value=pdf_url,
            provider=provider,
            binding_reason=binding_reason,
        )
    source_url = _string_field(record, "source_url")
    if source_url.lower().endswith(".pdf"):
        _append_bound_source(
            sources,
            kind="pdf_url",
            value=source_url,
            provider=provider,
            binding_reason=binding_reason,
        )
    arxiv_id = _record_arxiv_id(record)
    if arxiv_id:
        _append_bound_source(
            sources,
            kind="pdf_url",
            value=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            provider=provider,
            binding_reason="accepted_identifier_derived",
        )
    doi = extract_doi(_string_field(record, "doi")) or ""
    if doi.lower().startswith("10.3389/"):
        _append_bound_source(
            sources,
            kind="pdf_url",
            value=f"https://www.frontiersin.org/articles/{doi}/pdf",
            provider=provider,
            binding_reason="accepted_identifier_derived",
        )
    return sources


def _merge_admitted_observation(
    accepted: dict[str, Any],
    observation: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    merged = deepcopy(accepted)
    for key, value in observation.items():
        if value in ("", None, [], {}):
            continue
        if key == "metadata_sources":
            sources = _dedupe_string_list(merged.get(key, []))
            for source in _dedupe_string_list(value):
                if source not in sources:
                    sources.append(source)
            merged[key] = sources
            continue
        if key == "title":
            observation_title = normalize_whitespace(str(value))
            if (
                observation_title
                and _challengeable_title_replacement_reason(merged)
                and (
                    provider in PROVIDER_IDENTITY_SOURCES
                    or _has_stronger_identity_evidence(observation)
                )
            ):
                merged["title"] = deepcopy(value)
                merged.pop("local_pdf_title_source", None)
                merged.pop("local_pdf_artifact_title", None)
                merged["identity_confidence_reasons"] = [
                    reason
                    for reason in _dedupe_string_list(merged.get("identity_confidence_reasons", []))
                    if reason.lower() not in {
                        "first_page_title_used",
                        "local_pdf_stem_used",
                        "pdf_metadata_title_used",
                        "local_pdf_artifact_title",
                    }
                ]
                continue
        if merged.get(key) in ("", None, [], {}):
            merged[key] = deepcopy(value)
    sources = _dedupe_string_list(merged.get("metadata_sources", []))
    if provider != "unknown" and provider not in sources:
        sources.append(provider)
    if sources:
        merged["metadata_sources"] = sources
    merged["paper_id"] = _paper_id_for_effective_identity(merged)
    return merged


def _is_unique_exact_zotero_title_observation(
    anchor: dict[str, Any],
    item: dict[str, Any],
    observation: dict[str, Any],
) -> bool:
    relation = item.get("relation")
    if not isinstance(relation, dict):
        return False
    anchor_title = normalize_identity_title(_string_field(anchor, "title"))
    observation_title = normalize_identity_title(_string_field(observation, "title"))
    return bool(
        _string_field(item, "provider").lower() == "zotero"
        and _string_field(relation, "kind") == "zotero_lookup"
        and _string_field(relation, "match_kind") == "title"
        and _string_field(relation, "match_resolution") == "unique_exact"
        and _string_field(observation, "zotero_key")
        and anchor_title
        and anchor_title == observation_title
    )


def _is_unique_exact_arxiv_title_observation(
    anchor: dict[str, Any],
    item: dict[str, Any],
    observation: dict[str, Any],
) -> bool:
    relation = item.get("relation")
    if not isinstance(relation, dict):
        return False
    return bool(
        _string_field(item, "provider").lower() == "arxiv"
        and _string_field(relation, "kind") == "arxiv_lookup"
        and _string_field(relation, "match_kind") == "title"
        and _string_field(relation, "match_resolution") == "unique_exact"
        and _record_arxiv_id(observation)
        and normalize_identity_title(_string_field(anchor, "title"))
        == normalize_identity_title(_string_field(observation, "title"))
    )


def adjudicate_identity_observations(
    anchor: dict[str, Any],
    observations: list[Any],
) -> dict[str, Any]:
    accepted_metadata = deepcopy(anchor)
    accepted_metadata.pop("identity_observations", None)
    accepted_observations: list[dict[str, Any]] = []
    rejected_observations: list[dict[str, Any]] = []
    repair_attempts: list[dict[str, Any]] = []
    anchor_provider = _string_field(anchor, "source_type") or "input"
    field_provenance = {
        field: {
            "provider": anchor_provider,
            "retrieved_by": {"kind": "input", "value": _string_field(anchor, "paper_id")},
        }
        for field in PROVENANCE_FIELDS
        if anchor.get(field) not in ("", None, [], {})
    }
    bound_sources = _bound_sources_from_record(
        anchor,
        provider=_string_field(anchor, "source_type") or "input",
        binding_reason="trusted_input",
    )

    for item in observations:
        if not isinstance(item, dict):
            continue
        observation = _identity_observation_record(item)
        adjudication_anchor = accepted_metadata
        shared_identifiers, identifier_conflicts = _shared_identifier_evidence(
            adjudication_anchor,
            observation,
        )
        if identifier_conflicts:
            summary = _identity_observation_summary(
                item,
                status="rejected",
                reason="conflicting_strong_identifier",
            )
            rejected_observations.append(summary)
            repair_attempts.append(
                {
                    "attempt": len(repair_attempts) + 1,
                    "action": "reject_conflicting_provider_observation",
                    "status": "rejected",
                    "evidence_used": _repair_evidence_used(adjudication_anchor),
                    "rejected_candidate_identity": work_level_identity_from_record(
                        observation
                    ),
                    "accepted_correction": work_level_identity_from_record(
                        adjudication_anchor
                    ),
                    "conflicting_anchors": identifier_conflicts,
                }
            )
            continue
        anchor_year = _record_publication_year(adjudication_anchor)
        observation_year = _record_publication_year(observation)
        title_author_year_match = bool(
            normalize_identity_title(_string_field(adjudication_anchor, "title"))
            and normalize_identity_title(_string_field(adjudication_anchor, "title"))
            == normalize_identity_title(_string_field(observation, "title"))
            and _full_leading_author_matches(adjudication_anchor, observation)
            and anchor_year
            and anchor_year == observation_year
        )
        unique_exact_zotero_title_match = _is_unique_exact_zotero_title_observation(
            anchor,
            item,
            observation,
        )
        unique_exact_arxiv_title_match = _is_unique_exact_arxiv_title_observation(
            anchor,
            item,
            observation,
        )
        if not title_author_year_match and not shared_identifiers:
            observation_provider = (
                _string_field(item, "provider")
                or _string_field(observation, "source_type")
            ).lower()
            for other_item in observations:
                if other_item is item or not isinstance(other_item, dict):
                    continue
                other = _identity_observation_record(other_item)
                other_provider = (
                    _string_field(other_item, "provider")
                    or _string_field(other, "source_type")
                ).lower()
                anchor_title = normalize_identity_title(
                    _string_field(anchor, "title")
                )
                observation_title = normalize_identity_title(
                    _string_field(observation, "title")
                )
                other_title = normalize_identity_title(
                    _string_field(other, "title")
                )
                _, provider_conflicts = _shared_identifier_evidence(
                    observation,
                    other,
                )
                if (
                    observation_provider
                    and other_provider
                    and observation_provider != other_provider
                    and not provider_conflicts
                    and anchor_title
                    and anchor_title == observation_title == other_title
                    and _full_leading_author_matches(observation, other)
                    and observation_year
                    and observation_year == _record_publication_year(other)
                ):
                    title_author_year_match = True
                    break
        if (
            not shared_identifiers
            and not title_author_year_match
            and not unique_exact_zotero_title_match
            and not unique_exact_arxiv_title_match
        ):
            rejected_observations.append(
                _identity_observation_summary(
                    item,
                    status="rejected",
                    reason="insufficient_equivalence_evidence",
                )
            )
            continue

        if shared_identifiers:
            acceptance_reason = "shared_identifier"
        elif unique_exact_zotero_title_match:
            acceptance_reason = "unique_exact_zotero_title"
        elif unique_exact_arxiv_title_match:
            acceptance_reason = "unique_exact_arxiv_title"
        else:
            acceptance_reason = "title_author_year"
        summary = _identity_observation_summary(
            item,
            status="accepted",
            reason=acceptance_reason,
        )
        accepted_observations.append(summary)
        provider = summary["provider"]
        observation.setdefault("metadata_sources", [])
        if provider != "unknown" and provider not in observation["metadata_sources"]:
            observation["metadata_sources"].append(provider)
        previous_metadata = deepcopy(accepted_metadata)
        accepted_metadata = _merge_admitted_observation(
            accepted_metadata,
            observation,
            provider,
        )
        retrieved_by = deepcopy(item.get("retrieved_by", {}) or {})
        for field in PROVENANCE_FIELDS:
            value = observation.get(field)
            if value in ("", None, [], {}):
                continue
            if accepted_metadata.get(field) != value:
                continue
            if previous_metadata.get(field) not in ("", None, [], {}):
                if field == "title" and _challengeable_title_replacement_reason(previous_metadata):
                    pass
                else:
                    continue
            field_provenance[field] = {
                "provider": provider,
                "retrieved_by": retrieved_by,
            }
        for source in _bound_sources_from_record(
            observation,
            provider=provider,
            binding_reason=acceptance_reason,
        ):
            _append_bound_source(sources=bound_sources, **source)
        promoted_identifiers = {
            key: _string_field(observation, key)
            for key in ("doi", "arxiv_id", "zotero_key")
            if not _string_field(previous_metadata, key)
            and _string_field(observation, key)
        }
        if promoted_identifiers:
            repair_attempts.append(
                {
                    "attempt": len(repair_attempts) + 1,
                    "action": "accept_identity_promotion",
                    "status": "accepted",
                    "evidence_used": deepcopy(shared_identifiers)
                    or [
                        {
                            "kind": "title_author_year",
                            "value": _string_field(observation, "title"),
                            "source": provider,
                        }
                    ],
                    "rejected_candidate_identity": work_level_identity_from_record(
                        previous_metadata
                    ),
                    "accepted_correction": work_level_identity_from_record(
                        accepted_metadata
                    ),
                    "promoted_identifiers": promoted_identifiers,
                    "previous_paper_id": _string_field(previous_metadata, "paper_id"),
                    "accepted_paper_id": _string_field(accepted_metadata, "paper_id"),
                }
            )

    return {
        "accepted_metadata": apply_identity_confidence(accepted_metadata),
        "accepted_observations": accepted_observations,
        "rejected_observations": rejected_observations,
        "bound_sources": bound_sources,
        "repair_attempts": repair_attempts,
        "field_provenance": field_provenance,
    }


def identity_repair_decision(
    metadata: dict[str, Any],
    *,
    resolve_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observations = metadata.get("identity_observations", []) or []
    observation_decision = adjudicate_identity_observations(
        resolve_record or metadata,
        observations if isinstance(observations, list) else [],
    )
    effective = observation_decision["accepted_metadata"]
    for diagnostic_key in ("provider_unavailable", "provider_status"):
        if metadata.get(diagnostic_key) not in (None, "", False):
            effective[diagnostic_key] = deepcopy(metadata[diagnostic_key])
    repair_attempts = list(observation_decision["repair_attempts"])
    identity_verdict = "accepted"
    failure_class = ""
    unresolved_risks: list[str] = []

    if resolve_record:
        conflicts = _strong_anchor_conflicts(effective, resolve_record)
        if conflicts:
            repair_attempts.append(
                _apply_strong_anchor_protection(effective, resolve_record, conflicts)
            )
        else:
            replacement_reason = _challengeable_title_replacement_reason(resolve_record)
            if (
                replacement_reason
                and _title_was_replaced(resolve_record, effective)
                and _has_stronger_identity_evidence(effective)
            ):
                repair_attempts.append(
                    {
                        "attempt": len(repair_attempts) + 1,
                        "action": "replace_challengeable_identity_anchor",
                        "status": "accepted",
                        "evidence_used": _repair_evidence_used(effective),
                        "rejected_candidate_identity": work_level_identity_from_record(
                            resolve_record
                        ),
                        "accepted_correction": work_level_identity_from_record(effective),
                        "replacement_reason": replacement_reason,
                    }
                )
                effective["paper_id"] = _paper_id_for_effective_identity(effective)

    if _has_provider_unavailable(effective) and not _has_minimum_identity_evidence(
        effective,
        resolve_record,
    ):
        identity_verdict = "failed"
        failure_class = "provider_unavailable"
    elif _has_metadata_contradiction(effective):
        identity_verdict = "failed"
        failure_class = "metadata_contradiction"
    elif not _has_minimum_identity_evidence(effective, resolve_record):
        identity_verdict = "failed"
        failure_class = "insufficient_evidence"

    if failure_class:
        unresolved_risks.append(failure_class)

    bound_sources = list(observation_decision["bound_sources"])
    return {
        "record": effective,
        "identity_verdict": identity_verdict,
        "identity_failure_class": failure_class,
        "repair_attempts": repair_attempts,
        "warnings": [],
        "unresolved_risks": unresolved_risks,
        "accepted_metadata": deepcopy(effective),
        "accepted_observations": observation_decision["accepted_observations"],
        "rejected_observations": observation_decision["rejected_observations"],
        "bound_sources": bound_sources,
        "field_provenance": observation_decision["field_provenance"],
    }


def _equivalence_has_identifier_conflict(equivalence_decision: dict[str, Any]) -> bool:
    return any(
        item.get("kind") == "identifier" and item.get("status") == "conflict"
        for item in equivalence_decision.get("evidence", []) or []
        if isinstance(item, dict)
    )


def _is_source_pdf_record(record: dict[str, Any] | None) -> bool:
    if not record:
        return False
    return bool(
        _string_field(record, "local_pdf_path")
        or _string_field(record, "source_type").lower() == "local_pdf"
    )


def identity_failure_class_for_state(
    decision: dict[str, Any],
    equivalence_decision: dict[str, Any],
    source_record: dict[str, Any] | None,
) -> str:
    failure_class = _string_field(decision, "identity_failure_class")
    if _string_field(equivalence_decision, "status") == "ambiguous":
        if _is_source_pdf_record(source_record):
            return "source_pdf_mismatch"
        if _equivalence_has_identifier_conflict(equivalence_decision):
            return "metadata_contradiction"
        if failure_class not in {"provider_unavailable", "metadata_contradiction"}:
            return "ambiguous_competing_identities"
    return failure_class


def identity_failure_summary(failure_class: str) -> str:
    return IDENTITY_FAILURE_SUMMARIES.get(
        failure_class,
        "Identity repair exhausted: acquisition could not safely choose the paper identity.",
    )


def _repair_attempts_with_failure(
    attempts: list[dict[str, Any]],
    *,
    failure_class: str,
    evidence_used: list[dict[str, str]],
    equivalence_decision: dict[str, Any],
) -> list[dict[str, Any]]:
    if not failure_class:
        return attempts
    repaired = deepcopy(attempts)
    repaired.append(
        {
            "attempt": len(repaired) + 1,
            "action": "repair_exhausted_fail_closed",
            "status": "failed",
            "failure_class": failure_class,
            "evidence_used": evidence_used,
            "unresolved_reason": _string_field(equivalence_decision, "reason") or failure_class,
        }
    )
    return repaired


def identity_contract_state(
    metadata: dict[str, Any],
    *,
    source_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = identity_repair_decision(metadata, resolve_record=source_record)
    effective = decision["record"]
    source_record = source_record or effective
    paper_id = _paper_id_for_effective_identity(effective)
    effective["paper_id"] = paper_id
    accepted_metadata = deepcopy(decision["accepted_metadata"])
    accepted_metadata["paper_id"] = paper_id
    equivalence_decision = manifestation_equivalence_decision(effective, source_record)
    identity_verdict = identity_verdict_from_equivalence(equivalence_decision)
    warnings = []
    if identity_verdict == "accepted":
        identity_verdict = decision["identity_verdict"]
        if identity_verdict == "accepted":
            warnings = deepcopy(decision.get("warnings", []) or [])
            warnings.extend(_warning_scoped_metadata_uncertainty(effective, source_record))
            if warnings:
                identity_verdict = "accepted_with_warnings"
    failure_class = identity_failure_class_for_state(
        decision,
        equivalence_decision,
        source_record,
    )
    selected_evidence = selected_identity_evidence(effective, source_record)
    repair_attempts = _repair_attempts_with_failure(
        decision["repair_attempts"],
        failure_class=failure_class,
        evidence_used=selected_evidence,
        equivalence_decision=equivalence_decision,
    )
    failed = identity_verdict.replace("-", "_") not in ACCEPTED_IDENTITY_VERDICTS
    unresolved_risks = list(decision["unresolved_risks"])
    if failure_class and failure_class not in unresolved_risks:
        unresolved_risks.append(failure_class)
    return {
        "decision": decision,
        "record": effective,
        "source_record": source_record,
        "paper_id": paper_id,
        "identity_verdict": identity_verdict,
        "equivalence_decision": equivalence_decision,
        "warnings": warnings,
        "identity_failure_class": failure_class,
        "selected_identity_evidence": selected_evidence,
        "repair_attempts": repair_attempts,
        "failed": failed,
        "unresolved_risks": unresolved_risks,
        "accepted_metadata": accepted_metadata,
        "accepted_observations": decision["accepted_observations"],
        "rejected_observations": decision["rejected_observations"],
        "bound_sources": decision["bound_sources"],
        "field_provenance": decision["field_provenance"],
    }


def build_identity_repair_trace(
    metadata: dict[str, Any],
    *,
    source_record: dict[str, Any] | None = None,
    resolve_artifact_path: str = "",
    metadata_artifact_path: str = "",
) -> dict[str, Any]:
    state = identity_contract_state(metadata, source_record=source_record)
    failed = state["failed"]
    failure_class = state["identity_failure_class"]
    return {
        "status": "error" if failed else "ok",
        "run_status": "failed" if failed else "ok",
        "script": "build_identity_contract.py",
        "artifact_type": "identity_repair_trace",
        "schema_version": 2,
        "paper_id": state["paper_id"],
        "identity_verdict": state["identity_verdict"],
        "identity_failure_class": failure_class,
        "repair_attempts": state["repair_attempts"],
        "accepted_observations": state["accepted_observations"],
        "rejected_observations": state["rejected_observations"],
        "bound_sources": state["bound_sources"],
        "field_provenance": state["field_provenance"],
        "selected_identity_evidence": state["selected_identity_evidence"],
        "equivalence_decision": state["equivalence_decision"],
        "warnings": state["warnings"],
        "unresolved_risks": state["unresolved_risks"],
        "failure_summary": identity_failure_summary(failure_class) if failed else "",
        "provenance": identity_provenance(
            resolve_artifact_path=resolve_artifact_path,
            metadata_artifact_path=metadata_artifact_path,
        ),
    }


def build_canonical_identity_artifact(
    metadata: dict[str, Any],
    *,
    source_record: dict[str, Any] | None = None,
    repair_trace_path: str = "",
    resolve_artifact_path: str = "",
    metadata_artifact_path: str = "",
) -> dict[str, Any]:
    state = identity_contract_state(metadata, source_record=source_record)
    effective = state["record"]
    source_record = state["source_record"]
    failed = state["failed"]
    failure_class = state["identity_failure_class"]
    return {
        "status": "error" if failed else "ok",
        "run_status": "failed" if failed else "ok",
        "script": "build_identity_contract.py",
        "producer": "build_identity_contract.py",
        "artifact_type": "canonical_identity",
        "schema_version": 2,
        "paper_id": state["paper_id"],
        "identity_verdict": state["identity_verdict"],
        "identity_failure_class": failure_class,
        "failure_summary": identity_failure_summary(failure_class) if failed else "",
        "work_level_identity": work_level_identity_from_record(effective),
        "source_manifestation": source_manifestation_from_record(source_record, effective),
        "accepted_metadata": state["accepted_metadata"],
        "bound_sources": state["bound_sources"],
        "accepted_observations": state["accepted_observations"],
        "rejected_observations": state["rejected_observations"],
        "field_provenance": state["field_provenance"],
        "selected_identity_evidence": state["selected_identity_evidence"],
        "equivalence_decision": state["equivalence_decision"],
        "warnings": state["warnings"],
        "repair_trace_path": _artifact_path(repair_trace_path),
        "provenance": identity_provenance(
            resolve_artifact_path=resolve_artifact_path,
            metadata_artifact_path=metadata_artifact_path,
        ),
        "diagnostics": {
            "identity_confidence": _string_field(effective, "identity_confidence"),
            "identity_confidence_reasons": _dedupe_string_list(
                effective.get("identity_confidence_reasons", [])
            ),
        },
    }


def canonical_identity_acceptance_error(record: dict[str, Any]) -> str:
    artifact_type = _string_field(record, "artifact_type")
    if artifact_type != "canonical_identity":
        return f"non-canonical identity artifact: {artifact_type}"
    if record.get("schema_version") != 2:
        return "canonical identity must use schema v2"
    verdict = _string_field(record, "identity_verdict").lower().replace("-", "_")
    if verdict not in {"accepted", "accepted_with_warnings"}:
        return f"unaccepted canonical identity: identity_verdict={verdict}"
    return ""


def require_accepted_canonical_identity(record: dict[str, Any], consumer: str) -> dict[str, Any]:
    identity = dict(require_ok_input_artifact(record, consumer))
    error = canonical_identity_acceptance_error(identity)
    if error:
        raise SystemExit(f"{consumer} refuses {error}")
    return identity


def canonical_identity_summary(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": _string_field(identity, "artifact_type"),
        "schema_version": identity.get("schema_version", 0),
        "paper_id": _string_field(identity, "paper_id"),
        "identity_verdict": _string_field(identity, "identity_verdict"),
        "work_level_identity": deepcopy(identity.get("work_level_identity", {}) or {}),
        "source_manifestation": deepcopy(identity.get("source_manifestation", {}) or {}),
        "accepted_metadata": deepcopy(identity.get("accepted_metadata", {}) or {}),
        "bound_sources": deepcopy(identity.get("bound_sources", []) or []),
        "field_provenance": deepcopy(identity.get("field_provenance", {}) or {}),
        "selected_identity_evidence": deepcopy(
            identity.get("selected_identity_evidence", []) or []
        ),
        "equivalence_decision": deepcopy(identity.get("equivalence_decision", {}) or {}),
        "warnings": deepcopy(identity.get("warnings", []) or []),
        "repair_trace_path": _string_field(identity, "repair_trace_path"),
        "provenance": deepcopy(identity.get("provenance", {}) or {}),
    }


def require_accepted_fetch_artifact(
    record: dict[str, Any],
    consumer: str,
) -> dict[str, Any]:
    artifact = dict(require_ok_input_artifact(record, consumer))
    if _string_field(artifact, "script") != "fetch_pdf.py":
        raise SystemExit(f"{consumer} requires a fetch_pdf.py artifact.")
    identity = artifact.get("identity_contract")
    if not isinstance(identity, dict):
        raise SystemExit(f"{consumer} requires an embedded canonical identity contract.")
    require_accepted_canonical_identity(identity, consumer)
    canonical_paper_id = _string_field(identity, "paper_id")
    artifact_paper_id = _string_field(artifact, "paper_id")
    if not canonical_paper_id or artifact_paper_id != canonical_paper_id:
        raise SystemExit(f"{consumer} requires fetch paper_id to match canonical identity.")
    return artifact


def fetch_record_from_canonical_identity(identity: dict[str, Any]) -> dict[str, Any]:
    work_identity = identity.get("work_level_identity", {}) or {}
    source_manifestation = identity.get("source_manifestation", {}) or {}
    record: dict[str, Any] = {
        "status": "ok",
        "paper_id": identity.get("paper_id") or paper_id_for_record(work_identity),
        "title": work_identity.get("title") or source_manifestation.get("title", ""),
        "authors": work_identity.get("authors", []) or [],
        "year": work_identity.get("year", ""),
        "venue": work_identity.get("venue", ""),
        "doi": work_identity.get("doi") or source_manifestation.get("doi", ""),
        "arxiv_id": work_identity.get("arxiv_id") or source_manifestation.get("arxiv_id", ""),
        "zotero_key": work_identity.get("zotero_key") or source_manifestation.get("zotero_key", ""),
        "source_type": source_manifestation.get("source_kind", ""),
        "source_url": source_manifestation.get("source_url", ""),
        "pdf_url": source_manifestation.get("pdf_url", ""),
        "local_pdf_path": source_manifestation.get("local_pdf_path", ""),
        "identity_contract": canonical_identity_summary(identity),
        "source_manifestation": deepcopy(source_manifestation),
    }
    return {key: value for key, value in record.items() if value not in ("", None, [], {})}


def fallback_arxiv_record(arxiv_id: str, source_type: str, source_url: str = "") -> dict[str, Any]:
    paper = {
        "status": "ok",
        "source_type": source_type,
        "source_url": source_url or f"https://arxiv.org/abs/{arxiv_id}",
        "arxiv_id": arxiv_id,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "metadata_sources": [source_type],
    }
    paper["paper_id"] = paper_id_for_record(paper)
    return apply_identity_confidence(paper)


def http_get_text(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=https_ssl_context(url)) as response:
        return response.read().decode("utf-8")


def http_get_json(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return json.loads(http_get_text(url, timeout=timeout, headers=headers))


def http_get_bytes(url: str, *, timeout: int = 60, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=https_ssl_context(url)) as response:
        return response.read()


def https_ssl_context(url: str) -> ssl.SSLContext | None:
    if not str(url).lower().startswith("https://") or certifi is None:
        return None
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def semantic_scholar_headers() -> dict[str, str]:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    api_key = env_config_value("DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY", "SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def parse_arxiv_xml(xml_content: str) -> list[dict[str, Any]]:
    papers: list[dict[str, Any]] = []
    root = ET.fromstring(xml_content)
    for entry in root.findall("atom:entry", ARXIV_NS):
        paper: dict[str, Any] = {
            "source": "arxiv",
            "source_type": "arxiv",
            "metadata_sources": ["arxiv"],
        }
        id_elem = entry.find("atom:id", ARXIV_NS)
        if id_elem is not None and id_elem.text:
            paper["source_url"] = normalize_whitespace(id_elem.text)
            paper["url"] = paper["source_url"]
            arxiv_id = extract_arxiv_id(paper["source_url"])
            if arxiv_id:
                paper["arxiv_id"] = arxiv_id

        title_elem = entry.find("atom:title", ARXIV_NS)
        paper["title"] = normalize_whitespace(title_elem.text if title_elem is not None else "")

        summary_elem = entry.find("atom:summary", ARXIV_NS)
        paper["abstract"] = normalize_whitespace(summary_elem.text if summary_elem is not None else "")

        journal_ref_elem = entry.find("arxiv:journal_ref", ARXIV_NS)
        journal_ref = normalize_whitespace(journal_ref_elem.text if journal_ref_elem is not None else "")
        if journal_ref:
            paper["venue"] = journal_ref

        doi_elem = entry.find("arxiv:doi", ARXIV_NS)
        if doi_elem is not None and doi_elem.text:
            paper["doi"] = normalize_whitespace(doi_elem.text)

        authors = []
        for author in entry.findall("atom:author", ARXIV_NS):
            name_elem = author.find("atom:name", ARXIV_NS)
            if name_elem is not None and name_elem.text:
                authors.append(normalize_whitespace(name_elem.text))
        paper["authors"] = authors

        published_elem = entry.find("atom:published", ARXIV_NS)
        if published_elem is not None and published_elem.text:
            paper["published"] = normalize_whitespace(published_elem.text)
            if re.match(r"^\d{4}", paper["published"]):
                paper["year"] = paper["published"][:4]

        for link in entry.findall("atom:link", ARXIV_NS):
            if link.get("title") == "pdf" and link.get("href"):
                paper["pdf_url"] = str(link.get("href"))
                break

        papers.append(paper)
    return papers


def fetch_arxiv_entries(*, search_query: str = "", id_list: str = "", max_results: int = 10) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "id_list": id_list,
            "start": 0,
            "max_results": max_results,
        }
    )
    try:
        xml_content = http_get_text(f"https://export.arxiv.org/api/query?{params}")
    except Exception:
        return []
    if not normalize_whitespace(xml_content):
        return []
    try:
        return parse_arxiv_xml(xml_content)
    except Exception:
        return []


def safe_fetch_arxiv_entries(*, search_query: str = "", id_list: str = "", max_results: int = 10) -> list[dict[str, Any]]:
    try:
        return fetch_arxiv_entries(search_query=search_query, id_list=id_list, max_results=max_results)
    except Exception:
        return []


def normalize_crossref_work(item: dict[str, Any]) -> dict[str, Any]:
    title = normalize_whitespace(" ".join(item.get("title") or []))
    # Crossref splits "LightGCN: Simplifying ..." into title and subtitle.
    subtitle = normalize_whitespace(" ".join(item.get("subtitle") or []))
    if subtitle and subtitle.casefold() not in title.casefold():
        title = f"{title}: {subtitle}" if title else subtitle
    authors = []
    affiliations = []
    for author in item.get("author", []) or []:
        given = normalize_whitespace(str(author.get("given", "")))
        family = normalize_whitespace(str(author.get("family", "")))
        name = normalize_whitespace(" ".join(part for part in [given, family] if part))
        if name:
            authors.append(name)
        for aff in author.get("affiliation", []) or []:
            aff_name = normalize_whitespace(str(aff.get("name", "")))
            if aff_name and aff_name not in affiliations:
                affiliations.append(aff_name)
    venue = normalize_whitespace(" ".join(item.get("container-title") or []))
    published = (
        item.get("published-print", {}).get("date-parts")
        or item.get("published-online", {}).get("date-parts")
        or item.get("issued", {}).get("date-parts")
        or []
    )
    year = ""
    if published and isinstance(published, list) and isinstance(published[0], list) and published[0]:
        year = str(published[0][0])
    doi = normalize_whitespace(str(item.get("DOI", "")))
    source_url = normalize_whitespace(str(item.get("URL", "")))
    return {
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "venue": venue,
        "doi": doi,
        "source": "crossref",
        "source_type": "crossref",
        "source_url": source_url,
        "year": year,
        "published": year,
        "abstract": strip_tags(str(item.get("abstract", ""))),
        "metadata_sources": ["crossref"],
    }


def fetch_crossref_by_doi(doi: str) -> dict[str, Any] | None:
    url = f"{CROSSREF_WORKS_URL}/{urllib.parse.quote(doi)}"
    try:
        data = http_get_json(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    except Exception:
        return None
    message = data.get("message") or {}
    if not isinstance(message, dict):
        return None
    return normalize_crossref_work(message)


def search_crossref_by_title(title: str, *, limit: int = 5) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query.title": title, "rows": limit})
    try:
        data = http_get_json(f"{CROSSREF_WORKS_URL}?{params}", headers={"User-Agent": DEFAULT_USER_AGENT})
    except Exception:
        return []
    items = data.get("message", {}).get("items", []) or []
    return [normalize_crossref_work(item) for item in items if isinstance(item, dict)]


def normalize_semantic_scholar_paper(paper: dict[str, Any]) -> dict[str, Any]:
    ext_ids = paper.get("externalIds") or {}
    doi = normalize_whitespace(str(ext_ids.get("DOI", "")))
    arxiv_id = normalize_whitespace(str(ext_ids.get("ArXiv", "")))
    affiliations: list[str] = []
    authors: list[str] = []
    for author in paper.get("authors", []) or []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(str(author.get("name", "")))
        if name:
            authors.append(name)
        raw_affs = author.get("affiliations", []) or []
        if isinstance(raw_affs, str):
            raw_affs = [raw_affs]
        for aff in raw_affs:
            aff_name = normalize_whitespace(str(aff))
            if aff_name and aff_name not in affiliations:
                affiliations.append(aff_name)
    result = {
        "title": normalize_whitespace(str(paper.get("title", ""))),
        "abstract": normalize_whitespace(str(paper.get("abstract", ""))),
        "authors": authors,
        "affiliations": affiliations,
        "venue": normalize_whitespace(str(paper.get("venue", ""))),
        "year": normalize_whitespace(str(paper.get("year", ""))),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "source": "semantic_scholar",
        "source_type": "semantic_scholar",
        "source_url": normalize_whitespace(str(paper.get("url", ""))),
        "metadata_sources": ["semantic_scholar"],
    }
    if arxiv_id and not result.get("pdf_url"):
        result["pdf_url"] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return result


def search_semantic_scholar(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,venue,url,externalIds,authors.name,authors.affiliations",
        }
    )
    try:
        data = http_get_json(
            f"{SEMANTIC_SCHOLAR_SEARCH_URL}?{params}",
            headers=semantic_scholar_headers(),
        )
    except Exception:
        return []
    items = data.get("data", []) or []
    return [normalize_semantic_scholar_paper(item) for item in items if isinstance(item, dict)]


def normalize_openalex_work(item: dict[str, Any]) -> dict[str, Any]:
    title = normalize_whitespace(str(item.get("display_name", "")))
    authors = []
    affiliations = []
    for authorship in item.get("authorships", []) or []:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author", {}) or {}
        name = normalize_whitespace(str(author.get("display_name", "")))
        if name:
            authors.append(name)
        for institution in authorship.get("institutions", []) or []:
            if not isinstance(institution, dict):
                continue
            inst_name = normalize_whitespace(str(institution.get("display_name", "")))
            if inst_name and inst_name not in affiliations:
                affiliations.append(inst_name)
    ids = item.get("ids", {}) or {}
    doi_url = normalize_whitespace(str(ids.get("doi", "")))
    doi = extract_doi(doi_url or normalize_whitespace(str(item.get("doi", "")))) or ""
    primary_location = item.get("primary_location", {}) or {}
    pdf_url = normalize_whitespace(str((primary_location.get("pdf_url") or "")))
    landing_page_url = normalize_whitespace(str(primary_location.get("landing_page_url") or ""))
    best_oa = item.get("best_oa_location", {}) or {}
    if not pdf_url:
        pdf_url = normalize_whitespace(str(best_oa.get("pdf_url") or ""))
    if not landing_page_url:
        landing_page_url = normalize_whitespace(str(best_oa.get("landing_page_url") or ""))
    venue = normalize_whitespace(str((primary_location.get("source", {}) or {}).get("display_name", "")))
    year = normalize_whitespace(str(item.get("publication_year", "")))
    return {
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "venue": venue,
        "year": year,
        "doi": doi,
        "source": "openalex",
        "source_type": "openalex",
        "source_url": landing_page_url or normalize_whitespace(str(item.get("id", ""))),
        "pdf_url": pdf_url,
        "abstract": "",
        "metadata_sources": ["openalex"],
    }


def fetch_openalex_by_doi(doi: str) -> dict[str, Any] | None:
    url = f"{OPENALEX_WORKS_URL}/https://doi.org/{urllib.parse.quote(doi, safe='')}"
    try:
        data = http_get_json(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return normalize_openalex_work(data)


def search_openalex_by_title(title: str, *, limit: int = 5) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search": title, "per-page": limit})
    try:
        data = http_get_json(f"{OPENALEX_WORKS_URL}?{params}", headers={"User-Agent": DEFAULT_USER_AGENT})
    except Exception:
        return []
    items = data.get("results", []) or []
    return [normalize_openalex_work(item) for item in items if isinstance(item, dict)]


def merge_metadata_records(*records: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    metadata_sources: list[str] = []
    additive_list_fields = {"affiliations", "metadata_sources", "identity_confidence_reasons"}
    for record in records:
        if not isinstance(record, dict):
            continue
        for key, value in record.items():
            if value in ("", None, [], {}):
                continue
            if key == "authors":
                if not merged.get("authors"):
                    values = value if isinstance(value, list) else [value]
                    seen = set()
                    deduped = []
                    for item in values:
                        cleaned = normalize_whitespace(str(item))
                        marker = normalize_title(cleaned)
                        if cleaned and marker and marker not in seen:
                            deduped.append(cleaned)
                            seen.add(marker)
                    if deduped:
                        merged["authors"] = deduped
                continue
            if key in additive_list_fields:
                current = merged.setdefault(key, [])
                if not isinstance(current, list):
                    current = []
                    merged[key] = current
                values = value if isinstance(value, list) else [value]
                for item in values:
                    cleaned = normalize_whitespace(str(item))
                    if cleaned and cleaned not in current:
                        current.append(cleaned)
                continue
            if key not in merged or merged[key] in ("", None):
                merged[key] = value
    for record in records:
        if isinstance(record, dict):
            for source in record.get("metadata_sources", []) or []:
                source_name = normalize_whitespace(str(source))
                if source_name and source_name not in metadata_sources:
                    metadata_sources.append(source_name)
    if metadata_sources:
        merged["metadata_sources"] = metadata_sources
    merged["paper_id"] = paper_id_for_record(merged)
    return merged


def choose_best_title_match(title: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (
            title_similarity(title, str(item.get("title", ""))),
            candidate_priority_score(item),
            publication_quality_score(item),
            1 if item.get("doi") else 0,
            1 if item.get("pdf_url") else 0,
            1 if item.get("abstract") else 0,
        ),
        reverse=True,
    )
    best = ranked[0]
    if title_similarity(title, str(best.get("title", ""))) < 0.55:
        return None
    return best


def _record_publication_year(record: dict[str, Any]) -> str:
    for key in ("year", "published"):
        match = re.search(r"(?<!\d)((?:18|19|20|21)\d{2})(?!\d)", _string_field(record, key))
        if match:
            return match.group(1)
    return ""


def _has_strong_work_identifier(record: dict[str, Any]) -> bool:
    paper_id = _string_field(record, "paper_id").lower()
    return bool(
        extract_doi(_string_field(record, "doi"))
        or extract_doi(_string_field(record, "source_url"))
        or _record_arxiv_id(record)
        or paper_id.startswith(("doi:", "arxiv:"))
    )


def resolve_reference(value: str) -> dict[str, Any]:
    source_type = infer_source_type(value)
    stripped = (value or "").strip()
    if source_type == "local_pdf":
        path = Path(stripped).expanduser().resolve()
        hints = extract_local_pdf_hints(path)
        paper = {
            "status": "ok",
            "source_type": "local_pdf",
            "source_url": str(path),
            "local_pdf_path": str(path),
            "title": normalize_whitespace(str(hints.get("title", ""))) or clean_local_pdf_stem(path.stem) or path.stem.replace("_", " "),
            "metadata_sources": ["local_pdf"],
        }
        if hints.get("local_pdf_title_source"):
            paper["local_pdf_title_source"] = hints["local_pdf_title_source"]
        if hints.get("local_pdf_artifact_title"):
            paper["local_pdf_artifact_title"] = True
        doi = normalize_whitespace(str(hints.get("doi", "")))
        arxiv_id = normalize_whitespace(str(hints.get("arxiv_id", "")))
        if doi:
            paper["doi"] = doi
        if arxiv_id:
            paper["arxiv_id"] = arxiv_id
        paper["paper_id"] = paper_id_for_record(paper)
        return apply_identity_confidence(paper)
    if source_type == "arxiv_id":
        arxiv_id = extract_arxiv_id(stripped) or ""
        if arxiv_id:
            return fallback_arxiv_record(arxiv_id, "arxiv_id")
    if source_type == "arxiv_url":
        arxiv_id = extract_arxiv_id(stripped) or ""
        if arxiv_id:
            return fallback_arxiv_record(arxiv_id, "arxiv_url", source_url=stripped)
    if source_type in {"doi", "doi_url"}:
        doi = extract_doi(stripped) or ""
        paper = {
            "status": "ok",
            "source_type": "doi",
            "source_url": f"https://doi.org/{doi}",
            "doi": doi,
            "metadata_sources": ["doi"],
        }
        paper["paper_id"] = paper_id_for_record(paper)
        return apply_identity_confidence(paper)
    if source_type == "pdf_url":
        filename = Path(urllib.parse.urlparse(stripped).path).stem or "paper"
        paper = {
            "status": "ok",
            "source_type": "pdf_url",
            "source_url": stripped,
            "pdf_url": stripped,
            "title": filename.replace("_", " "),
            "metadata_sources": ["pdf_url"],
        }
        paper["paper_id"] = paper_id_for_record(paper)
        return apply_identity_confidence(paper)
    if source_type == "url":
        doi = extract_doi(stripped)
        if doi:
            return resolve_reference(doi)
        paper = {
            "status": "ok",
            "source_type": "url",
            "source_url": stripped,
            "metadata_sources": ["url"],
        }
        paper["paper_id"] = paper_id_for_record(paper)
        return apply_identity_confidence(paper)
    if source_type == "zotero_key":
        paper = {
            "status": "ok",
            "source_type": "zotero_key",
            "zotero_key": stripped,
            "source_url": "",
            "metadata_sources": ["zotero_key"],
        }
        paper["paper_id"] = paper_id_for_record(paper)
        return apply_identity_confidence(paper)

    title = stripped
    paper = {
        "status": "ok",
        "source_type": "title_query",
        "title": title,
        "source_url": "",
        "metadata_sources": ["title_query"],
    }
    paper["paper_id"] = paper_id_for_record(paper)
    return apply_identity_confidence(paper)


def collect_metadata_observations(record: dict[str, Any]) -> list[dict[str, Any]]:
    base = dict(record)
    observations = [
        deepcopy(item)
        for item in base.get("identity_observations", []) or []
        if isinstance(item, dict)
    ]
    doi = normalize_whitespace(str(base.get("doi", "")))
    title = normalize_whitespace(str(base.get("title", "")))
    arxiv_id = normalize_whitespace(str(base.get("arxiv_id", "")))

    def append(
        provider: str,
        kind: str,
        value: str,
        candidate: dict[str, Any] | None,
        relation: dict[str, str] | None = None,
    ) -> None:
        if not candidate:
            return
        observation = {
            "provider": provider,
            "retrieved_by": {"kind": kind, "value": value},
            "record": deepcopy(candidate),
        }
        if relation:
            observation["relation"] = relation
        if observation not in observations:
            observations.append(observation)

    if doi:
        crossref = fetch_crossref_by_doi(doi)
        append("crossref", "doi", doi, crossref)
        openalex = fetch_openalex_by_doi(doi)
        append("openalex", "doi", doi, openalex)
        sem = choose_best_title_match(title or doi, search_semantic_scholar(doi, limit=3))
        append("semantic_scholar", "doi", doi, sem)

    if arxiv_id:
        arxiv = safe_fetch_arxiv_entries(id_list=arxiv_id, max_results=1)
        if arxiv:
            append("arxiv", "arxiv_id", arxiv_id, arxiv[0])

    if title:
        sem = choose_best_title_match(title, search_semantic_scholar(title, limit=5))
        append("semantic_scholar", "title", title, sem)
        oa = choose_best_title_match(title, search_openalex_by_title(title, limit=5))
        append("openalex", "title", title, oa)
        cross = choose_best_title_match(title, search_crossref_by_title(title, limit=5))
        append("crossref", "title", title, cross)
        arxiv_candidates = safe_fetch_arxiv_entries(
            search_query=f'ti:"{title}"', max_results=5
        )
        arxiv = choose_best_title_match(title, arxiv_candidates)
        exact_matches = [
            candidate
            for candidate in arxiv_candidates
            if normalize_identity_title(_string_field(candidate, "title"))
            == normalize_identity_title(title)
        ]
        relation = (
            {
                "kind": "arxiv_lookup",
                "match_kind": "title",
                "match_resolution": "unique_exact",
            }
            if arxiv is not None and len(exact_matches) == 1 and arxiv == exact_matches[0]
            else None
        )
        append("arxiv", "title", title, arxiv, relation)

    return observations


def enrich_metadata(record: dict[str, Any]) -> dict[str, Any]:
    base = dict(record)
    observations = collect_metadata_observations(base)
    merged = adjudicate_identity_observations(base, observations)["accepted_metadata"]
    if not merged.get("year") and merged.get("published") and re.match(r"^\d{4}", str(merged["published"])):
        merged["year"] = str(merged["published"])[:4]
    if merged.get("doi") and not merged.get("source_url"):
        merged["source_url"] = f"https://doi.org/{merged['doi']}"
    if merged.get("arxiv_id") and not merged.get("pdf_url"):
        merged["pdf_url"] = f"https://arxiv.org/pdf/{merged['arxiv_id']}.pdf"
    if merged.get("arxiv_id") and not merged.get("doi"):
        merged["doi"] = f"10.48550/arXiv.{merged['arxiv_id']}"
    merged["paper_id"] = paper_id_for_record(merged)
    return apply_identity_confidence(merged)


def runtime_config(
    *,
    explicit_overrides: dict[str, Any] | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_run_overrides(
        explicit_overrides=explicit_overrides,
        cli_overrides=cli_overrides,
    )
    if resolved["issues"] or resolved["missing"]:
        inspection = inspect_configuration()
        if inspection["state"] != "ready":
            raise RuntimeError(json.dumps(inspection, ensure_ascii=False, sort_keys=True))
        resolved = resolve_preferences(
            explicit_overrides=explicit_overrides,
            cli_overrides=cli_overrides,
        )
        if resolved["issues"] or resolved["missing"]:
            raise RuntimeError(json.dumps(resolved, ensure_ascii=False, sort_keys=True))
    return {
        "obsidian_vault": "",
        "papers_dir": "",
        **resolved["values"],
        "output_dir": env_config_value("DEEPPAPERNOTE_OUTPUT_DIR", default="tmp/DeepPaperNote"),
        "workspace_output_dir": env_config_value(
            "DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR",
            default="DeepPaperNote_output",
        ),
    }


def default_pdf_path(record: dict[str, Any], dest_dir: str | None = None) -> Path:
    config = runtime_config()
    base_dir = Path(dest_dir or config["output_dir"]).expanduser().resolve() / "pdfs"
    base_dir.mkdir(parents=True, exist_ok=True)
    title = str(record.get("title") or record.get("paper_id") or "paper")
    return base_dir / f"{slugify_filename(title)}.pdf"


def default_assets_dir(record: dict[str, Any], dest_dir: str | None = None) -> Path:
    config = runtime_config()
    base_dir = Path(dest_dir or config["output_dir"]).expanduser().resolve() / "assets"
    title = str(record.get("title") or record.get("paper_id") or "paper")
    asset_dir = base_dir / slugify_filename(title)
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def clean_pdf_line(line: str) -> str:
    line = re.sub(r"\s+", " ", normalize_pdf_text_artifacts(line or "")).strip()
    if not line:
        return ""
    if re.fullmatch(r"\d+", line):
        return ""
    if re.fullmatch(r"page \d+", line.lower()):
        return ""
    if len(line) <= 2 and not re.search(r"[\u3400-\u9fff]", line):
        return ""
    return line


def normalize_heading(line: str) -> str:
    line = normalize_pdf_text_artifacts(line or "").strip().lower()
    line = re.sub(r"^\s*(?:section\s*)?\d+(\.\d+)*[\s.、．:：-]*", "", line)
    line = re.sub(r"^\s*[一二三四五六七八九十百千]+[、．.:\s-]*", "", line)
    line = re.sub(r"^\s*[ivxlcdm]+[.)\s]+", "", line)
    line = re.sub(r"[^a-z0-9\u3400-\u9fff\s]", " ", line)
    line = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", line)
    return re.sub(r"\s+", " ", line).strip()


SECTION_ALIASES = {
    "abstract": {"abstract", "摘要"},
    "introduction": {
        "introduction",
        "background",
        "preliminaries",
        "preliminary",
        "related work",
        "literature review",
        "引言",
        "绪论",
        "背景",
        "相关工作",
        "文献综述",
    },
    "method": {
        "method",
        "methods",
        "approach",
        "approaches",
        "methodology",
        "framework",
        "model",
        "models",
        "materials",
        "materials and methods",
        "study design",
        "方法",
        "方法学",
        "研究方法",
        "材料与方法",
        "实验方法",
        "研究设计",
        "模型",
        "框架",
        "系统设计",
    },
    "data": {
        "data",
        "dataset",
        "datasets",
        "corpus",
        "data and materials",
        "数据",
        "数据集",
        "语料库",
    },
    "experiment": {
        "experiment",
        "experiments",
        "evaluation",
        "evaluations",
        "results",
        "experimental results",
        "evaluation results",
        "analysis",
        "findings",
        "ablations",
        "ablation",
        "实验",
        "实验结果",
        "结果",
        "研究结果",
        "评价",
        "评估",
        "分析",
        "发现",
        "消融",
    },
    "conclusion": {
        "conclusion",
        "conclusions",
        "discussion",
        "discussions",
        "future work",
        "limitations",
        "limitation",
        "结论",
        "总结",
        "讨论",
        "局限",
        "不足",
        "未来工作",
    },
}

STOP_SECTION_ALIASES = {
    "references",
    "bibliography",
    "appendix",
    "appendices",
    "supplementary material",
    "acknowledgments",
    "acknowledgements",
    "参考文献",
    "附录",
    "补充材料",
    "致谢",
}

STOP_SECTION_REASONS = {
    "references": "references",
    "bibliography": "references",
    "参考文献": "references",
    "appendix": "appendix",
    "appendices": "appendix",
    "supplementary material": "appendix",
    "附录": "appendix",
    "补充材料": "appendix",
    "acknowledgments": "acknowledgments",
    "acknowledgements": "acknowledgments",
    "致谢": "acknowledgments",
}


def match_section_heading(line: str) -> str | None:
    normalized = normalize_heading(line)
    if not normalized:
        return None
    if normalized in STOP_SECTION_ALIASES:
        return "stop"
    for section, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section
    return None


def stop_section_reason(line: str, *, allow_prefix: bool = False) -> str:
    normalized = normalize_heading(line)
    if not normalized:
        return ""
    reason = STOP_SECTION_REASONS.get(normalized, "")
    if reason or not allow_prefix:
        return reason
    if normalized.startswith(("references ", "bibliography ")):
        return "references"
    if normalized.startswith(("appendix ", "appendices ", "supplementary material ")):
        return "appendix"
    if normalized.startswith(("acknowledgments ", "acknowledgements ")):
        return "acknowledgments"
    return ""


def pdf_coverage_summary(pdf_path: Path, max_pages: int | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total_pages": None,
        "text_max_pages": max_pages,
        "text_pages_scanned": 0,
        "truncated_due_to_page_limit": False,
        "appendix_detected": False,
        "appendix_start_page": None,
        "references_start_page": None,
        "section_stop_reason": "",
        "section_stop_page": None,
    }
    if fitz is None or not pdf_path.is_file():
        return summary

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return summary

    try:
        total_pages = len(doc)
        page_limit = total_pages if max_pages is None else min(total_pages, max_pages)
        summary["total_pages"] = total_pages
        summary["text_pages_scanned"] = page_limit
        summary["truncated_due_to_page_limit"] = max_pages is not None and total_pages > max_pages

        for page_index in range(total_pages):
            page_number = page_index + 1
            text = doc[page_index].get_text("text")
            for raw_line in text.splitlines():
                line = clean_pdf_line(raw_line)
                if not line:
                    continue
                exact_reason = stop_section_reason(line)
                detected_reason = exact_reason or stop_section_reason(line, allow_prefix=True)
                if not detected_reason:
                    continue
                if detected_reason == "references" and summary["references_start_page"] is None:
                    summary["references_start_page"] = page_number
                if detected_reason == "appendix" and summary["appendix_start_page"] is None:
                    summary["appendix_start_page"] = page_number
                    summary["appendix_detected"] = True
                if exact_reason and not summary["section_stop_reason"]:
                    summary["section_stop_reason"] = exact_reason
                    summary["section_stop_page"] = page_number
                break
    finally:
        doc.close()
    return summary


def extract_appendix_page_texts(
    pdf_path: Path,
    appendix_start_page: int | None,
) -> list[dict[str, Any]]:
    if fitz is None or not pdf_path.is_file() or not appendix_start_page:
        return []

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    pages: list[dict[str, Any]] = []
    try:
        start_index = max(int(appendix_start_page) - 1, 0)
        for page_index in range(start_index, len(doc)):
            text = doc[page_index].get_text("text")
            cleaned = normalize_whitespace(text)
            if cleaned:
                pages.append({"page": page_index + 1, "text": text})
    finally:
        doc.close()
    return pages


def appendix_section_title(line: str) -> str:
    cleaned = clean_pdf_line(line)
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower in {"appendix", "appendices", "supplementary material"}:
        return ""
    if re.match(r"^fig(?:ure)?\.?\s*\d+", cleaned, re.IGNORECASE):
        return ""
    if re.match(r"^table\.?\s*\d+", cleaned, re.IGNORECASE):
        return ""
    if len(cleaned) > 120:
        return ""
    if re.match(r"^(?:appendix\s+)?[A-Z]\.?\s+.{3,}$", cleaned, re.IGNORECASE):
        return cleaned
    return ""


def extract_appendix_index(
    pdf_path: Path,
    pdf_coverage: dict[str, Any] | None = None,
    *,
    max_sections: int = 20,
    max_captions: int = 24,
) -> dict[str, Any]:
    pdf_coverage = pdf_coverage or {}
    start_page = pdf_coverage.get("appendix_start_page")
    index: dict[str, Any] = {
        "appendix_detected": bool(pdf_coverage.get("appendix_detected")),
        "start_page": start_page,
        "sections": [],
        "figure_captions": [],
        "table_captions": [],
    }
    if not index["appendix_detected"] or not start_page:
        return index

    seen_sections = set()
    seen_figure_captions = set()
    seen_table_captions = set()
    for page in extract_appendix_page_texts(pdf_path, int(start_page)):
        page_number = int(page.get("page", 0) or 0)
        text = str(page.get("text", ""))
        for raw_line in text.splitlines():
            title = appendix_section_title(raw_line)
            marker = normalize_title(title)
            if title and marker not in seen_sections and len(index["sections"]) < max_sections:
                seen_sections.add(marker)
                index["sections"].append({"title": title, "page": page_number})

        for caption in extract_caption_lines(text, "figure"):
            marker = f"{caption.get('id', '').lower()}::{caption.get('caption', '').lower()}"
            if marker in seen_figure_captions or len(index["figure_captions"]) >= max_captions:
                continue
            seen_figure_captions.add(marker)
            index["figure_captions"].append({**caption, "page_hint": f"p.{page_number}"})

        for caption in extract_caption_lines(text, "table"):
            marker = f"{caption.get('id', '').lower()}::{caption.get('caption', '').lower()}"
            if marker in seen_table_captions or len(index["table_captions"]) >= max_captions:
                continue
            seen_table_captions.add(marker)
            index["table_captions"].append({**caption, "page_hint": f"p.{page_number}"})
    return index


def extract_pdf_sections(pdf_path: Path, max_pages: int | None = None) -> dict[str, str]:
    if fitz is None:
        return {}
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    doc = fitz.open(pdf_path)
    try:
        page_limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        for page_index in range(page_limit):
            text = doc[page_index].get_text("text")
            reached_stop = False
            for raw_line in text.splitlines():
                line = clean_pdf_line(raw_line)
                if not line:
                    continue
                heading = match_section_heading(line)
                if heading == "stop":
                    reached_stop = True
                    break
                if heading:
                    current = heading
                    sections.setdefault(current, [])
                    continue
                sections.setdefault(current, []).append(line)
            if reached_stop:
                break
    finally:
        doc.close()

    collapsed = {}
    for key, value in sections.items():
        if not value:
            continue
        text = re.sub(r"\s+", " ", " ".join(value)).strip()
        if text:
            collapsed[key] = text
    return collapsed


def extract_pdf_text(pdf_path: Path, max_pages: int | None = None) -> str:
    if fitz is None:
        return ""
    doc = fitz.open(pdf_path)
    try:
        page_limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        texts = [doc[i].get_text("text") for i in range(page_limit)]
    finally:
        doc.close()
    return "\n".join(texts)


TITLE_MIN_LETTER_SHARE = 0.6
TITLE_MAX_GARBLE_SHARE = 0.05
TITLE_GARBLE_CHARS = set("!\"#$%*<=>@[\\]^_`{|}~")
TITLE_LINE_SIZE_RATIO = 0.9
TITLE_LINE_SPACING = 1.6
TITLE_FOOTNOTE_MARKS_RE = re.compile(r"[\s*∗†‡§¶]+$")
CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")


def is_mostly_letters(text: str) -> bool:
    """Tell readable words from a garbled text layer, which decodes to stray symbols."""
    visible = [char for char in TITLE_FOOTNOTE_MARKS_RE.sub("", text) if not char.isspace()]
    if not visible:
        return False
    letters = sum(1 for char in visible if char.isalpha())
    garble = sum(1 for char in visible if char in TITLE_GARBLE_CHARS)
    return (
        letters / len(visible) >= TITLE_MIN_LETTER_SHARE
        and garble / len(visible) <= TITLE_MAX_GARBLE_SHARE
    )


def is_plausible_pdf_title_line(line: str) -> bool:
    normalized = clean_pdf_line(line)
    lower = normalized.lower()
    # A Chinese title has no spaces between words, so only its length counts.
    single_word = len(normalized.split()) < 2 and not CJK_CHAR_RE.search(normalized)
    if len(normalized) < 8 or (len(normalized) < 20 and single_word):
        return False
    if not is_mostly_letters(normalized):
        return False
    if normalized.count(",") >= 3:
        return False
    if any(token in lower for token in ["doi.org/", "http://", "https://", "www.", "check for updates"]):
        return False
    if lower in {"abstract", "article", "preprint"}:
        return False
    if lower.startswith("npj |") or lower.startswith("arxiv:") or lower.startswith("submitted to"):
        return False
    if any(re.search(pattern, lower) for pattern in LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS):
        return False
    if " doi:" in lower or lower.startswith("doi:"):
        return False
    return True


def join_title_lines(lines: list[str]) -> str:
    title = ""
    for line in lines:
        if not title:
            title = line
        elif title.endswith("-") and line[:1].islower():
            title = title[:-1] + line
        elif CJK_CHAR_RE.match(title[-1]) and CJK_CHAR_RE.match(line[0]):
            title += line
        else:
            title = f"{title} {line}"
    return TITLE_FOOTNOTE_MARKS_RE.sub("", title)


def first_page_title_from_layout(page: Any) -> str:
    """Return the first page's title: its largest plausible line plus the adjacent lines set
    in the same type, so a journal name or volume line printed above it is passed over."""
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return ""
    lines = []
    for block in blocks:
        for line in block.get("lines", []):
            if tuple(line.get("dir", (1.0, 0.0))) != (1.0, 0.0):
                continue
            spans = line.get("spans", [])
            text = clean_pdf_line("".join(str(span.get("text", "")) for span in spans))
            if text:
                sizes = [
                    float(span.get("size", 0))
                    for span in spans
                    if str(span.get("text", "")).strip()
                ]
                size = max(sizes)
                lines.append({"text": text, "size": size, "top": float(line["bbox"][1])})
    candidates = [line for line in lines if is_plausible_pdf_title_line(line["text"])]
    if not candidates:
        return ""
    anchor = max(candidates, key=lambda line: (line["size"], -line["top"]))
    ordered = sorted(lines, key=lambda line: line["top"])
    start = end = ordered.index(anchor)

    def continues_title(edge: dict, neighbour: dict) -> bool:
        return (
            neighbour["size"] >= anchor["size"] * TITLE_LINE_SIZE_RATIO
            and abs(neighbour["top"] - edge["top"]) <= anchor["size"] * TITLE_LINE_SPACING
            and is_mostly_letters(neighbour["text"])
        )

    while start > 0 and continues_title(ordered[start], ordered[start - 1]):
        start -= 1
    while end + 1 < len(ordered) and continues_title(ordered[end], ordered[end + 1]):
        end += 1
    return join_title_lines([line["text"] for line in ordered[start : end + 1]])


def first_page_title_candidate(first_page_text: str) -> str:
    for raw_line in (first_page_text or "").splitlines():
        if is_plausible_pdf_title_line(raw_line):
            return clean_pdf_line(raw_line)
    return ""


def extract_local_pdf_hints(pdf_path: Path) -> dict[str, Any]:
    raw_title = normalize_whitespace(pdf_path.stem.replace("_", " "))
    cleaned_title = clean_local_pdf_stem(pdf_path.stem)
    hints: dict[str, Any] = {
        "title": cleaned_title or raw_title,
        "local_pdf_title_source": "local_pdf_stem_used",
    }
    if is_probable_local_pdf_artifact_title(raw_title):
        hints["local_pdf_artifact_title"] = True
    if fitz is None:
        return hints

    metadata_title = ""
    metadata_subject = ""
    first_page_text = ""
    layout_title = ""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return hints
    try:
        metadata = doc.metadata or {}
        metadata_title = normalize_whitespace(str(metadata.get("title", "")))
        metadata_subject = normalize_whitespace(str(metadata.get("subject", "")))
        if len(doc):
            first_page_text = doc[0].get_text("text")
            layout_title = first_page_title_from_layout(doc[0])
    except Exception:
        return hints
    finally:
        doc.close()

    if metadata_title:
        hints["title"] = metadata_title
        hints["local_pdf_title_source"] = "pdf_metadata_title_used"
    else:
        page_title = layout_title or first_page_title_candidate(first_page_text)
        if page_title:
            hints["title"] = page_title
            hints["local_pdf_title_source"] = "first_page_title_used"

    searchable = "\n".join(part for part in [metadata_subject, metadata_title, first_page_text] if part)
    doi = extract_doi(searchable)
    if doi:
        hints["doi"] = doi
    arxiv_id = extract_arxiv_id(searchable)
    if arxiv_id:
        hints["arxiv_id"] = arxiv_id

    return hints


def choose_local_pdf_corrected_title(base: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    current_title = normalize_whitespace(str(base.get("title", "")))
    if not current_title:
        return ""
    titled_candidates = [candidate for candidate in candidates if normalize_whitespace(str(candidate.get("title", "")))]
    if local_pdf_title_needs_identity_correction(base):
        identity_matches = [
            candidate for candidate in titled_candidates if external_identity_matches(base, candidate)
        ]
        if identity_matches:
            best_identity = sorted(
                identity_matches,
                key=lambda item: (
                    candidate_priority_score(item),
                    publication_quality_score(item),
                    len(normalize_whitespace(str(item.get("title", "")))),
                ),
                reverse=True,
            )[0]
            return normalize_whitespace(str(best_identity.get("title", "")))

    if not is_probable_local_pdf_artifact_title(current_title):
        return ""
    best = choose_best_title_match(current_title, titled_candidates)
    if not best:
        return ""
    candidate_title = normalize_whitespace(str(best.get("title", "")))
    if not candidate_title:
        return ""
    if title_similarity(current_title, candidate_title) < 0.55:
        return ""
    if not (best.get("doi") or best.get("arxiv_id") or publication_quality_score(best) >= 2):
        return ""
    return candidate_title


LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS = (
    r"^(?:research|original|review)\s+article$",
    r"^provided proper attribution\b",
    r"^published as\b",
    r"^submitted to\b",
    r"^accepted (?:as|to|for)\b",
    r"^conference paper\b",
    r"^proceedings of\b",
    r"^arxiv\s*:",
    r"^doi\s*:",
)


def local_pdf_title_needs_identity_correction(base: dict[str, Any]) -> bool:
    title = normalize_whitespace(str(base.get("title", "")))
    if not title:
        return False
    if base.get("local_pdf_artifact_title") or is_probable_local_pdf_artifact_title(title):
        return True
    source = normalize_whitespace(str(base.get("local_pdf_title_source", "")))
    if source not in {"first_page_title_used", "local_pdf_stem_used", "pdf_metadata_title_used"}:
        return False
    lowered = title.lower()
    return any(re.search(pattern, lowered) for pattern in LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS)


def external_identity_matches(base: dict[str, Any], candidate: dict[str, Any]) -> bool:
    base_doi = extract_doi(str(base.get("doi", ""))) or ""
    candidate_doi = extract_doi(str(candidate.get("doi", ""))) or ""
    if base_doi and candidate_doi and base_doi.lower() == candidate_doi.lower():
        return True
    base_arxiv = normalize_whitespace(str(base.get("arxiv_id", "")))
    candidate_arxiv = normalize_whitespace(str(candidate.get("arxiv_id", "")))
    return bool(base_arxiv and candidate_arxiv and base_arxiv == candidate_arxiv)


def normalize_caption_label(label: str) -> str:
    label = normalize_whitespace(unicodedata.normalize("NFKC", label))
    chinese_match = re.match(r"^(图|表)\s*([A-Z]?\d+[a-z]?)$", label, re.IGNORECASE)
    if chinese_match:
        return f"{chinese_match.group(1)} {chinese_match.group(2)}"
    extended_figure_match = re.match(
        r"^extended\s+data\s+fig(?:ure)?\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if extended_figure_match:
        return f"Extended Data Fig {extended_figure_match.group(1)}"
    extended_table_match = re.match(
        r"^extended\s+data\s+table\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if extended_table_match:
        return f"Extended Data Table {extended_table_match.group(1)}"
    scheme_match = re.match(r"^(scheme|algorithm)\.?\s*(\d+[a-z]?)$", label, re.IGNORECASE)
    if scheme_match:
        return f"{scheme_match.group(1).capitalize()} {scheme_match.group(2)}"
    supplementary_match = re.match(
        r"^(supplementary)\s+(fig(?:ure)?|table)\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if supplementary_match:
        return f"{supplementary_match.group(1)} {supplementary_match.group(2)} {supplementary_match.group(3)}"
    english_match = re.match(
        r"^(fig(?:ure)?|table)\.?\s*([AS]?\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if english_match:
        return f"{english_match.group(1)} {english_match.group(2)}"
    return label


CAPTION_REFERENCE_VERBS = {
    "show",
    "shows",
    "illustrate",
    "illustrates",
    "plot",
    "plots",
    "present",
    "presents",
    "report",
    "reports",
    "depict",
    "depicts",
    "compare",
    "compares",
    "summarize",
    "summarizes",
    "demonstrate",
    "demonstrates",
}


def caption_label_key(label: str) -> str:
    normalized = normalize_caption_label(label).lower()
    normalized = re.sub(r"\bfigure\b", "fig", normalized)
    normalized = re.sub(r"\bfig\.\s*", "fig ", normalized)
    normalized = re.sub(r"\btable\.\s*", "table ", normalized)
    return normalize_whitespace(normalized)


def caption_preference_score(label: str, caption: str) -> int:
    cleaned_caption = normalize_whitespace(caption)
    lowered_label = normalize_whitespace(label).lower()
    first_word_match = re.match(r"^([A-Za-z][A-Za-z-]*)\b", cleaned_caption)
    first_word = first_word_match.group(1).lower() if first_word_match else ""
    score = len(cleaned_caption)
    if lowered_label.startswith(("figure", "table")):
        score += 25
    if first_word in CAPTION_REFERENCE_VERBS or cleaned_caption[:1].islower():
        score -= 80
    if len(cleaned_caption) < 12:
        score -= 20
    return score


def extract_caption_lines(pdf_text: str, kind: str) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    scores: dict[str, int] = {}
    order: list[str] = []
    lines = [clean_pdf_line(line) for line in pdf_text.splitlines()]
    if kind == "figure":
        pattern = re.compile(
            r"^((?:"
            r"supplementary\s+fig(?:ure)?\.?\s*\d+[a-z]?"
            r"|extended\s+data\s+fig(?:ure)?\.?\s*\d+[a-z]?"
            r"|scheme\.?\s*\d+[a-z]?"
            r"|algorithm\.?\s*\d+[a-z]?"
            r"|fig(?:ure)?\.?\s*[AS]?\d+[a-z]?"
            r"|图\.?\s*[A-Z]?\d+[a-z]?"
            r"))(?!\.\d)(?:[:：.。,\s、|—–-]+|$)(.*)$",
            re.IGNORECASE,
        )
    else:
        pattern = re.compile(
            r"^((?:"
            r"supplementary\s+table\.?\s*\d+[a-z]?"
            r"|extended\s+data\s+table\.?\s*\d+[a-z]?"
            r"|table\.?\s*[AS]?\d+[a-z]?"
            r"|表\.?\s*[A-Z]?\d+[a-z]?"
            r"))(?!\.\d)(?:[:：.。,\s、|—–-]+|$)(.*)$",
            re.IGNORECASE,
        )
    for idx, line in enumerate(lines):
        if not line:
            continue
        match = pattern.match(line)
        if not match:
            continue
        label = normalize_caption_label(match.group(1))
        caption = normalize_whitespace(match.group(2))
        if not caption and idx + 1 < len(lines):
            caption = normalize_whitespace(lines[idx + 1])
        key = caption_label_key(label)
        if not key:
            continue
        candidate = {"id": label, "caption": caption}
        score = caption_preference_score(label, caption)
        if key not in grouped:
            grouped[key] = candidate
            scores[key] = score
            order.append(key)
            continue
        if score > scores[key]:
            grouped[key] = candidate
            scores[key] = score
    return [grouped[key] for key in order]


