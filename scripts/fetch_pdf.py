#!/usr/bin/env python3
"""Acquire the best available PDF or equivalent full text for one paper."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    default_pdf_path,
    emit,
    enrich_metadata,
    extract_doi,
    http_get_bytes,
    maybe_load_json_record,
    paper_id_for_record,
    resolve_reference,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "fetch pdf")
    p.add_argument("--input", required=True, help="Metadata JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output path for JSON status.")
    p.add_argument("--paper-id", default="", help="Canonical paper id if already known.")
    p.add_argument("--dest-dir", default="", help="Directory for downloaded PDFs.")
    return p


def is_pdf_content(data: bytes) -> bool:
    return b"%PDF-" in data[:1024]


def frontiers_pdf_url_from_doi(doi: str) -> str:
    normalized = extract_doi(doi) or ""
    if not normalized.lower().startswith("10.3389/"):
        return ""
    return f"https://www.frontiersin.org/articles/{normalized}/pdf"


def append_candidate(candidates: list[tuple[str, str]], kind: str, value: str) -> None:
    cleaned = value.strip()
    if cleaned and (kind, cleaned) not in candidates:
        candidates.append((kind, cleaned))


def choose_pdf_source(record: dict) -> tuple[str, str]:
    candidates = pdf_source_candidates(record)
    return candidates[0] if candidates else ("", "")


def pdf_source_candidates(record: dict) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    local_pdf = str(record.get("local_pdf_path", "")).strip()
    if local_pdf and Path(local_pdf).expanduser().exists():
        return [("local_pdf", str(Path(local_pdf).expanduser().resolve()))]

    pdf_url = str(record.get("pdf_url", "")).strip()
    if pdf_url:
        append_candidate(candidates, "pdf_url", pdf_url)

    source_url = str(record.get("source_url", "")).strip()
    if source_url.lower().endswith(".pdf"):
        append_candidate(candidates, "pdf_url", source_url)

    arxiv_id = str(record.get("arxiv_id", "")).strip()
    if arxiv_id:
        append_candidate(candidates, "pdf_url", f"https://arxiv.org/pdf/{arxiv_id}.pdf")

    doi = extract_doi(str(record.get("doi", "")).strip())
    if doi:
        enriched = enrich_metadata({"doi": doi, "title": record.get("title", "")})
        enriched_pdf = str(enriched.get("pdf_url", "")).strip()
        if enriched_pdf:
            append_candidate(candidates, "pdf_url", enriched_pdf)
        frontiers_pdf = frontiers_pdf_url_from_doi(doi)
        if frontiers_pdf:
            append_candidate(candidates, "pdf_url", frontiers_pdf)

    return candidates


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        record = dict(input_record)
    else:
        record = enrich_metadata(resolve_reference(args.input))

    record["paper_id"] = args.paper_id or record.get("paper_id") or paper_id_for_record(record)
    source_candidates = pdf_source_candidates(record)
    source_kind, source_value = source_candidates[0] if source_candidates else ("", "")

    if not source_kind:
        payload = {
            "status": "error",
            "script": "fetch_pdf.py",
            "paper_id": record["paper_id"],
            "title": record.get("title", ""),
            "error": "No accessible PDF source found.",
            "source_url": record.get("source_url", ""),
        }
        emit(payload, args.output)
        raise SystemExit(1)

    if source_kind == "local_pdf":
        pdf_path = Path(source_value)
        payload = {
            "status": "ok",
            "script": "fetch_pdf.py",
            "paper_id": record["paper_id"],
            "title": record.get("title", ""),
            "pdf_path": str(pdf_path),
            "pdf_source": "local_pdf",
            "source_url": record.get("source_url", "") or str(pdf_path),
            "pdf_url": "",
        }
        emit(payload, args.output)
        return

    target_path = default_pdf_path(record, dest_dir=args.dest_dir)
    attempted_sources: list[dict[str, str]] = []
    downloaded: tuple[str, str, bytes] | None = None
    for candidate_kind, candidate_value in source_candidates:
        if candidate_kind != "pdf_url":
            continue
        try:
            data = http_get_bytes(candidate_value)
        except Exception as exc:
            attempted_sources.append(
                {"kind": candidate_kind, "url": candidate_value, "status": f"download_error:{exc}"}
            )
            continue
        if not is_pdf_content(data):
            attempted_sources.append(
                {"kind": candidate_kind, "url": candidate_value, "status": "not_pdf_content"}
            )
            continue
        downloaded = (candidate_kind, candidate_value, data)
        break

    if downloaded is None:
        payload = {
            "status": "error",
            "script": "fetch_pdf.py",
            "paper_id": record["paper_id"],
            "title": record.get("title", ""),
            "error": "No candidate URL returned PDF content.",
            "source_url": record.get("source_url", ""),
            "attempted_sources": attempted_sources,
        }
        emit(payload, args.output)
        raise SystemExit(1)

    source_kind, source_value, pdf_bytes = downloaded
    target_path.write_bytes(pdf_bytes)
    payload = {
        "status": "ok",
        "script": "fetch_pdf.py",
        "paper_id": record["paper_id"],
        "title": record.get("title", ""),
        "pdf_path": str(target_path),
        "pdf_source": "downloaded",
        "source_url": record.get("source_url", ""),
        "pdf_url": source_value,
        "file_size": target_path.stat().st_size,
    }
    if attempted_sources:
        payload["attempted_sources"] = attempted_sources
    emit(payload, args.output)


if __name__ == "__main__":
    main()
