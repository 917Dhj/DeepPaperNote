#!/usr/bin/env python3
"""Find a verified local source without changing the Vault."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import emit, maybe_load_json_record, runtime_config
from paper_archive import ArchiveError, find_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Metadata JSON or original paper reference.")
    parser.add_argument("--vault", default="")
    parser.add_argument(
        "--reference", default="", help="Original user reference; preserves explicit versions."
    )
    parser.add_argument("--target-directory", default="")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    record = maybe_load_json_record(args.input) or {"source_url": args.input}
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", args.input):
        record["arxiv_id"] = args.input
    vault = args.vault or runtime_config().get("obsidian_vault", "")
    try:
        if not vault or not Path(vault).expanduser().is_dir():
            raise ArchiveError("invalid_vault", [vault])
        source = find_source(
            Path(vault).expanduser().resolve(),
            record,
            args.reference or args.input,
            args.target_directory,
            args.source_sha256,
        )
        emit({"status": "ok" if source else "not_found", **(source or {})}, args.output)
    except ArchiveError as exc:
        emit({"status": "blocked", "conflict_code": exc.code, "candidates": exc.paths}, args.output)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
