"""Fetch and normalize paper metadata from arXiv, Crossref, Semantic Scholar, and OpenAlex."""

from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any

from _local_pdf_title import extract_local_pdf_hints
from common import (
    _record_arxiv_id,
    _string_field,
    adjudicate_identity_observations,
    apply_identity_confidence,
    choose_best_title_match,
    clean_local_pdf_stem,
    env_config_value,
    extract_arxiv_id,
    extract_doi,
    infer_source_type,
    normalize_identity_title,
    normalize_title,
    normalize_whitespace,
    paper_id_for_record,
    strip_tags,
)

try:
    import certifi  # type: ignore
except ImportError:  # pragma: no cover
    certifi = None


ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
DEFAULT_USER_AGENT = "DeepPaperNote/0.1"


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
