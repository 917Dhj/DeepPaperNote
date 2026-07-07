#!/usr/bin/env python3
"""Create a deterministic paper input record from trusted metadata such as Zotero results."""

from __future__ import annotations

import argparse
import json

from common import emit, normalize_whitespace, paper_id_for_record


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "create input record")
    p.add_argument("--title", required=True, help="Canonical paper title.")
    p.add_argument("--translated-title", default="", help="Optional translated title.")
    p.add_argument("--authors-json", default="[]", help="JSON array of author names.")
    p.add_argument("--affiliations-json", default="[]", help="JSON array of affiliations.")
    p.add_argument("--year", default="", help="Publication year.")
    p.add_argument("--venue", default="", help="Venue or journal.")
    p.add_argument("--doi", default="", help="DOI if known.")
    p.add_argument("--arxiv-id", default="", help="arXiv id if known.")
    p.add_argument("--source-url", default="", help="Canonical source URL.")
    p.add_argument("--pdf-url", default="", help="Preferred PDF URL if known.")
    p.add_argument("--local-pdf-path", default="", help="Local PDF path if already available.")
    p.add_argument("--zotero-key", default="", help="Local Zotero item key.")
    p.add_argument("--abstract", default="", help="Abstract text when available.")
    p.add_argument("--source-type", default="", help="Optional explicit source type.")
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def parse_json_list(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    values: list[str] = []
    for item in data:
        cleaned = normalize_whitespace(str(item))
        if cleaned:
            values.append(cleaned)
    return values


def main() -> None:
    args = parser().parse_args()
    record = {
        "status": "ok",
        "script": "create_input_record.py",
        "title": normalize_whitespace(args.title),
        "translated_title": normalize_whitespace(args.translated_title),
        "authors": parse_json_list(args.authors_json),
        "affiliations": parse_json_list(args.affiliations_json),
        "year": normalize_whitespace(args.year),
        "venue": normalize_whitespace(args.venue),
        "doi": normalize_whitespace(args.doi),
        "arxiv_id": normalize_whitespace(args.arxiv_id),
        "source_url": normalize_whitespace(args.source_url),
        "pdf_url": normalize_whitespace(args.pdf_url),
        "local_pdf_path": normalize_whitespace(args.local_pdf_path),
        "zotero_key": normalize_whitespace(args.zotero_key),
        "abstract": normalize_whitespace(args.abstract),
        "source_type": normalize_whitespace(args.source_type)
        or ("zotero_seed" if normalize_whitespace(args.zotero_key) else "seed_record"),
        "metadata_sources": ["zotero_seed"] if normalize_whitespace(args.zotero_key) else ["seed_record"],
    }
    record["paper_id"] = paper_id_for_record(record)
    emit(record, args.output)


if __name__ == "__main__":
    main()
