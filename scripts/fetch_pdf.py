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


def choose_pdf_source(record: dict) -> tuple[str, str]:
    local_pdf = str(record.get("local_pdf_path", "")).strip()
    if local_pdf and Path(local_pdf).expanduser().exists():
        return "local_pdf", str(Path(local_pdf).expanduser().resolve())

    pdf_url = str(record.get("pdf_url", "")).strip()
    if pdf_url:
        return "pdf_url", pdf_url

    source_url = str(record.get("source_url", "")).strip()
    if source_url.lower().endswith(".pdf"):
        return "pdf_url", source_url

    arxiv_id = str(record.get("arxiv_id", "")).strip()
    if arxiv_id:
        return "pdf_url", f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    doi = extract_doi(str(record.get("doi", "")).strip())
    if doi:
        enriched = enrich_metadata({"doi": doi, "title": record.get("title", "")})
        enriched_pdf = str(enriched.get("pdf_url", "")).strip()
        if enriched_pdf:
            return "pdf_url", enriched_pdf

    return "", ""


def main() -> None:
    args = parser().parse_args()
    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        record = dict(input_record)
    else:
        record = enrich_metadata(resolve_reference(args.input))

    record["paper_id"] = args.paper_id or record.get("paper_id") or paper_id_for_record(record)
    source_kind, source_value = choose_pdf_source(record)

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
    target_path.write_bytes(http_get_bytes(source_value))
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
    emit(payload, args.output)


if __name__ == "__main__":
    main()
