#!/usr/bin/env python3
"""Resolve a title, DOI, URL, arXiv ID, local PDF, or Zotero item into one paper identity."""

from __future__ import annotations

from common import base_parser, emit, maybe_load_json_record, paper_id_for_record, resolve_reference


def main() -> None:
    parser = base_parser(__doc__ or "resolve paper")
    args = parser.parse_args()

    if not args.input:
        raise SystemExit("resolve_paper.py requires --input.")

    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        resolved = dict(input_record)
    else:
        resolved = resolve_reference(args.input)

    resolved["paper_id"] = args.paper_id or resolved.get("paper_id") or paper_id_for_record(resolved)
    resolved["status"] = resolved.get("status") or "ok"
    resolved["script"] = "resolve_paper.py"
    emit(resolved, args.output)


if __name__ == "__main__":
    main()
