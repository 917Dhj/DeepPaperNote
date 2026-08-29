#!/usr/bin/env python3
"""Acquire the best available PDF or equivalent full text for one paper."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    canonical_identity_summary,
    default_pdf_path,
    emit,
    fetch_record_from_canonical_identity,
    file_sha256,
    http_get_bytes,
    maybe_load_json_record,
    paper_id_for_record,
    require_accepted_canonical_identity,
    require_ok_input_artifact,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "fetch pdf")
    p.add_argument("--input", required=True, help="Metadata JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output path for JSON status.")
    p.add_argument("--dest-dir", default="", help="Directory for downloaded PDFs.")
    p.add_argument(
        "--identity",
        default="",
        help="Accepted Canonical Identity Artifact JSON path or JSON string.",
    )
    return p


def is_pdf_content(data: bytes) -> bool:
    return b"%PDF-" in data[:1024]


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if not args.identity:
        raise SystemExit("fetch_pdf.py requires an accepted --identity artifact.")
    identity_summary: dict = {}
    source_manifestation: dict = {}
    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        require_ok_input_artifact(input_record, "fetch_pdf.py")
    identity_record = maybe_load_json_record(args.identity)
    if identity_record is None:
        raise SystemExit("fetch_pdf.py requires --identity to be a JSON artifact.")
    identity = require_accepted_canonical_identity(identity_record, "fetch_pdf.py")
    if not isinstance(identity.get("bound_sources"), list):
        raise SystemExit("fetch_pdf.py requires canonical identity bound_sources.")
    identity_summary = canonical_identity_summary(identity)
    source_manifestation = dict(identity_summary.get("source_manifestation", {}) or {})
    record = fetch_record_from_canonical_identity(identity)

    record["paper_id"] = record.get("paper_id") or paper_id_for_record(record)
    source_candidates = [
        (str(item.get("kind", "")), str(item.get("value", "")))
        for item in identity.get("bound_sources", []) or []
        if isinstance(item, dict)
        and item.get("kind") in {"local_pdf", "pdf_url"}
        and str(item.get("value", "")).strip()
    ]

    if not source_candidates:
        payload = {
            "status": "error",
            "script": "fetch_pdf.py",
            "paper_id": record["paper_id"],
            "title": record.get("title", ""),
            "error": "No accessible PDF source found.",
            "source_url": record.get("source_url", ""),
        }
        if identity_summary:
            payload["identity_contract"] = identity_summary
            payload["source_manifestation"] = source_manifestation
        emit(payload, args.output)
        raise SystemExit(1)

    attempted_sources: list[dict[str, str]] = []
    downloaded: tuple[str, str, bytes] | None = None
    for candidate_kind, candidate_value in source_candidates:
        if candidate_kind == "local_pdf":
            pdf_path = Path(candidate_value).expanduser()
            if not pdf_path.exists() or not pdf_path.is_file():
                attempted_sources.append(
                    {
                        "kind": "local_pdf",
                        "path": candidate_value,
                        "status": "missing_file",
                    }
                )
                continue
            pdf_path = pdf_path.resolve()
            payload = {
                "status": "ok",
                "script": "fetch_pdf.py",
                "paper_id": record["paper_id"],
                "title": record.get("title", ""),
                "pdf_path": str(pdf_path),
                "pdf_source": "local_pdf",
                "source_url": record.get("source_url", "") or str(pdf_path),
                "pdf_url": "",
                "source_sha256": file_sha256(pdf_path),
            }
            if identity_summary:
                payload["identity_contract"] = identity_summary
                payload["source_manifestation"] = source_manifestation
            if attempted_sources:
                payload["attempted_sources"] = attempted_sources
            emit(payload, args.output)
            return
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
        if identity_summary:
            payload["identity_contract"] = identity_summary
            payload["source_manifestation"] = source_manifestation
        emit(payload, args.output)
        raise SystemExit(1)

    target_path = default_pdf_path(record, dest_dir=args.dest_dir)
    _, source_value, pdf_bytes = downloaded
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
        "source_sha256": file_sha256(target_path),
    }
    if identity_summary:
        payload["identity_contract"] = identity_summary
        payload["source_manifestation"] = source_manifestation
    if attempted_sources:
        payload["attempted_sources"] = attempted_sources
    emit(payload, args.output)


if __name__ == "__main__":
    main()
