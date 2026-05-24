#!/usr/bin/env python3
"""Validate that a note plan is grounded in the canonical source manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import caption_label_key, emit, maybe_load_json_record, normalize_whitespace
from contracts import (
    NOTE_PLAN_LIST_FIELDS,
    NOTE_PLAN_REQUIRED_FIELDS,
    NOTE_PLAN_STRING_FIELDS,
    PAPER_TYPE_VALUES,
    WRITING_CONTRACT_RULES,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "lint grounding")
    p.add_argument("--note-plan", required=True, help="note_plan JSON path or JSON string.")
    p.add_argument(
        "--source-manifest",
        required=True,
        help="Source manifest JSON path or JSON string.",
    )
    p.add_argument(
        "--bundle-json",
        default="",
        help="Optional synthesis bundle JSON path or JSON string.",
    )
    p.add_argument(
        "--figure-decisions",
        required=True,
        help="Figure/table decisions JSON path or JSON string.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def load_record(value: str) -> dict[str, Any]:
    record = maybe_load_json_record(value)
    if record is not None:
        return record
    path = Path(value).expanduser()
    if path.exists() and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    raise SystemExit(f"Expected JSON object for {value!r}.")


def issue(code: str, severity: str = "error", **details: Any) -> dict[str, Any]:
    payload = {"code": code, "severity": severity}
    payload.update(details)
    return payload


def source_section_ids(source_manifest: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in source_manifest.get("sections", []) or []:
        if isinstance(section, dict):
            sid = normalize_whitespace(str(section.get("section_id", "")))
            if sid:
                ids.add(sid)
    for page in source_manifest.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        for sid in page.get("section_ids", []) or []:
            cleaned = normalize_whitespace(str(sid))
            if cleaned:
                ids.add(cleaned)
    return ids


def total_pages(source_manifest: dict[str, Any]) -> int:
    for container in (source_manifest.get("coverage", {}), source_manifest.get("pdf", {})):
        if isinstance(container, dict):
            value = int(container.get("total_pages", 0) or 0)
            if value:
                return value
    return 0


def source_is_truncated(source_manifest: dict[str, Any]) -> bool:
    for container in (source_manifest.get("coverage", {}), source_manifest.get("pdf", {})):
        if isinstance(container, dict) and (
            container.get("text_truncated") or container.get("truncated_due_to_page_limit")
        ):
            return True
    return False


def accepts_partial_reading(note_plan: dict[str, Any]) -> bool:
    coverage = note_plan.get("source_coverage", {})
    if isinstance(coverage, dict) and coverage.get("partial_reading_accepted") is True:
        return True
    return normalize_whitespace(str(note_plan.get("reading_mode", ""))).lower() in {
        "partial",
        "accepted_partial",
        "partial_reading",
    }


def contains_old_reference(value: Any) -> bool:
    prefixes = WRITING_CONTRACT_RULES["old_bundle_reference_prefixes"]
    tokens = WRITING_CONTRACT_RULES.get("old_evidence_reference_tokens", ())
    if isinstance(value, str):
        return any(prefix in value for prefix in prefixes) or any(
            token in value for token in tokens
        )
    if isinstance(value, dict):
        return any(contains_old_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_old_reference(item) for item in value)
    return False


def valid_section_id(value: Any, valid_ids: set[str]) -> bool:
    section_id = normalize_whitespace(str(value))
    return bool(section_id and section_id in valid_ids)


def valid_pages(value: Any, max_page: int) -> bool:
    if max_page <= 0:
        return False
    if isinstance(value, dict):
        try:
            start = int(value.get("start", 0) or value.get("page_start", 0) or 0)
            end = int(value.get("end", 0) or value.get("page_end", 0) or start or 0)
        except (TypeError, ValueError):
            return False
        return 1 <= start <= end <= max_page
    if isinstance(value, int):
        return 1 <= value <= max_page
    if isinstance(value, list) and value:
        try:
            pages = [int(page) for page in value]
        except (TypeError, ValueError):
            return False
        return all(1 <= page <= max_page for page in pages)
    return False


def evidence_sources(item: dict[str, Any]) -> list[Any]:
    for key in ("evidence_sources", "source_refs", "sources", "grounding"):
        value = item.get(key)
        if isinstance(value, list):
            return value
        if value:
            return [value]
    return []


def section_focus_text(item: dict[str, Any]) -> str:
    fields = WRITING_CONTRACT_RULES["note_plan_depth_requirements"][
        "required_section_focus_fields"
    ]
    for field in fields:
        value = normalize_whitespace(str(item.get(field, "")))
        if value:
            return value
    return ""


def focus_is_substantive(text: str) -> bool:
    requirements = WRITING_CONTRACT_RULES["note_plan_depth_requirements"]
    normalized = normalize_whitespace(text)
    lowered = normalized.lower()
    if any(phrase in lowered for phrase in requirements.get("generic_focus_phrases", ())):
        return False
    min_chars = int(requirements["required_section_focus_min_chars"])
    compact = "".join(ch for ch in normalized if not ch.isspace())
    return len(compact) >= min_chars


def source_grounding_errors(source: Any, valid_ids: set[str], max_page: int) -> list[str]:
    if contains_old_reference(source):
        return ["old_bundle_reference"]
    if isinstance(source, str):
        return [] if valid_section_id(source, valid_ids) else ["source_reference_unresolved"]
    if not isinstance(source, dict):
        return ["source_reference_invalid"]

    has_valid_section = valid_section_id(source.get("section_id", ""), valid_ids)
    has_valid_pages = valid_pages(source.get("pages"), max_page) or valid_pages(
        source.get("page_range"),
        max_page,
    )
    if has_valid_section or has_valid_pages:
        return []
    return ["source_reference_missing_valid_section_or_pages"]


def validate_note_plan(
    note_plan: dict[str, Any],
    source_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in NOTE_PLAN_REQUIRED_FIELDS:
        if field not in note_plan:
            issues.append(issue("note_plan_required_field_missing", field=field))
    for field in NOTE_PLAN_STRING_FIELDS:
        if field in note_plan and not normalize_whitespace(str(note_plan.get(field, ""))):
            issues.append(issue("note_plan_required_field_empty", field=field))
    for field in NOTE_PLAN_LIST_FIELDS:
        value = note_plan.get(field)
        if field in note_plan and (not isinstance(value, list) or not value):
            issues.append(issue("note_plan_required_field_empty", field=field))

    paper_type = normalize_whitespace(str(note_plan.get("paper_type", "")))
    if paper_type not in PAPER_TYPE_VALUES:
        issues.append(issue("note_plan_paper_type_invalid", paper_type=paper_type))

    if source_is_truncated(source_manifest) and not accepts_partial_reading(note_plan):
        issues.append(issue("source_manifest_truncated_without_partial_acceptance"))

    valid_ids = source_section_ids(source_manifest)
    max_page = total_pages(source_manifest)
    required_sections = set(WRITING_CONTRACT_RULES["grounding_required_sections"])
    grounded_sections: set[str] = set()
    section_plan = note_plan.get("section_plan", [])
    if not isinstance(section_plan, list):
        issues.append(issue("note_plan_section_plan_invalid"))
        return issues

    for item in section_plan:
        if not isinstance(item, dict):
            issues.append(issue("note_plan_section_plan_item_invalid"))
            continue
        section_name = normalize_whitespace(
            str(item.get("section") or item.get("name") or item.get("heading") or "")
        )
        if section_name in required_sections:
            grounded_sections.add(section_name)
        sources = evidence_sources(item)
        if section_name in required_sections and not sources:
            issues.append(issue("section_plan_grounding_missing", section=section_name))
            continue
        if section_name in required_sections and not focus_is_substantive(
            section_focus_text(item)
        ):
            issues.append(issue("section_plan_focus_too_thin", section=section_name))
        for source in sources:
            for code in source_grounding_errors(source, valid_ids, max_page):
                issues.append(issue(code, section=section_name, source=source))

    for section_name in sorted(required_sections - grounded_sections):
        issues.append(issue("section_plan_required_section_missing", section=section_name))

    issues.extend(validate_central_claims(note_plan, valid_ids, max_page))

    if contains_old_reference(note_plan):
        issues.append(issue("note_plan_old_bundle_reference_present"))

    return issues


def validate_central_claims(
    note_plan: dict[str, Any],
    valid_ids: set[str],
    max_page: int,
) -> list[dict[str, Any]]:
    central_claims = note_plan.get("central_claims", [])
    if "central_claims" not in note_plan:
        return []
    if not isinstance(central_claims, list):
        return [issue("central_claims_invalid")]

    issues: list[dict[str, Any]] = []
    required_text_fields = (
        "claim",
        "what_it_actually_proves",
        "what_it_does_not_prove",
    )
    for index, item in enumerate(central_claims):
        if not isinstance(item, dict):
            issues.append(issue("central_claim_item_invalid", index=index))
            continue
        for field in required_text_fields:
            if not normalize_whitespace(str(item.get(field, ""))):
                issues.append(
                    issue("central_claim_required_field_missing", index=index, field=field)
                )
        sources = item.get("supporting_evidence", [])
        if not isinstance(sources, list) or not sources:
            issues.append(issue("central_claim_supporting_evidence_missing", index=index))
            continue
        for source in sources:
            for code in source_grounding_errors(source, valid_ids, max_page):
                issues.append(issue(code, section="central_claims", source=source, index=index))
    return issues


def validate_bundle_contract(
    note_plan: dict[str, Any],
    bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    if not bundle:
        return []
    issues: list[dict[str, Any]] = []
    for old_key in (
        "evidence",
        "evidence_pack",
        "candidate_chunks",
        "section_texts",
        "summary",
        "summary_hints",
    ):
        if old_key in bundle:
            issues.append(issue("bundle_old_model_input_field_present", field=old_key))
    writing_contract = bundle.get("writing_contract", {})
    if not isinstance(writing_contract, dict):
        issues.append(issue("bundle_writing_contract_missing"))
        return issues
    contracts = writing_contract.get("contracts_by_paper_type", {})
    if not isinstance(contracts, dict) or not contracts:
        issues.append(issue("bundle_contracts_by_paper_type_missing"))
        return issues
    missing = [paper_type for paper_type in PAPER_TYPE_VALUES if paper_type not in contracts]
    if missing:
        issues.append(issue("bundle_contracts_by_paper_type_incomplete", missing=missing))
    paper_type = normalize_whitespace(str(note_plan.get("paper_type", "")))
    if paper_type and paper_type in PAPER_TYPE_VALUES and paper_type not in contracts:
        issues.append(issue("bundle_note_plan_paper_type_contract_missing", paper_type=paper_type))
    return issues


def validate_figure_decisions(
    source_manifest: dict[str, Any],
    decisions_wrapper: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(decisions_wrapper, dict) or "decisions" not in decisions_wrapper:
        return [issue("figure_table_decisions_missing")]
    issues: list[dict[str, Any]] = []
    decisions = decisions_wrapper.get("decisions", [])
    if not isinstance(decisions, list):
        return [issue("figure_table_decisions_invalid")]
    valid_decisions = set(WRITING_CONTRACT_RULES["figure_decision_values"])
    usable_insert = WRITING_CONTRACT_RULES["usable_insert_candidate"]
    insertable_kinds = set(usable_insert.get("kinds", ()))
    decision_ids = {
        normalize_whitespace(
            str(item.get("source_id") or item.get("label") or item.get("item_id") or "")
        )
        for item in decisions
        if isinstance(item, dict)
    }
    decision_label_keys = {
        caption_label_key(source_id)
        for source_id in decision_ids
        if caption_label_key(source_id)
    }
    captions = (
        source_manifest.get("captions", {})
        if isinstance(source_manifest.get("captions"), dict)
        else {}
    )
    for kind in ("figures", "tables"):
        for caption in captions.get(kind, []) or []:
            if not isinstance(caption, dict):
                continue
            caption_id = normalize_whitespace(str(caption.get("id", "")))
            caption_key = caption_label_key(caption_id)
            if caption_id and caption_id not in decision_ids and caption_key not in decision_label_keys:
                issues.append(
                    issue(
                        "figure_table_caption_missing_decision",
                        caption_id=caption_id,
                    )
                )
    for item in decisions:
        if not isinstance(item, dict):
            issues.append(issue("figure_table_decision_item_invalid"))
            continue
        decision = normalize_whitespace(str(item.get("decision", "")))
        if decision not in valid_decisions:
            issues.append(
                issue(
                    "figure_table_decision_value_invalid",
                    decision=decision,
                    source_id=item.get("source_id") or item.get("label") or "",
                )
            )
        if decision == "insert" and not normalize_whitespace(
            str(item.get("source_image_path", ""))
        ):
            issues.append(
                issue(
                    "figure_insert_decision_missing_source_image",
                    source_id=item.get("source_id") or item.get("label") or "",
                )
            )
        is_required_insert_candidate = (
            normalize_whitespace(str(item.get("kind", ""))) in insertable_kinds
            and normalize_whitespace(str(item.get("visual_quality_status", "")))
            == usable_insert["visual_quality_status"]
            and normalize_whitespace(str(item.get("source_image_path", "")))
        )
        if is_required_insert_candidate and decision != "insert":
            skip_reason = normalize_whitespace(str(item.get("skip_reason", "")))
            issues.append(
                issue(
                    "usable_insert_candidate_left_placeholder",
                    source_id=item.get("source_id") or item.get("label") or "",
                    skip_reason=skip_reason,
                )
            )
    return issues


def main() -> None:
    args = parser().parse_args()
    note_plan = load_record(args.note_plan)
    source_manifest = load_record(args.source_manifest)
    bundle = load_record(args.bundle_json) if args.bundle_json else {}
    decisions = load_record(args.figure_decisions)

    issues = []
    issues.extend(validate_note_plan(note_plan, source_manifest))
    issues.extend(validate_bundle_contract(note_plan, bundle))
    issues.extend(validate_figure_decisions(source_manifest, decisions))
    error_issues = [item for item in issues if item.get("severity", "error") == "error"]
    payload = {
        "status": "ok",
        "script": "lint_grounding.py",
        "paper_id": source_manifest.get("paper_id", note_plan.get("paper_id", "")),
        "issues": issues,
        "warnings": [item for item in issues if item.get("severity") == "warning"],
        "passes_grounding": not error_issues,
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
