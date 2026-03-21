#!/usr/bin/env python3
"""Collect and merge metadata from Zotero, DOI, Semantic Scholar, OpenAlex, arXiv, and publisher pages."""

from __future__ import annotations

from common import base_parser, emit, enrich_metadata, maybe_load_json_record, paper_id_for_record, resolve_reference


def main() -> None:
    parser = base_parser(__doc__ or "collect metadata")
    args = parser.parse_args()

    if not args.input:
        raise SystemExit("collect_metadata.py requires --input.")

    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        record = dict(input_record)
    else:
        record = resolve_reference(args.input)

    metadata = enrich_metadata(record)
    metadata["paper_id"] = args.paper_id or metadata.get("paper_id") or paper_id_for_record(metadata)
    metadata["status"] = "ok"
    metadata["script"] = "collect_metadata.py"
    emit(metadata, args.output)


if __name__ == "__main__":
    main()
