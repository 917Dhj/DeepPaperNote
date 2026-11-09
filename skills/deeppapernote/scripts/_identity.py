"""Paper identity: identifiers, title matching, manifestation equivalence, and the canonical identity contract."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any

from common import normalize_title, normalize_whitespace, require_ok_input_artifact

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

LOCAL_PDF_PREFIX_PATTERN = re.compile(r"^(?:[^-]{1,120})\s+-\s+(?:19|20)\d{2}\s+-\s+")
LOCAL_PDF_SUFFIX_ID_PATTERN = re.compile(r"\s*-\s*\d{4,}\s*$")
PREPRINT_HINTS = ("medrxiv", "biorxiv", "preprint", "arxiv", "10.1101/", "10.21203/rs.", "preprints.org")


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


TITLE_LEAD_IN_MAX_WORDS = 3


def _printed_title_with_lead_in(record: dict[str, Any], observation: dict[str, Any]) -> str:
    """Return the PDF's printed title when it is a preprint's title after a short lead-in.

    A venue can require a lead-in such as "Position:" that the preprint record never
    gains, so the printed title is then the published one. A published record's title
    still wins, and a longer lead-in is more likely a header line joined to the title.
    """
    if publication_quality_score(observation) != 0:
        return ""
    printed = _string_field(record, "local_pdf_first_page_title")
    if not printed and _string_field(record, "local_pdf_title_source") == "first_page_title_used":
        printed = _string_field(record, "title")
    lead_in, colon, rest = printed.partition(":")
    observed = normalize_identity_title(_string_field(observation, "title"))
    if (
        colon
        and observed
        and normalize_identity_title(rest) == observed
        and 1 <= len(lead_in.split()) <= TITLE_LEAD_IN_MAX_WORDS
    ):
        return printed
    return ""


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
                merged["title"] = _printed_title_with_lead_in(merged, observation) or deepcopy(
                    value
                )
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
