#!/usr/bin/env python3
"""Emit the accepted acquisition Paper Identity contract for trusted inputs."""

from __future__ import annotations

import argparse

from common import (
    ACCEPTED_IDENTITY_VERDICTS,
    build_canonical_identity_artifact,
    build_identity_repair_trace,
    emit,
    maybe_load_json_record,
    require_ok_input_artifact,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "build identity contract")
    p.add_argument("--input", required=True, help="Metadata JSON path or JSON string.")
    p.add_argument("--resolve", default="", help="Resolve artifact path for provenance.")
    p.add_argument("--trace-output", required=True, help="Identity repair trace JSON output path.")
    p.add_argument("--output", required=True, help="Canonical Identity Artifact JSON output path.")
    return p


def load_required_record(value: str, consumer: str) -> dict:
    record = maybe_load_json_record(value)
    if record is None:
        raise SystemExit(f"{consumer} requires a JSON acquisition artifact input.")
    return dict(require_ok_input_artifact(record, consumer))


def load_optional_record(value: str, consumer: str) -> dict | None:
    record = maybe_load_json_record(value)
    if record is None:
        return None
    return dict(require_ok_input_artifact(record, consumer))


def main() -> None:
    args = parser().parse_args()
    metadata = load_required_record(args.input, "build_identity_contract.py")
    source_record = load_optional_record(args.resolve, "build_identity_contract.py")

    trace = build_identity_repair_trace(
        metadata,
        source_record=source_record,
        resolve_artifact_path=args.resolve,
        metadata_artifact_path=args.input,
    )
    emit(trace, args.trace_output)

    identity = build_canonical_identity_artifact(
        metadata,
        source_record=source_record,
        repair_trace_path=args.trace_output,
        resolve_artifact_path=args.resolve,
        metadata_artifact_path=args.input,
    )
    emit(identity, args.output)
    verdict = str(identity.get("identity_verdict", "")).lower().replace("-", "_")
    if verdict not in ACCEPTED_IDENTITY_VERDICTS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
