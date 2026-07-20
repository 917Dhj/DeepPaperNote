#!/usr/bin/env python3
"""Resolve a title, DOI, URL, arXiv ID, local PDF, or Zotero item into one paper identity."""

from __future__ import annotations

from typing import Any

from _zotero_local import lookup_zotero_local
from common import (
    base_parser,
    emit,
    infer_source_type,
    maybe_load_json_record,
    paper_id_for_record,
    require_ok_input_artifact,
    resolve_reference,
)

ZOTERO_MODES = ("auto", "off", "required")
ZOTERO_QUERY_SOURCE_TYPES = {
    "arxiv_id",
    "arxiv_url",
    "doi",
    "doi_url",
    "title",
    "title_query",
    "zotero_key",
}
ZOTERO_BYPASS_SOURCE_TYPES = {"local_pdf"}


class ZoteroResolutionError(RuntimeError):
    """Raised when Zotero mode requires the resolver to stop fail-closed."""

    def __init__(self, message: str, *, lookup: dict[str, Any], failure_class: str) -> None:
        super().__init__(message)
        self.lookup = lookup
        self.failure_class = failure_class


def parser():
    p = base_parser(__doc__ or "resolve paper")
    p.add_argument(
        "--zotero-mode",
        choices=ZOTERO_MODES,
        default="auto",
        help=(
            "Local Zotero lookup policy: auto prefers unique local matches, off preserves "
            "the web-only path, and required fails unless Zotero resolves the reference."
        ),
    )
    return p


def zotero_lookup_summary(result: dict[str, Any], *, mode: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mode": mode,
        "status": str(result.get("status", "error")),
        "match_kind": str(result.get("match_kind", "")),
    }
    if result.get("candidate_count") is not None:
        summary["candidate_count"] = result["candidate_count"]
    probe = result.get("probe", {})
    if isinstance(probe, dict) and probe:
        summary["api_status"] = str(probe.get("status", ""))
        summary["api_version"] = str(probe.get("api_version", ""))
        summary["schema_version"] = str(probe.get("schema_version", ""))
    error = result.get("error", {})
    if isinstance(error, dict) and error:
        summary["error"] = dict(error)
    return summary


def _zotero_failure(result: dict[str, Any], *, mode: str) -> ZoteroResolutionError:
    status = str(result.get("status", "error"))
    summary = zotero_lookup_summary(result, mode=mode)
    if status == "ambiguous":
        return ZoteroResolutionError(
            "Zotero returned multiple equally plausible local items; provide a DOI, arXiv ID, "
            "or exact Zotero item key.",
            lookup=summary,
            failure_class="zotero_ambiguous_match",
        )
    error = result.get("error", {})
    error_code = str(error.get("code", "")) if isinstance(error, dict) else ""
    if str(result.get("match_kind", "")) == "unsupported_reference":
        failure_class = "zotero_unsupported_reference"
    else:
        failure_class = error_code or (
            "zotero_item_not_found" if status == "not_found" else "zotero_lookup_failed"
        )
    return ZoteroResolutionError(
        "Zotero Local API could not uniquely resolve this reference while "
        f"--zotero-mode={mode} is active.",
        lookup=summary,
        failure_class=failure_class,
    )


def resolve_scalar_reference(reference: str, *, zotero_mode: str = "auto") -> dict[str, Any]:
    if zotero_mode not in ZOTERO_MODES:
        raise ValueError(f"Unsupported Zotero mode: {zotero_mode}")
    source_type = infer_source_type(reference)
    if zotero_mode == "off" or source_type in ZOTERO_BYPASS_SOURCE_TYPES:
        return resolve_reference(reference)

    if source_type not in ZOTERO_QUERY_SOURCE_TYPES:
        if zotero_mode == "required":
            result = {
                "status": "not_found",
                "match_kind": "unsupported_reference",
            }
            raise _zotero_failure(result, mode=zotero_mode)
        return resolve_reference(reference)

    lookup = lookup_zotero_local(reference, reference_type=source_type)
    lookup_status = str(lookup.get("status", "error"))
    explicit_zotero_reference = source_type == "zotero_key" or reference.strip().lower().startswith(
        "zotero://select/"
    )
    if lookup_status == "match":
        record = lookup.get("record", {})
        if not isinstance(record, dict):
            lookup = {
                "status": "error",
                "match_kind": source_type,
                "error": {
                    "code": "zotero_invalid_response",
                    "message": "Zotero lookup returned an invalid record.",
                    "retryable": False,
                },
            }
        else:
            resolved = dict(record)
            resolved["zotero_lookup"] = zotero_lookup_summary(lookup, mode=zotero_mode)
            return resolved

    if lookup_status == "ambiguous" or zotero_mode == "required" or explicit_zotero_reference:
        raise _zotero_failure(lookup, mode=zotero_mode)

    resolved = resolve_reference(reference)
    resolved["zotero_lookup"] = zotero_lookup_summary(lookup, mode=zotero_mode)
    return resolved


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)

    if not args.input:
        raise SystemExit("resolve_paper.py requires --input.")

    input_record = maybe_load_json_record(args.input)
    if input_record is not None:
        resolved = dict(require_ok_input_artifact(input_record, "resolve_paper.py"))
    else:
        try:
            resolved = resolve_scalar_reference(args.input, zotero_mode=args.zotero_mode)
        except ZoteroResolutionError as exc:
            emit(
                {
                    "status": "error",
                    "run_status": "failed",
                    "script": "resolve_paper.py",
                    "failure_class": exc.failure_class,
                    "failure_summary": str(exc),
                    "zotero_lookup": exc.lookup,
                },
                args.output,
            )
            raise SystemExit(str(exc)) from exc

    resolved["paper_id"] = (
        args.paper_id or resolved.get("paper_id") or paper_id_for_record(resolved)
    )
    resolved["status"] = resolved.get("status") or "ok"
    resolved["script"] = "resolve_paper.py"
    emit(resolved, args.output)


if __name__ == "__main__":
    main()
