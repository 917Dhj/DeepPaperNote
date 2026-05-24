#!/usr/bin/env python3
"""Shared helpers for DeepPaperNote scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
DEFAULT_USER_AGENT = "DeepPaperNote/0.1"
SHELL_CONFIG_FILES = [
    Path.home() / ".zshenv",
    Path.home() / ".zprofile",
    Path.home() / ".zshrc",
    Path.home() / ".bash_profile",
    Path.home() / ".bashrc",
]

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", help="Primary input path, JSON artifact, or identifier.")
    parser.add_argument("--output", help="Output path for JSON or Markdown.")
    parser.add_argument("--paper-id", help="Canonical paper id if already known.")
    return parser


def ensure_parent(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def emit(payload: dict[str, Any], output_path: str | None = None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        ensure_parent(output_path)
        Path(output_path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def stub_payload(script: str, description: str, outputs: list[str]) -> dict[str, Any]:
    return {
        "status": "scaffold",
        "script": script,
        "description": description,
        "next_step": "Implement this contract incrementally.",
        "outputs": outputs,
    }


def load_json_file(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Expected a JSON object.")
    return data


def maybe_load_json_record(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    path = Path(stripped).expanduser()
    if path.exists() and path.is_file() and path.suffix.lower() == ".json":
        return load_json_file(path)
    if stripped.startswith("{"):
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    return None


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
            lines = path.read_text(encoding="utf-8").splitlines()
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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def http_get_json(url: str, *, timeout: int = 30, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return json.loads(http_get_text(url, timeout=timeout, headers=headers))


def http_get_bytes(url: str, *, timeout: int = 60, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


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
        papers = safe_fetch_arxiv_entries(id_list=arxiv_id, max_results=1)
        if papers:
            paper = papers[0]
            paper["paper_id"] = paper_id_for_record(paper)
            paper["status"] = "ok"
            return apply_identity_confidence(paper)
        if arxiv_id:
            return fallback_arxiv_record(arxiv_id, "arxiv_id")
    if source_type == "arxiv_url":
        arxiv_id = extract_arxiv_id(stripped) or ""
        papers = safe_fetch_arxiv_entries(id_list=arxiv_id, max_results=1)
        if papers:
            paper = papers[0]
            paper["paper_id"] = paper_id_for_record(paper)
            paper["status"] = "ok"
            return apply_identity_confidence(paper)
        if arxiv_id:
            return fallback_arxiv_record(arxiv_id, "arxiv_url", source_url=stripped)
    if source_type in {"doi", "doi_url"}:
        doi = extract_doi(stripped) or ""
        paper = fetch_crossref_by_doi(doi) or {"doi": doi, "source_url": f"https://doi.org/{doi}"}
        paper["source_type"] = "doi"
        paper["source_url"] = paper.get("source_url") or f"https://doi.org/{doi}"
        paper["status"] = "ok"
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
    candidates = (
        search_semantic_scholar(title, limit=5)
        + search_crossref_by_title(title, limit=5)
        + search_openalex_by_title(title, limit=5)
        + safe_fetch_arxiv_entries(search_query=f'ti:"{title}"', max_results=5)
    )
    best = choose_best_title_match(title, candidates)
    if best:
        best = merge_metadata_records({"title": title, "source_type": "title_query", "source_url": "", "metadata_sources": ["title_query"]}, best)
        best["status"] = "ok"
        return apply_identity_confidence(best)
    paper = {
        "status": "ok",
        "source_type": "title_query",
        "title": title,
        "source_url": "",
        "metadata_sources": ["title_query"],
    }
    paper["paper_id"] = paper_id_for_record(paper)
    return apply_identity_confidence(paper)


def enrich_metadata(record: dict[str, Any]) -> dict[str, Any]:
    base = dict(record)
    candidates: list[dict[str, Any]] = [base]
    doi = normalize_whitespace(str(base.get("doi", "")))
    title = normalize_whitespace(str(base.get("title", "")))
    arxiv_id = normalize_whitespace(str(base.get("arxiv_id", "")))

    if doi:
        crossref = fetch_crossref_by_doi(doi)
        if crossref:
            candidates.append(crossref)
        openalex = fetch_openalex_by_doi(doi)
        if openalex:
            candidates.append(openalex)
        sem = choose_best_title_match(title or doi, search_semantic_scholar(doi, limit=3))
        if sem:
            candidates.append(sem)

    if arxiv_id:
        arxiv = safe_fetch_arxiv_entries(id_list=arxiv_id, max_results=1)
        if arxiv:
            candidates.append(arxiv[0])

    if title:
        sem = choose_best_title_match(title, search_semantic_scholar(title, limit=5))
        if sem:
            candidates.append(sem)
        oa = choose_best_title_match(title, search_openalex_by_title(title, limit=5))
        if oa:
            candidates.append(oa)
        cross = choose_best_title_match(title, search_crossref_by_title(title, limit=5))
        if cross:
            candidates.append(cross)
        arxiv = choose_best_title_match(title, safe_fetch_arxiv_entries(search_query=f'ti:"{title}"', max_results=5))
        if arxiv:
            candidates.append(arxiv)

    merged = merge_metadata_records(*candidates)
    if not merged.get("year") and merged.get("published") and re.match(r"^\d{4}", str(merged["published"])):
        merged["year"] = str(merged["published"])[:4]
    if merged.get("doi") and not merged.get("source_url"):
        merged["source_url"] = f"https://doi.org/{merged['doi']}"
    if merged.get("arxiv_id") and not merged.get("pdf_url"):
        merged["pdf_url"] = f"https://arxiv.org/pdf/{merged['arxiv_id']}.pdf"
    if merged.get("arxiv_id") and not merged.get("doi"):
        merged["doi"] = f"10.48550/arXiv.{merged['arxiv_id']}"
    if base.get("source_type") == "local_pdf":
        if base.get("local_pdf_title_source"):
            merged["local_pdf_title_source"] = base["local_pdf_title_source"]
        elif is_probable_local_pdf_artifact_title(str(base.get("title", ""))):
            merged["local_pdf_title_source"] = "local_pdf_stem_used"
        if base.get("local_pdf_artifact_title") or is_probable_local_pdf_artifact_title(str(base.get("title", ""))):
            merged["local_pdf_artifact_title"] = True
        corrected_title = choose_local_pdf_corrected_title(base, candidates[1:])
        if corrected_title:
            merged["title"] = corrected_title
            merged["title_corrected_from_external_metadata"] = True
    merged["paper_id"] = paper_id_for_record(merged)
    return apply_identity_confidence(merged)


def runtime_config() -> dict[str, Any]:
    return {
        "obsidian_vault": env_config_value("DEEPPAPERNOTE_OBSIDIAN_VAULT"),
        "papers_dir": env_config_value("DEEPPAPERNOTE_PAPERS_DIR", default="Research/Papers"),
        "output_dir": env_config_value("DEEPPAPERNOTE_OUTPUT_DIR", default="tmp/DeepPaperNote"),
        "workspace_output_dir": env_config_value(
            "DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR",
            default="DeepPaperNote_output",
        ),
    }


def configured_obsidian_vault(config: dict[str, Any]) -> Path | None:
    vault = str(config.get("obsidian_vault", "")).strip()
    if not vault:
        return None
    vault_path = Path(vault).expanduser().resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RuntimeError(f"Configured Obsidian vault does not exist: {vault_path}")
    return vault_path


def require_obsidian_vault(config: dict[str, Any]) -> Path:
    vault_path = configured_obsidian_vault(config)
    if vault_path is None:
        raise RuntimeError("Missing Obsidian vault configuration. Set DEEPPAPERNOTE_OBSIDIAN_VAULT.")
    return vault_path


def resolve_note_output_mode(config: dict[str, Any]) -> tuple[str, Path]:
    vault_path = configured_obsidian_vault(config)
    if vault_path is not None:
        return ("obsidian", vault_path)
    workspace_root = Path.cwd().resolve()
    output_dir = str(config.get("workspace_output_dir", "DeepPaperNote_output")).strip() or "DeepPaperNote_output"
    return ("workspace", workspace_root / output_dir)


DOMAIN_RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "domain_rules.yaml"
DOMAIN_LIST_KEYS = (
    "aliases",
    "keywords",
    "methods",
    "application_keywords",
    "method_keywords",
    "specialized_folders",
)
DOMAIN_SECTIONS = ("domains", "fallback_domains")
DOMAIN_SECTION_ALIASES = {"application_domains": "domains"}
DEFAULT_DOMAIN_RULES: dict[str, list[dict[str, Any]]] = {
    "domains": [
        {
            "label": "医疗健康",
            "aliases": ["healthcare", "medical", "clinical medicine"],
            "specialized_folders": ["心理健康"],
            "keywords": [
                "clinical",
                "patient",
                "patients",
                "depression",
                "anxiety",
                "mental health",
                "psychiatric",
                "psychology",
                "therapy",
                "counseling",
                "symptom",
                "diagnosis",
                "screening",
                "hospital",
                "healthcare",
                "medical",
            ],
            "methods": [],
        },
        {
            "label": "法律",
            "aliases": ["legal", "law"],
            "keywords": [
                "legal",
                "law",
                "court",
                "judge",
                "contract",
                "statute",
                "regulation",
                "litigation",
                "case law",
            ],
            "methods": [],
        },
        {
            "label": "教育",
            "aliases": ["education", "educational"],
            "keywords": [
                "education",
                "student",
                "teacher",
                "classroom",
                "curriculum",
                "tutoring",
                "learning analytics",
                "pedagogy",
            ],
            "methods": [],
        },
        {
            "label": "金融",
            "aliases": ["finance", "financial"],
            "keywords": [
                "finance",
                "financial",
                "stock",
                "market",
                "trading",
                "portfolio",
                "risk",
                "credit",
                "banking",
                "investment",
            ],
            "methods": [],
        },
        {
            "label": "机器人",
            "aliases": ["robotics", "robotic"],
            "keywords": [
                "robot",
                "robotics",
                "robotic",
                "manipulation",
                "navigation",
                "control policy",
                "locomotion",
                "autonomous driving",
                "embodied",
            ],
            "methods": ["diffusion policy"],
        },
        {
            "label": "软件工程",
            "aliases": ["software engineering"],
            "keywords": [
                "software engineering",
                "code generation",
                "program repair",
                "bug",
                "repository",
                "developer",
                "code review",
                "test generation",
                "compiler",
            ],
            "methods": [],
        },
        {
            "label": "生物医学",
            "aliases": ["biomedical", "bioinformatics"],
            "keywords": [
                "biomedical",
                "genomics",
                "protein",
                "drug discovery",
                "molecular",
                "cell",
                "gene",
                "bioinformatics",
            ],
            "methods": [],
        },
        {
            "label": "心理健康",
            "route_to": "医疗健康",
            "aliases": ["mental health", "psychology", "psychiatry"],
            "keywords": [
                "depression",
                "anxiety",
                "mental health",
                "psychiatric",
                "psychology",
                "therapy",
                "counseling",
                "symptom",
            ],
            "methods": [],
        },
        {
            "label": "推荐系统",
            "aliases": ["recommender systems", "recommendation"],
            "keywords": [
                "recommendation",
                "recommender",
                "ctr prediction",
                "ranking system",
                "personalization",
            ],
            "methods": [],
        },
    ],
    "fallback_domains": [
        {
            "label": "大模型",
            "aliases": ["llm", "large language model", "language model", "foundation model"],
            "keywords": [
                "large language model",
                "llm",
                "foundation model",
                "gpt",
                "transformer",
                "instruction tuning",
                "pretrain",
                "pre-training",
                "language model",
                "agent",
                "multi-agent",
                "multi agent",
                "reasoning",
                "multimodal",
                "retrieval-augmented generation",
                "rag",
                "in-context learning",
                "long-context",
                "long context",
                "mixture-of-experts",
                "mixture of experts",
                "moe",
                "alignment",
                "rlhf",
            ],
            "methods": [],
        },
        {
            "label": "机器学习",
            "aliases": ["machine learning", "ml"],
            "keywords": [
                "machine learning",
                "deep learning",
                "neural network",
                "representation learning",
                "reinforcement learning",
                "computer vision",
                "graph neural network",
                "speech recognition",
            ],
            "methods": [],
        },
    ],
}


def _copy_default_domain_rules() -> dict[str, list[dict[str, Any]]]:
    return {
        section: [
            {key: list(value) if isinstance(value, list) else value for key, value in rule.items()}
            for rule in DEFAULT_DOMAIN_RULES[section]
        ]
        for section in DOMAIN_SECTIONS
    }


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_inline_yaml_list(value: str) -> list[str]:
    items: list[str] = []
    current = []
    in_single = False
    in_double = False
    for char in value:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "," and not in_single and not in_double:
            item = _parse_yaml_scalar("".join(current))
            if item:
                items.append(item)
            current = []
            continue
        current.append(char)
    item = _parse_yaml_scalar("".join(current))
    if item:
        items.append(item)
    return items


def _parse_yaml_value(value: str) -> str | list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return _split_inline_yaml_list(value[1:-1])
    return _parse_yaml_scalar(value)


def _parse_domain_rules_yaml(text: str) -> dict[str, list[dict[str, Any]]]:
    rules: dict[str, list[dict[str, Any]]] = {section: [] for section in DOMAIN_SECTIONS}
    section = ""
    current: dict[str, Any] | None = None
    current_list_key = ""

    for raw_line in text.splitlines():
        line = _strip_yaml_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            current = None
            current_list_key = ""
            key, _, value = stripped.partition(":")
            key = DOMAIN_SECTION_ALIASES.get(key.strip(), key.strip())
            if key in DOMAIN_SECTIONS:
                section = key
                if value.strip() == "[]":
                    rules[section] = []
            else:
                section = ""
            continue

        if section not in rules:
            continue

        if indent <= 2 and stripped.startswith("- "):
            current = {}
            rules[section].append(current)
            current_list_key = ""
            item = stripped[2:].strip()
            if item:
                key, separator, value = item.partition(":")
                if not separator:
                    raise ValueError("Domain list entries must be mappings.")
                current[key.strip()] = _parse_yaml_value(value)
            continue

        if current is None:
            raise ValueError("Domain properties must belong to a list entry.")

        if stripped.startswith("- "):
            if not current_list_key:
                raise ValueError("List item without a list key.")
            item = _parse_yaml_scalar(stripped[2:].strip())
            if item:
                current.setdefault(current_list_key, []).append(item)
            continue

        key, separator, value = stripped.partition(":")
        if not separator:
            raise ValueError("Expected key/value domain property.")
        key = key.strip()
        value = value.strip()
        if key in DOMAIN_LIST_KEYS:
            parsed = _parse_yaml_value(value) if value else []
            current[key] = parsed if isinstance(parsed, list) else [parsed]
            current_list_key = key if not value else ""
        else:
            current[key] = _parse_yaml_scalar(value)
            current_list_key = ""

    return rules


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_domain_rule(raw: dict[str, Any]) -> dict[str, Any] | None:
    label = str(raw.get("label", "")).strip()
    if not label:
        return None
    rule: dict[str, Any] = {"label": label}
    route_to = str(raw.get("route_to", "")).strip()
    if route_to:
        rule["route_to"] = route_to
    rule["aliases"] = _as_string_list(raw.get("aliases"))
    rule["specialized_folders"] = _as_string_list(raw.get("specialized_folders"))
    rule["keywords"] = _as_string_list(raw.get("keywords")) + _as_string_list(
        raw.get("application_keywords")
    )
    rule["methods"] = _as_string_list(raw.get("methods")) + _as_string_list(
        raw.get("method_keywords")
    )
    return rule


def _normalize_domain_rules(
    raw: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]] | None:
    normalized: dict[str, list[dict[str, Any]]] = {section: [] for section in DOMAIN_SECTIONS}
    for section in DOMAIN_SECTIONS:
        items = raw.get(section)
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                return None
            rule = _normalize_domain_rule(item)
            if rule is None:
                return None
            normalized[section].append(rule)
    if not normalized["domains"] and not normalized["fallback_domains"]:
        return None
    return normalized


def load_domain_rules() -> dict[str, list[dict[str, Any]]]:
    try:
        if not DOMAIN_RULES_PATH.exists():
            return _copy_default_domain_rules()
        parsed = _parse_domain_rules_yaml(DOMAIN_RULES_PATH.read_text(encoding="utf-8"))
        normalized = _normalize_domain_rules(parsed)
        if normalized is None:
            return _copy_default_domain_rules()
        return normalized
    except Exception:
        return _copy_default_domain_rules()


def _normalized_domain_label(value: str) -> str:
    return normalize_whitespace(value).lower()


def _term_in_text(term: str, text: str) -> bool:
    normalized = _normalized_domain_label(term)
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._+/#-]*", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None
    return normalized in text


def _count_term_hits(terms: list[str], text: str) -> int:
    return sum(1 for term in terms if _term_in_text(term, text))


def _domain_route_label(rule: dict[str, Any]) -> str:
    return str(rule.get("route_to") or rule.get("label") or "").strip()


def _domain_match_terms(rule: dict[str, Any]) -> list[str]:
    terms = [str(rule.get("label", "")).strip(), _domain_route_label(rule)]
    terms.extend(_as_string_list(rule.get("aliases")))
    terms.extend(_as_string_list(rule.get("specialized_folders")))
    return [term for term in terms if term]


def _domain_name_matches_rule(domain_name: str, rule: dict[str, Any]) -> bool:
    name = _normalized_domain_label(domain_name)
    return any(_normalized_domain_label(term) == name for term in _domain_match_terms(rule))


def _rules_for_label(
    rules: dict[str, list[dict[str, Any]]],
    label: str,
) -> list[tuple[str, dict[str, Any]]]:
    normalized_label = _normalized_domain_label(label)
    matches: list[tuple[str, dict[str, Any]]] = []
    for section in DOMAIN_SECTIONS:
        for rule in rules[section]:
            route_label = _normalized_domain_label(_domain_route_label(rule))
            terms = [_normalized_domain_label(term) for term in _domain_match_terms(rule)]
            if normalized_label == route_label or normalized_label in terms:
                matches.append((section, rule))
    return matches


def _score_domain_for_inference(rule: dict[str, Any], text: str, *, fallback: bool) -> int:
    label_hits = _count_term_hits([str(rule.get("label", "")), _domain_route_label(rule)], text)
    alias_hits = _count_term_hits(_as_string_list(rule.get("aliases")), text)
    specialized_hits = _count_term_hits(_as_string_list(rule.get("specialized_folders")), text)
    keyword_hits = _count_term_hits(_as_string_list(rule.get("keywords")), text)
    method_hits = _count_term_hits(_as_string_list(rule.get("methods")), text)
    if fallback:
        return (label_hits * 80) + (alias_hits * 60) + (keyword_hits * 12) + (method_hits * 4)
    return (
        (label_hits * 100)
        + (alias_hits * 80)
        + (specialized_hits * 80)
        + (keyword_hits * 20)
        + (method_hits * 3)
    )


def infer_domain_label(title: str, abstract: str = "") -> str:
    lower = normalize_whitespace(f"{title} {abstract}").lower()
    rules = load_domain_rules()
    scored: list[tuple[int, str]] = []
    for rule in rules["domains"]:
        score = _score_domain_for_inference(rule, lower, fallback=False)
        if score > 0:
            scored.append((score, _domain_route_label(rule)))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]

    for rule in rules["fallback_domains"]:
        score = _score_domain_for_inference(rule, lower, fallback=True)
        if score > 0:
            scored.append((score, _domain_route_label(rule)))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]

    paper_type, _ = infer_paper_type(title, abstract)
    if paper_type == "clinical_or_psychology_empirical":
        return "医疗健康"
    if paper_type == "AI_method":
        return "机器学习"
    return "未分类"


def is_probable_paper_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    marker = path / f"{path.name}.md"
    return marker.exists()


def existing_domain_dirs(config: dict[str, Any]) -> list[str]:
    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    base_dir = root_path / Path(papers_dir) if output_mode == "obsidian" else root_path
    if not base_dir.exists() or not base_dir.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if is_probable_paper_folder(child):
            continue
        names.append(child.name)
    return names


def domain_name_score(domain_name: str, label: str, title: str, abstract: str) -> int:
    name = domain_name.strip().lower()
    score = 0
    if name == label.lower():
        score += 100
    lower = normalize_whitespace(f"{title} {abstract}").lower()
    rules = load_domain_rules()
    label_rules = _rules_for_label(rules, label)
    label_is_application = any(section == "domains" for section, _ in label_rules)
    known_fallback_name = any(
        _domain_name_matches_rule(domain_name, rule) for rule in rules["fallback_domains"]
    )

    for section, rule in label_rules:
        if not _domain_name_matches_rule(domain_name, rule):
            continue
        score += 90 if section == "domains" else 70
        score += _count_term_hits(_as_string_list(rule.get("aliases")), lower) * 20
        score += _count_term_hits(_as_string_list(rule.get("specialized_folders")), lower) * 20
        score += _count_term_hits(_as_string_list(rule.get("keywords")), lower) * 10
        score += _count_term_hits(_as_string_list(rule.get("methods")), lower) * 2

    if not (label_is_application and known_fallback_name) and _term_in_text(domain_name, lower):
        score += 15
    return score


def resolve_domain_subdir(
    config: dict[str, Any],
    *,
    title: str,
    abstract: str = "",
    subdir: str = "",
) -> str:
    if subdir.strip():
        return subdir.strip()
    label = infer_domain_label(title, abstract)
    existing = existing_domain_dirs(config)
    if existing:
        best_name = ""
        best_score = -1
        for domain_name in existing:
            score = domain_name_score(domain_name, label, title, abstract)
            if score > best_score:
                best_name = domain_name
                best_score = score
        if best_name and best_score > 0:
            return best_name
    return label


def resolve_obsidian_note_path(
    config: dict[str, Any],
    *,
    title: str,
    subdir: str = "",
    filename: str = "",
) -> Path:
    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    relative_dir = Path(papers_dir) if output_mode == "obsidian" else Path()
    if subdir:
        subdir_path = Path(subdir)
        if output_mode == "obsidian" and str(subdir_path).startswith(papers_dir):
            relative_dir = subdir_path
        else:
            relative_dir = relative_dir / subdir_path
    note_slug = slugify_filename(title)
    target_name = filename or f"{note_slug}.md"
    folder_name = Path(target_name).stem or note_slug
    folder_aliases = {folder_name, note_slug, slugify_filename(folder_name)}
    normalized_folder_aliases = {alias.lower() for alias in folder_aliases if alias}
    if relative_dir.name.lower() in normalized_folder_aliases:
        return root_path / relative_dir / target_name
    return root_path / relative_dir / folder_name / target_name


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


def is_plausible_pdf_title_line(line: str) -> bool:
    normalized = clean_pdf_line(line)
    lower = normalized.lower()
    if len(normalized) < 20 or len(normalized.split()) < 4:
        return False
    if normalized.count(",") >= 3:
        return False
    if any(token in lower for token in ["doi.org/", "http://", "https://", "www.", "check for updates"]):
        return False
    if lower in {"abstract", "article", "preprint"}:
        return False
    if lower.startswith("npj |") or lower.startswith("arxiv:") or lower.startswith("submitted to"):
        return False
    if " doi:" in lower or lower.startswith("doi:"):
        return False
    return True


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
    except Exception:
        return hints
    finally:
        doc.close()

    if metadata_title:
        hints["title"] = metadata_title
        hints["local_pdf_title_source"] = "pdf_metadata_title_used"
    else:
        page_title = first_page_title_candidate(first_page_text)
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
    if not current_title or not is_probable_local_pdf_artifact_title(current_title):
        return ""
    titled_candidates = [candidate for candidate in candidates if normalize_whitespace(str(candidate.get("title", "")))]
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


def normalize_caption_label(label: str) -> str:
    label = normalize_whitespace(label)
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
    if first_word in CAPTION_REFERENCE_VERBS:
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


def infer_paper_type(title: str, abstract: str) -> tuple[str, str]:
    lower = f"{title} {abstract}".lower()
    survey_terms = [
        "survey",
        "tutorial",
        "overview",
        "systematic review",
        "literature review",
        "scoping review",
        "meta-analysis",
        "meta analysis",
    ]
    if any(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower) for token in survey_terms):
        return "survey_or_review", "The paper is an explicit survey, review, tutorial, overview, or meta-analysis."
    if any(token in lower for token in ["depression", "anxiety", "mental health", "clinical", "patient", "psychiatric", "psychological", "hospital"]):
        return "clinical_or_psychology_empirical", "The paper is closer to an empirical clinical or psychology study."
    if any(token in lower for token in ["humanities", "social science", "theoretical framing", "ethnographic", "interpretive", "conceptual", "argument structure"]):
        return "humanities_or_social_science", "The paper emphasizes theoretical framing, interpretation, or social-science argument structure."
    if any(token in lower for token in ["benchmark", "leaderboard", "evaluation suite", "dataset", "corpus"]):
        return "benchmark_or_dataset", "The paper emphasizes benchmark, dataset, or evaluation design."
    return "AI_method", "The paper is best treated as a method-focused technical paper."


def extract_dataset_candidates(text: str) -> list[str]:
    found: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        if not any(token in sentence.lower() for token in ["dataset", "benchmark", "corpus", "participants", "patients"]):
            continue
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9+\-]{2,}(?:[ -][A-Z][A-Za-z0-9+\-]{2,})?\b", sentence)
        for candidate in candidates:
            norm = candidate.lower()
            if norm in seen:
                continue
            seen.add(norm)
            found.append(candidate)
            if len(found) >= 8:
                return found
    return found


def extract_metric_claims(text: str) -> list[str]:
    claims: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if not re.search(r"\d", sentence):
            continue
        if not any(token in lower for token in ["accuracy", "f1", "auc", "auprc", "mae", "rmse", "score", "%", "outperform", "improv", "bac"]):
            continue
        normalized = normalize_whitespace(sentence)
        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= 8:
            break
    return claims


def extract_negative_claims(text: str, *, limit: int = 6) -> list[str]:
    claims: list[str] = []
    seen = set()
    explicit_negative_tokens = [
        "worse",
        "degrade",
        "degraded",
        "drop",
        "dropped",
        "decrease",
        "decreased",
        "unstable",
        "instability",
        "fail",
        "failed",
        "fails",
        "collapse",
        "collapsed",
        "underperform",
        "underperformed",
        "sensitive",
        "sensitivity",
        "trade-off",
        "tradeoff",
        "hurt performance",
        "hurts performance",
    ]
    ablation_tokens = [
        "without",
        "w/o",
        "remove",
        "removed",
        "removing",
        "omit",
        "omits",
        "omitted",
        "omitting",
        "ablation",
    ]
    performance_tokens = [
        "accuracy",
        "f1",
        "auc",
        "auprc",
        "mae",
        "rmse",
        "score",
        "performance",
        "%",
        "result",
        "results",
        "training",
        "converge",
        "convergence",
        "stable",
        "stability",
        "baseline",
    ]
    positive_only_tokens = [
        "outperform",
        "improv",
        "better than",
        "achieve",
        "state-of-the-art",
        "sota",
    ]

    for sentence in split_sentences(text):
        normalized = normalize_whitespace(sentence)
        if not normalized:
            continue
        lower = normalized.lower()
        has_explicit_negative = any(token in lower for token in explicit_negative_tokens)
        has_ablation_marker = any(token in lower for token in ablation_tokens)
        has_performance_context = any(token in lower for token in performance_tokens) or bool(re.search(r"\d", normalized))
        has_positive_only = any(token in lower for token in positive_only_tokens)

        if not has_explicit_negative:
            if not (has_ablation_marker and has_performance_context):
                continue
            if has_positive_only and not any(token in lower for token in ["trade-off", "tradeoff", "sensitive", "stability"]):
                continue

        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= limit:
            break
    return claims


def extract_mechanism_flow_sentences(text: str, *, limit: int = 8) -> list[str]:
    claims: list[str] = []
    seen = set()
    action_tokens = [
        "encode",
        "encoded",
        "encoding",
        "extract",
        "extracted",
        "project",
        "projected",
        "pool",
        "pooled",
        "fuse",
        "fused",
        "fusion",
        "concat",
        "concatenate",
        "query",
        "queried",
        "align",
        "aligned",
        "compress",
        "compressed",
        "send",
        "sent",
        "feed",
        "fed",
        "generate",
        "generated",
        "predict",
        "predicted",
        "decode",
        "decoded",
        "update",
        "updated",
        "freeze",
        "frozen",
        "fine-tune",
        "finetune",
    ]
    flow_tokens = [
        "input",
        "inputs",
        "output",
        "outputs",
        "token",
        "tokens",
        "feature",
        "features",
        "representation",
        "representations",
        "encoder",
        "decoder",
        "attention",
        "module",
        "modules",
        "llm",
        "language model",
        "query token",
        "cross-attention",
        "projection",
        "state",
        "states",
    ]

    for sentence in split_sentences(text):
        normalized = normalize_whitespace(sentence)
        if not normalized:
            continue
        lower = normalized.lower()
        if not any(token in lower for token in action_tokens):
            continue
        if not any(token in lower for token in flow_tokens):
            continue
        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= limit:
            break
    return claims


def pick_sentences_by_keywords(text: str, keywords: list[str], *, limit: int = 5) -> list[str]:
    picked: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if not any(keyword in lower for keyword in keywords):
            continue
        normalized = normalize_title(sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        picked.append(normalize_whitespace(sentence))
        if len(picked) >= limit:
            break
    return picked
