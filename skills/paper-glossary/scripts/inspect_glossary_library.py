#!/usr/bin/env python3
"""Inspect selected terms against an existing glossary library."""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_common import (
    elapsed_ms,
    emit,
    load_json_file,
    validate_current_provenance_chain,
)
from glossary_library import inspect_selected_terms


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--terms", required=True, help="Selected-term JSON path.")
    result.add_argument("--terms-dir", required=True, help="Existing glossary directory.")
    result.add_argument("--source-manifest", required=True, help="Current source manifest.")
    result.add_argument("--raw-sections", default="", help="Optional current raw-sections JSONL.")
    result.add_argument(
        "--reviewed-shortlist", required=True, help="Saved reviewed-shortlist artifact."
    )
    result.add_argument("--output", default="", help="Output JSON status path.")
    return result


def _selected_terms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selected = payload.get("selected", payload.get("terms", []))
    if not isinstance(selected, list):
        raise SystemExit("Selected-term JSON must contain a 'selected' list.")
    return selected


def _selection_provenance(
    payload: dict[str, Any],
    selected: list[dict[str, Any]],
    source_manifest: str,
    raw_sections: str,
    reviewed_shortlist: str,
) -> dict[str, Any]:
    if payload.get("mode") != "triage":
        raise SystemExit("Selected terms must be a triage artifact with valid provenance.")
    return validate_current_provenance_chain(
        payload,
        selected,
        source_manifest,
        raw_sections,
        reviewed_shortlist,
    )["provenance"]


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    payload = load_json_file(Path(args.terms).expanduser().resolve())
    selected = _selected_terms(payload)
    provenance = _selection_provenance(
        payload,
        selected,
        args.source_manifest,
        args.raw_sections,
        args.reviewed_shortlist,
    )
    results = inspect_selected_terms(
        selected, Path(args.terms_dir).expanduser().resolve()
    )
    emit(
        {
            "status": "ok",
            "script": "inspect_glossary_library.py",
            "paper_id": payload["paper_id"],
            "provenance": provenance,
            "results": results,
            "elapsed_ms": elapsed_ms(started),
        },
        args.output,
    )


if __name__ == "__main__":
    main()
