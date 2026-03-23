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
    joined = " ".join([venue, source_url, source])
    if any(token in joined for token in ["medrxiv", "biorxiv", "preprint", "arxiv"]):
        return 0
    if venue or source == "crossref":
        return 2
    return 1


def candidate_priority_score(record: dict[str, Any]) -> int:
    source = normalize_whitespace(str(record.get("source", ""))).lower()
    source_url = normalize_whitespace(str(record.get("source_url", ""))).lower()
    doi = normalize_whitespace(str(record.get("doi", ""))).lower()
    joined = " ".join([source, source_url, doi])

    if "preprints.org" in joined or "10.20944/preprints" in joined:
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
        r"abs/(\d{4}\.\d{4,5})(?:v\d+)?",
        r"pdf/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?",
        r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b",
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
        if extract_arxiv_id(stripped):
            return "arxiv_url"
        if extract_doi(stripped):
            return "doi_url"
        if stripped.lower().endswith(".pdf"):
            return "pdf_url"
        return "url"
    if extract_arxiv_id(stripped):
        return "arxiv_id"
    if extract_doi(stripped):
        return "doi"
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
    xml_content = http_get_text(f"https://export.arxiv.org/api/query?{params}")
    return parse_arxiv_xml(xml_content)


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
    if not pdf_url:
        best_oa = item.get("best_oa_location", {}) or {}
        pdf_url = normalize_whitespace(str(best_oa.get("pdf_url") or best_oa.get("landing_page_url") or ""))
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
        "source_url": normalize_whitespace(str(item.get("id", ""))),
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
    additive_list_fields = {"affiliations", "metadata_sources"}
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
        return {
            "status": "ok",
            "source_type": "local_pdf",
            "source_url": str(path),
            "local_pdf_path": str(path),
            "title": path.stem.replace("_", " "),
            "metadata_sources": ["local_pdf"],
            "paper_id": paper_id_for_record({"title": path.stem}),
        }
    if source_type == "arxiv_id":
        papers = fetch_arxiv_entries(id_list=extract_arxiv_id(stripped) or "", max_results=1)
        if papers:
            paper = papers[0]
            paper["paper_id"] = paper_id_for_record(paper)
            paper["status"] = "ok"
            return paper
    if source_type == "arxiv_url":
        papers = fetch_arxiv_entries(id_list=extract_arxiv_id(stripped) or "", max_results=1)
        if papers:
            paper = papers[0]
            paper["paper_id"] = paper_id_for_record(paper)
            paper["status"] = "ok"
            return paper
    if source_type in {"doi", "doi_url"}:
        doi = extract_doi(stripped) or ""
        paper = fetch_crossref_by_doi(doi) or {"doi": doi, "source_url": f"https://doi.org/{doi}"}
        paper["source_type"] = "doi"
        paper["source_url"] = paper.get("source_url") or f"https://doi.org/{doi}"
        paper["status"] = "ok"
        paper["paper_id"] = paper_id_for_record(paper)
        return paper
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
        return paper
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
        return paper
    if source_type == "zotero_key":
        paper = {
            "status": "ok",
            "source_type": "zotero_key",
            "zotero_key": stripped,
            "source_url": "",
            "metadata_sources": ["zotero_key"],
        }
        paper["paper_id"] = paper_id_for_record(paper)
        return paper

    title = stripped
    candidates = (
        search_semantic_scholar(title, limit=5)
        + search_crossref_by_title(title, limit=5)
        + search_openalex_by_title(title, limit=5)
        + fetch_arxiv_entries(search_query=f'ti:"{title}"', max_results=5)
    )
    best = choose_best_title_match(title, candidates)
    if best:
        best = merge_metadata_records({"title": title, "source_type": "title_query", "source_url": "", "metadata_sources": ["title_query"]}, best)
        best["status"] = "ok"
        return best
    paper = {
        "status": "ok",
        "source_type": "title_query",
        "title": title,
        "source_url": "",
        "metadata_sources": ["title_query"],
    }
    paper["paper_id"] = paper_id_for_record(paper)
    return paper


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
        arxiv = fetch_arxiv_entries(id_list=arxiv_id, max_results=1)
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
        arxiv = choose_best_title_match(title, fetch_arxiv_entries(search_query=f'ti:"{title}"', max_results=5))
        if arxiv:
            candidates.append(arxiv)

    merged = merge_metadata_records(*candidates)
    if not merged.get("year") and merged.get("published") and re.match(r"^\d{4}", str(merged["published"])):
        merged["year"] = str(merged["published"])[:4]
    if merged.get("doi") and not merged.get("source_url"):
        merged["source_url"] = f"https://doi.org/{merged['doi']}"
    if merged.get("arxiv_id") and not merged.get("pdf_url"):
        merged["pdf_url"] = f"https://arxiv.org/pdf/{merged['arxiv_id']}.pdf"
    merged["paper_id"] = paper_id_for_record(merged)
    return merged


def runtime_config() -> dict[str, Any]:
    return {
        "obsidian_vault": env_config_value(
            "DEEPPAPERNOTE_OBSIDIAN_VAULT",
            "READ_ARXIV_OBSIDIAN_VAULT",
        ),
        "papers_dir": env_config_value("DEEPPAPERNOTE_PAPERS_DIR", default="20_Research/Papers"),
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


DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("心理健康", ("mental health", "depression", "anxiety", "psychiatric", "psychology", "clinical", "patient", "counsel", "therapy")),
    ("大模型", ("large language model", "llm", "foundation model", "gpt", "transformer", "instruction tuning", "pretrain", "pre-training", "language model", "agent", "reasoning")),
    ("多模态", ("multimodal", "vision-language", "audio-visual", "video-language", "image-text", "cross-modal")),
    ("计算机视觉", ("computer vision", "image classification", "object detection", "segmentation", "vision transformer", "visual recognition")),
    ("强化学习", ("reinforcement learning", "policy optimization", "bandit", "markov decision process", "rl")),
    ("语音", ("speech", "asr", "automatic speech recognition", "text-to-speech", "speaker recognition", "audio")),
    ("推荐系统", ("recommendation", "recommender", "ctr prediction", "ranking system")),
    ("机器人", ("robot", "robotics", "manipulation", "navigation", "control policy")),
    ("图学习", ("graph neural network", "graph learning", "molecular graph", "gnn")),
    ("机器学习", ("machine learning", "deep learning", "neural network", "representation learning")),
]


def infer_domain_label(title: str, abstract: str = "") -> str:
    lower = normalize_whitespace(f"{title} {abstract}").lower()
    scored: list[tuple[int, str]] = []
    for label, keywords in DOMAIN_RULES:
        score = sum(1 for keyword in keywords if keyword in lower)
        if score > 0:
            scored.append((score, label))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]
    paper_type, _ = infer_paper_type(title, abstract)
    if paper_type == "clinical_or_psychology_empirical":
        return "心理健康"
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
    papers_dir = str(config.get("papers_dir", "20_Research/Papers")).strip() or "20_Research/Papers"
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
    for rule_label, keywords in DOMAIN_RULES:
        if rule_label.lower() != name:
            continue
        score += sum(10 for keyword in keywords if keyword in lower)
    if name in lower:
        score += 15
    aliases = {
        "大模型": ("llm", "large language model", "language model", "transformer", "agent", "multimodal"),
        "心理健康": ("depression", "anxiety", "mental health", "clinical", "patient", "therapy"),
    }
    for canonical, terms in aliases.items():
        if canonical.lower() == name:
            score += sum(4 for term in terms if term in lower)
    return score


def resolve_domain_subdir(config: dict[str, Any], *, title: str, abstract: str = "", subdir: str = "") -> str:
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
    papers_dir = str(config.get("papers_dir", "20_Research/Papers")).strip() or "20_Research/Papers"
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
    line = re.sub(r"\s+", " ", line or "").strip()
    if not line:
        return ""
    if re.fullmatch(r"\d+", line):
        return ""
    if re.fullmatch(r"page \d+", line.lower()):
        return ""
    if len(line) <= 2:
        return ""
    return line


def normalize_heading(line: str) -> str:
    line = line.strip().lower()
    line = re.sub(r"^\d+(\.\d+)*\s*", "", line)
    line = re.sub(r"[^a-z\s]", "", line)
    return re.sub(r"\s+", " ", line).strip()


SECTION_ALIASES = {
    "abstract": {"abstract"},
    "introduction": {"introduction", "background", "preliminaries", "preliminary"},
    "method": {"method", "methods", "approach", "approaches", "methodology", "framework", "model", "models"},
    "experiment": {"experiment", "experiments", "evaluation", "evaluations", "results", "analysis", "ablations", "ablation"},
    "conclusion": {"conclusion", "conclusions", "discussion", "discussions", "future work", "limitations"},
}

STOP_SECTION_ALIASES = {"references", "appendix", "appendices", "acknowledgments", "acknowledgements"}


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


def extract_caption_lines(pdf_text: str, kind: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen = set()
    lines = [clean_pdf_line(line) for line in pdf_text.splitlines()]
    if kind == "figure":
        pattern = re.compile(r"^(fig(?:ure)?\.?\s*\d+[a-z]?)[:.\s-]*(.*)$", re.IGNORECASE)
    else:
        pattern = re.compile(r"^(table\.?\s*\d+[a-z]?)[:.\s-]*(.*)$", re.IGNORECASE)
    for idx, line in enumerate(lines):
        if not line:
            continue
        match = pattern.match(line)
        if not match:
            continue
        label = normalize_whitespace(match.group(1))
        caption = normalize_whitespace(match.group(2))
        if not caption and idx + 1 < len(lines):
            caption = normalize_whitespace(lines[idx + 1])
        marker = f"{label.lower()}::{caption.lower()}"
        if marker in seen:
            continue
        seen.add(marker)
        results.append({"id": label, "caption": caption})
    return results


def infer_paper_type(title: str, abstract: str) -> tuple[str, str]:
    lower = f"{title} {abstract}".lower()
    if any(token in lower for token in ["survey", "overview", "tutorial"]):
        return "humanities_or_social_science", "The paper is survey-like or overview-oriented rather than a single empirical method report."
    if any(token in lower for token in ["benchmark", "leaderboard", "evaluation suite", "dataset", "corpus"]):
        return "benchmark_or_dataset", "The paper emphasizes benchmark, dataset, or evaluation design."
    if any(token in lower for token in ["depression", "anxiety", "mental health", "clinical", "patient", "psychiatric", "psychological", "hospital"]):
        return "clinical_or_psychology_empirical", "The paper is closer to an empirical clinical or psychology study."
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


TERM_REPLACEMENTS = [
    (r"\bLarge Language Models?\b", "大语言模型"),
    (r"\bLLMs?\b", "大语言模型"),
    (r"\bbenchmark(s)?\b", "基准测试"),
    (r"\bmultimodal\b", "多模态"),
    (r"\bvision-language\b", "视觉语言"),
    (r"\bfine-tuning\b", "微调"),
    (r"\binference\b", "推理"),
    (r"\breasoning\b", "推理"),
    (r"\bagent(s)?\b", "智能体"),
    (r"\bframework(s)?\b", "框架"),
    (r"\bmodel(s)?\b", "模型"),
    (r"\bpipeline(s)?\b", "流程"),
    (r"\bdataset(s)?\b", "数据集"),
]


def apply_term_replacements(text: str) -> str:
    updated = normalize_whitespace(text)
    for pattern, replacement in TERM_REPLACEMENTS:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
    updated = re.sub(r"\s+", " ", updated).strip(" .;,:")
    return updated


def shorten_clause(text: str, max_len: int = 140) -> str:
    cleaned = normalize_whitespace(text)
    if len(cleaned) <= max_len:
        return cleaned
    pivot = cleaned[:max_len].rsplit(" ", 1)[0]
    return (pivot or cleaned[:max_len]).rstrip(",;:") + "..."


def english_sentence_to_cn(sentence: str) -> str:
    raw = normalize_whitespace(sentence).rstrip(".")
    if not raw:
        return ""

    converted = apply_term_replacements(raw)
    converted = re.sub(r"\bet al\.?\b", "等人", converted, flags=re.IGNORECASE)

    patterns = [
        (r"^This paper (?:studies|investigates) (.+)$", "这篇论文研究的是%s。"),
        (r"^This work (?:studies|investigates) (.+)$", "这项工作研究的是%s。"),
        (r"^This paper presents (.+)$", "这篇论文提出了%s。"),
        (r"^This work presents (.+)$", "这项工作提出了%s。"),
        (r"^We propose (.+)$", "作者提出了%s。"),
        (r"^We present (.+)$", "作者提出了%s。"),
        (r"^We introduce (.+)$", "作者引入了%s。"),
        (r"^To evaluate (.+)$", "为了评估%s。"),
        (r"^Experiments show that (.+)$", "实验结果表明%s。"),
        (r"^Results show that (.+)$", "结果表明%s。"),
        (r"^However,? (.+)$", "但需要注意的是，%s。"),
    ]
    for pattern, template in patterns:
        match = re.match(pattern, converted, flags=re.IGNORECASE)
        if match:
            return template % shorten_clause(match.group(1))

    if converted.lower().startswith("the paper"):
        converted = re.sub(r"^the paper", "论文", converted, flags=re.IGNORECASE)
    elif converted.lower().startswith("this paper"):
        converted = re.sub(r"^this paper", "这篇论文", converted, flags=re.IGNORECASE)
    elif converted.lower().startswith("this work"):
        converted = re.sub(r"^this work", "这项工作", converted, flags=re.IGNORECASE)
    return shorten_clause(converted)


def paraphrase_sentences_to_cn(sentences: list[str], *, limit: int = 4) -> list[str]:
    rewritten: list[str] = []
    seen = set()
    for sentence in sentences:
        cn = english_sentence_to_cn(sentence)
        marker = normalize_title(cn)
        if not cn or marker in seen:
            continue
        seen.add(marker)
        rewritten.append(cn)
        if len(rewritten) >= limit:
            break
    return rewritten


def finalize_cn_line(text: str, *, max_len: int = 140) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    if re.search(r"[A-Za-z]", cleaned) and not re.search(r"[\u4e00-\u9fff]", cleaned):
        cleaned = english_sentence_to_cn(cleaned)
    else:
        cleaned = apply_term_replacements(cleaned)
    return shorten_clause(cleaned, max_len=max_len)
