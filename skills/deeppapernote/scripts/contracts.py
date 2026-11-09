#!/usr/bin/env python3
"""Scaffolded JSON contracts for the paper-deep-notes core workflow."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, TypedDict

from localization import note_schema, normalize_output_language
from type_profiles import (
    HEAD_SECTION_KEYS,
    NOT_REPORTED_PHRASE,
    PROFILES,
    SECONDARY_QUESTION_LIMIT,
    TAIL_SECTION_KEYS,
    TYPE_KEYS,
    WEAK_EVIDENCE_CALLOUT,
    WORKFLOW_STEP_RANGE,
    localized_profiles,
    middle_sections,
    question_ids,
    required_question_ids,
)

def note_required_sections(language: str | None = None, paper_type: str = "") -> tuple[str, ...]:
    """Fixed head sections, the paper type's middle sections, then fixed tail sections."""
    resolved = normalize_output_language(language)
    sections = note_schema(resolved)["sections"]
    return (
        tuple(sections[key] for key in HEAD_SECTION_KEYS)
        + middle_sections(paper_type, resolved)
        + tuple(sections[key] for key in TAIL_SECTION_KEYS)
    )


def grounding_required_sections(language: str | None = None, paper_type: str = "") -> tuple[str, ...]:
    """The sections whose plan entries must cite the source: the middle sections plus limitations."""
    resolved = normalize_output_language(language)
    return middle_sections(paper_type, resolved) + (note_schema(resolved)["sections"]["limitations"],)


PAPER_TYPE_VALUES: tuple[str, ...] = TYPE_KEYS

NOTE_PLAN_STRING_FIELDS: tuple[str, ...] = (
    "paper_type",
    "paper_type_rationale",
    "dominant_domain",
    "storyline",
)
# The storyline is the paper's own story in a few sentences: problem, idea, evidence, so what.
STORYLINE_SENTENCE_RANGE = (3, 5)
# Periods inside these do not end a sentence.
_NON_TERMINAL_ABBREVIATIONS = re.compile(r"\b(?:et al|e\.g|i\.e|vs|cf|Fig|Figs|Eq|Eqs|No|Sec|Tab)\.", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[。！？!?]+|\.(?=\s|$)")

NOTE_PLAN_LIST_FIELDS: tuple[str, ...] = (
    "must_cover",
    "key_numbers",
    "real_comparisons",
    "central_claims",
    "claim_boundaries",
    "negative_or_limiting_results",
    "mechanism_result_map",
    "comparative_positioning",
    "reuse_takeaways",
    "followup_questions",
    "key_prior_work",
    "section_plan",
)

NOTE_PLAN_REQUIRED_FIELDS: tuple[str, ...] = NOTE_PLAN_STRING_FIELDS + NOTE_PLAN_LIST_FIELDS
# Optional fields stay in the template so the planner sees them, but an empty value is valid.
NOTE_PLAN_OPTIONAL_STRING_FIELDS: tuple[str, ...] = ("reader_research_direction",)
NOTE_PLAN_OPTIONAL_LIST_FIELDS: tuple[str, ...] = ("connections",)
TAKEAWAY_PLAN_FIELDS: tuple[str, ...] = ("reuse_takeaways", "followup_questions")
# Fields that depend on paper_type; type_plan_issues checks them against the type's profile.
NOTE_PLAN_TYPE_FIELDS: dict[str, str] = {
    "positioning": "string",
    "survey_mode": "string",
    "secondary_type": "string",
    "secondary_host_section": "string",
    "core_answers": "object",
    "workflow": "array",
}
NOTE_PLAN_FIELD_TYPES: dict[str, str] = {
    **dict.fromkeys(NOTE_PLAN_STRING_FIELDS, "string"),
    **dict.fromkeys(NOTE_PLAN_LIST_FIELDS, "array"),
}
REQUIRED_FIELD_CHECKS: dict[str, dict[str, bool]] = {
    "string": {"non_empty": True},
    "array": {"non_empty": True},
}
CENTRAL_CLAIM_FIELD_TYPES: dict[str, str] = {
    "claim": "string",
    "supporting_evidence": "array",
    "what_it_actually_proves": "string",
    "what_it_does_not_prove": "string",
}


def required_field_value_error(
    value: Any,
    field_type: str,
    checks: dict[str, dict[str, bool]],
) -> str:
    if field_type == "string":
        if not isinstance(value, str):
            return "invalid"
        return "empty" if checks["string"]["non_empty"] and not value.strip() else ""
    if field_type == "array":
        if not isinstance(value, list):
            return "invalid"
        return "empty" if checks["array"]["non_empty"] and not value else ""
    return "invalid"

def paper_type_contracts(language: str | None = None) -> dict[str, dict[str, Any]]:
    return localized_profiles(normalize_output_language(language))

WRITING_CONTRACT_RULES: dict[str, Any] = {
    "paper_type_values": PAPER_TYPE_VALUES,
    "note_plan_required_fields": NOTE_PLAN_REQUIRED_FIELDS,
    "note_plan_field_types": NOTE_PLAN_FIELD_TYPES,
    "note_plan_required_field_checks": REQUIRED_FIELD_CHECKS,
    "allowed_grounding_reference_forms": ("section_id", "pages"),
    "excluded_model_input_fields": (
        "evidence",
        "evidence_pack",
        "candidate_chunks",
        "section_texts",
        "summary",
        "summary_hints",
    ),
    "old_bundle_reference_prefixes": (
        "synthesis_bundle.evidence",
        "bundle.evidence",
        "synthesis_bundle.candidate_chunks",
        "synthesis_bundle.section_texts",
        "synthesis_bundle.summary",
        "bundle.candidate_chunks",
        "bundle.section_texts",
        "bundle.summary",
    ),
    "old_evidence_reference_tokens": (
        "evidence_pack",
        "summary.paper_type",
        "problem_evidence",
        "task_evidence",
        "data_evidence",
        "method_evidence",
        "mechanism_evidence",
        "results_evidence",
        "ablation_evidence",
        "limitations_evidence",
        "candidate_chunks",
        "section_texts",
    ),
    "figure_decision_values": (
        "review_pending",
        "insert",
        "placeholder",
        "low_priority",
        "visual_defect",
        "dropped",
        "skip",
    ),
    "usable_insert_candidate": {
        "kinds": ("figure", "table"),
        "visual_quality_status": "usable_candidate",
        "requires_source_image_path": True,
    },
    "allowed_usable_placeholder_reasons": (
        "visual_defect",
        "materialization_blocked",
    ),
    "manual_visual_review_required_statuses": (
        "usable_candidate",
        "needs_visual_quality_check",
        "review",
    ),
    "automatic_fail_closed_visual_statuses": (
        "reject_visual_quality",
        "asset_candidate_missing",
    ),
    "visual_review_contract": {
        "selected_render_dpi": 300,
        "page_preview_dpi": 96,
        "review_fields": (
            "status",
            "reviewed_asset_sha256",
            "preserved_scientific_elements",
            "omitted_scientific_elements",
            "notes",
            "failure_reason",
            "repair_attempts",
            "revised_bbox",
        ),
        "review_status_values": ("pending", "pass", "fail", "repair_requested", "dropped"),
        "repair_limit": 1,
        "asset_sha256_bound": True,
        "caption_free_visual_body_required": True,
        "decision_freeze_before": "note_plan",
        "review_evidence_fields": (
            "candidate_path",
            "page_preview_path",
            "source_pdf_path",
            "source_page",
            "caption",
            "bbox_pt",
            "normalized_bbox",
            "render_dpi",
        ),
        "repairable_failure_reasons": (
            "caption_contamination",
            "surrounding_prose_contamination",
            "scientific_content_clipped",
            "insufficient_safety_margin",
        ),
        "terminal_failure_reasons": (
            "identity_mismatch",
            "caption_inseparable",
            "ambiguous_visual_body",
            "unreadable_source",
            "scientific_content_missing",
            "repair_limit_exhausted",
        ),
    },
    "note_plan_depth_requirements": {
        "required_section_focus_min_chars": 20,
        "required_section_focus_fields": ("focus", "reading_goal", "purpose"),
        "generic_focus_phrases": (
            "use the raw source to explain",
            "paper-specific role of",
            "explain the paper-specific role",
            "explain this section",
            "summarize this section",
        ),
    },
    "frontmatter_contract": {
        "required_fields": ("paper_type", "methods", "datasets", "tasks", "read_date"),
        "list_fields": ("methods", "datasets", "tasks"),
        "max_list_items": 5,
        "domain_tag_prefix": "papers/",
        "read_date_format": "YYYY-MM-DD",
        "paper_type_source": "note_plan.paper_type",
        # A list value naming a listed glossary term is written as that term's link.
        "term_link_source": "glossary_terms",
        "term_link_fields": ("methods", "datasets", "tasks"),
    },
    "connections_contract": {
        "plan_fields": ("connections", "key_prior_work"),
        "connection_fields": ("target", "relation", "reason"),
        "key_prior_work_fields": ("work", "role"),
        "relations": (
            "baseline", "extends", "extended_by", "conflicting_findings",
            "same_task", "same_benchmark", "shared_method",
        ),
        "max_in_vault": 8,
        "key_prior_work_items": {"min": 3, "max": 5},
        "candidate_source": "connection_candidates",
        "followup_papers_must_appear_in_connections": True,
    },
    "takeaways_contract": {
        "plan_fields": TAKEAWAY_PLAN_FIELDS,
        "min_items": 1,
        "max_items": 2,
        "min_item_chars": 20,
        "reader_context_field": "reader_research_direction",
        # Used when the request names no direction: the user's confirmed research memory.
        "reader_context_fallback": "research_memory.suggested_reader_research_direction",
    },
    "storyline_contract": {
        "plan_field": "storyline",
        "sentences": STORYLINE_SENTENCE_RANGE,
        "role": "writing_outline_and_review_basis_not_note_text",
    },
    "type_structure_contract": {
        "plan_fields": tuple(NOTE_PLAN_TYPE_FIELDS),
        "middle_sections_source": "contracts_by_paper_type[note_plan.paper_type].middle_sections",
        "core_answer_forms": ({"answer": "string", "evidence_refs": "array"}, {"not_reported": True, "reason": "string"}),
        "secondary_question_limit": SECONDARY_QUESTION_LIMIT,
        "workflow_step_range": WORKFLOW_STEP_RANGE,
        "weak_evidence_rule": "more_than_half_of_primary_core_questions_not_reported",
    },
    "analysis_coverage_contract": {
        "central_claim_fields": tuple(CENTRAL_CLAIM_FIELD_TYPES),
        "central_claim_field_types": CENTRAL_CLAIM_FIELD_TYPES,
        "central_claim_required_field_checks": REQUIRED_FIELD_CHECKS,
        "required_plan_fields": (
            "central_claims",
            "claim_boundaries",
            "negative_or_limiting_results",
            "mechanism_result_map",
            "comparative_positioning",
            "reuse_takeaways",
            "followup_questions",
        ),
    },
}

def writing_contract_rules(language: str | None = None) -> dict[str, Any]:
    resolved = normalize_output_language(language)
    schema = note_schema(resolved)
    rules = deepcopy(WRITING_CONTRACT_RULES)
    rules["language"] = resolved
    rules["fixed_head_sections"] = tuple(schema["sections"][key] for key in HEAD_SECTION_KEYS)
    rules["fixed_tail_sections"] = tuple(schema["sections"][key] for key in TAIL_SECTION_KEYS)
    rules["limitations_section"] = schema["sections"]["limitations"]
    rules["weak_evidence_callout"] = WEAK_EVIDENCE_CALLOUT[resolved]
    rules["not_reported_phrase"] = NOT_REPORTED_PHRASE[resolved]
    rules["core_info_fields"] = tuple(schema["core_info_fields"])
    rules["figure_labels"] = dict(schema["figure_labels"])
    rules["takeaways_contract"]["section"] = schema["sections"]["takeaways"]
    rules["takeaways_contract"]["subsections"] = tuple(schema["takeaways_subsections"].values())
    rules["takeaways_contract"]["judgment_marker"] = schema["takeaways_judgment_marker"]
    rules["takeaways_contract"]["max_item_chars"] = schema["takeaways_max_item_chars"]
    connections = rules["connections_contract"]
    connections["section"] = schema["sections"]["connections"]
    connections["subsections"] = tuple(schema["connections_subsections"].values())
    connections["relation_labels"] = {
        key: schema["connections_relation_labels"][key] for key in connections["relations"]
    }
    connections["empty_statements"] = dict(schema["connections_empty_statements"])
    connections["in_vault_entry_format"] = (
        "- [[target|标题]]（关系）：理由" if resolved == "zh-CN" else "- [[target|Title]] (relation): reason"
    )
    connections["key_prior_work_entry_format"] = (
        "- 作者 年份. 标题（角色）" if resolved == "zh-CN" else "- Author Year. Title (role)"
    )
    rules["my_notes_contract"] = {
        "section": schema["sections"]["my_notes"],
        "guidance": schema["my_notes_guidance"],
        "position": "last",
        "user_owned": True,
    }
    if schema.get("abstract_contract"):
        rules["abstract_contract"] = deepcopy(schema["abstract_contract"])
    return rules


def compact_text_length(value: str) -> int:
    return sum(1 for ch in value if not ch.isspace())


def takeaway_plan_issues(note_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Check the plan fields that feed the Takeaways section and the optional reader context."""
    contract = WRITING_CONTRACT_RULES["takeaways_contract"]
    generic = WRITING_CONTRACT_RULES["note_plan_depth_requirements"]["generic_focus_phrases"]
    issues: list[dict[str, Any]] = []
    for field in contract["plan_fields"]:
        items = note_plan.get(field)
        if not isinstance(items, list) or not items:
            continue  # missing or empty lists are reported by the required-field checks
        if not contract["min_items"] <= len(items) <= contract["max_items"]:
            issues.append({"code": "note_plan_takeaway_item_count_invalid", "field": field, "count": len(items)})
        for index, item in enumerate(items):
            if not isinstance(item, str):
                issues.append({"code": "note_plan_takeaway_item_invalid", "field": field, "index": index})
                continue
            lowered = " ".join(item.split()).lower()
            if compact_text_length(item) < contract["min_item_chars"] or any(
                phrase in lowered for phrase in generic
            ):
                issues.append({"code": "note_plan_takeaway_item_too_thin", "field": field, "index": index})
    reader_field = contract["reader_context_field"]
    if reader_field in note_plan and not isinstance(note_plan[reader_field], str):
        issues.append({"code": "note_plan_reader_research_direction_invalid", "field": reader_field})
    return issues


def storyline_sentence_count(text: str) -> int:
    cleaned = _NON_TERMINAL_ABBREVIATIONS.sub("", text)
    return sum(1 for part in _SENTENCE_END.split(cleaned) if part.strip())


def storyline_plan_issues(note_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The storyline is 3 to 5 sentences (an empty one is reported as a missing required field)."""
    value = note_plan.get("storyline")
    if not isinstance(value, str) or not value.strip():
        return []
    low, high = STORYLINE_SENTENCE_RANGE
    count = storyline_sentence_count(value)
    if not low <= count <= high:
        return [{"code": "note_plan_storyline_sentence_count_invalid", "field": "storyline", "count": count}]
    return []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def core_answer_form(value: Any) -> str:
    """`answer`, `not_reported`, or `invalid` for one core_answers entry."""
    if not isinstance(value, dict):
        return "invalid"
    if set(value) == {"answer", "evidence_refs"} and _text(value["answer"]) and isinstance(value["evidence_refs"], list) and value["evidence_refs"]:
        return "answer"
    if set(value) == {"not_reported", "reason"} and value["not_reported"] is True and _text(value["reason"]):
        return "not_reported"
    return "invalid"


def weak_evidence_question_ids(note_plan: dict[str, Any]) -> list[str]:
    """The primary type's unreported questions, when they are more than half of its questions."""
    paper_type = _text(note_plan.get("paper_type"))
    answers = note_plan.get("core_answers")
    ids = question_ids(paper_type)
    if not ids or not isinstance(answers, dict):
        return []
    unreported = [qid for qid in ids if core_answer_form(answers.get(qid)) == "not_reported"]
    return unreported if len(unreported) * 2 > len(ids) else []


def type_plan_issues(note_plan: dict[str, Any], language: str | None = None) -> list[dict[str, Any]]:
    """Check the type-dependent plan fields against the paper type's profile (shape only)."""
    resolved = normalize_output_language(language)
    paper_type = _text(note_plan.get("paper_type"))
    found = PROFILES.get(paper_type)
    if found is None:
        return []  # an unknown paper_type is reported by the paper_type check
    issues: list[dict[str, Any]] = []
    enums = found.get("plan_enums", {})
    for field in ("positioning", "survey_mode"):
        value = note_plan.get(field, "")
        if field in enums:
            if value not in enums[field]:
                issues.append({"code": f"note_plan_{field}_invalid", "field": field, "allowed": list(enums[field])})
        elif value not in ("", None):
            issues.append({"code": f"note_plan_{field}_not_applicable", "field": field})

    secondary = _text(note_plan.get("secondary_type"))
    host = _text(note_plan.get("secondary_host_section"))
    if secondary:
        if secondary not in PROFILES or secondary == paper_type:
            issues.append({"code": "note_plan_secondary_type_invalid", "field": "secondary_type"})
            secondary = ""
        elif host not in middle_sections(paper_type, resolved):
            issues.append({"code": "note_plan_secondary_host_section_invalid", "field": "secondary_host_section"})
    elif host:
        issues.append({"code": "note_plan_secondary_host_section_not_applicable", "field": "secondary_host_section"})

    answers = note_plan.get("core_answers")
    required = required_question_ids(paper_type, secondary)
    if not isinstance(answers, dict):
        issues.append({"code": "note_plan_core_answers_invalid", "field": "core_answers"})
    else:
        for qid in required:
            if qid not in answers:
                issues.append({"code": "note_plan_core_answer_missing", "field": "core_answers", "question": qid})
            elif core_answer_form(answers[qid]) == "invalid":
                issues.append({"code": "note_plan_core_answer_invalid", "field": "core_answers", "question": qid})
        for qid in sorted(set(answers) - set(required)):
            issues.append({"code": "note_plan_core_answer_unexpected", "field": "core_answers", "question": qid})

    issues.extend(_workflow_plan_issues(note_plan.get("workflow", []), found["workflow"]))
    return issues


def _workflow_plan_issues(flows: Any, contract: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(flows, list):
        return [{"code": "note_plan_workflow_invalid", "field": "workflow"}]
    if contract is None:
        return [{"code": "note_plan_workflow_not_applicable", "field": "workflow"}] if flows else []
    if not flows:
        return [] if contract["may_be_unreported"] else [{"code": "note_plan_workflow_missing", "field": "workflow"}]
    issues: list[dict[str, Any]] = []
    low, high = WORKFLOW_STEP_RANGE
    for index, flow in enumerate(flows):
        steps = flow.get("steps") if isinstance(flow, dict) else None
        if not isinstance(flow, dict) or not _text(flow.get("name")) or not isinstance(steps, list):
            issues.append({"code": "note_plan_workflow_flow_invalid", "field": "workflow", "index": index})
            continue
        if not low <= len(steps) <= high:
            issues.append({"code": "note_plan_workflow_step_count_invalid", "field": "workflow", "index": index, "count": len(steps)})
        for step_index, step in enumerate(steps):
            if not _workflow_step_valid(step, contract["step_fields"]):
                issues.append({"code": "note_plan_workflow_step_invalid", "field": "workflow", "index": index, "step": step_index})
    return issues


def _workflow_step_valid(step: Any, fields: tuple[str, ...]) -> bool:
    if not isinstance(step, dict) or set(step) != set(fields):
        return False
    return all(
        isinstance(step[field], bool) if field == "novel" else bool(_text(step[field]))
        for field in fields
    )


def connection_plan_issues(note_plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Check the plan fields that feed the Connections section (shape only, not targets)."""
    contract = WRITING_CONTRACT_RULES["connections_contract"]
    issues: list[dict[str, Any]] = []
    prior = note_plan.get("key_prior_work")
    if isinstance(prior, list) and prior:
        limits = contract["key_prior_work_items"]
        if not limits["min"] <= len(prior) <= limits["max"]:
            issues.append({"code": "note_plan_key_prior_work_count_invalid", "field": "key_prior_work", "count": len(prior)})
        for index, item in enumerate(prior):
            if not _filled_object(item, contract["key_prior_work_fields"]):
                issues.append({"code": "note_plan_key_prior_work_item_invalid", "field": "key_prior_work", "index": index})
    if "connections" not in note_plan:
        return issues
    connections = note_plan["connections"]
    if not isinstance(connections, list):
        return issues + [{"code": "note_plan_connections_invalid", "field": "connections"}]
    if len(connections) > contract["max_in_vault"]:
        issues.append({"code": "note_plan_connections_count_invalid", "field": "connections", "count": len(connections)})
    seen: set[str] = set()
    for index, item in enumerate(connections):
        if not _filled_object(item, contract["connection_fields"]):
            issues.append({"code": "note_plan_connection_item_invalid", "field": "connections", "index": index})
            continue
        if item["relation"] not in contract["relations"]:
            issues.append({"code": "note_plan_connection_relation_invalid", "field": "connections", "index": index})
        if item["target"] in seen:
            issues.append({"code": "note_plan_connection_duplicate", "field": "connections", "index": index})
        seen.add(item["target"])
    return issues


def connection_target_issues(note_plan: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Every planned connection must link to a note the bundle recalled."""
    connections = note_plan.get("connections")
    if not isinstance(connections, list) or not connections:
        return []
    recalled = bundle.get("connection_candidates")
    known: set[str] = set()
    if isinstance(recalled, dict):
        for group in ("cited", "related"):
            for candidate in recalled.get(group) or []:
                if isinstance(candidate, dict) and isinstance(candidate.get("target"), str):
                    known.add(candidate["target"])
    return [
        {"code": "note_plan_connection_target_unknown", "field": "connections", "index": index, "target": item["target"]}
        for index, item in enumerate(connections)
        if isinstance(item, dict) and isinstance(item.get("target"), str) and item["target"] not in known
    ]


def _filled_object(item: object, fields: tuple[str, ...]) -> bool:
    return isinstance(item, dict) and set(item) == set(fields) and all(
        isinstance(item[field], str) and item[field].strip() for field in fields
    )


class MetadataRecord(TypedDict, total=False):
    title: str
    translated_title: str
    paper_id: str
    source_type: str
    source_url: str
    year: str
    authors: list[str]
    affiliations: list[str]
    venue: str
    doi: str
    abstract: str
    code_url: str
    project_url: str
    zotero_key: str
    arxiv_id: str
    metadata_sources: list[str]
    identity_confidence: str
    identity_confidence_reasons: list[str]


class EvidenceItem(TypedDict, total=False):
    claim: str
    evidence: str
    source_section: str
    page_hint: str


class CandidateChunk(TypedDict, total=False):
    text: str
    source_section: str
    actual_source_section: str
    is_abstract_fallback: bool
    page_hint: str
    kind_hint: str


class EquationCandidate(TypedDict, total=False):
    equation: str
    source_section: str
    kind_hint: str


class ReferenceCandidate(TypedDict, total=False):
    raw_text: str
    display_text: str
    page_hint: str
    doi: str
    arxiv_id: str
    wikilink: str
    vault_target: str
    match_status: str
    match_reason: str


class FigureQualitySignals(TypedDict, total=False):
    visual_quality_status: str
    quality_reason_codes: list[str]
    page_coverage_ratio: float
    visual_rect_count: int
    visual_body_ratio: float
    paragraph_text_chars: int
    table_body_rows: int
    caption_text_chars: int


class FigureAssetCandidate(TypedDict, total=False):
    filename: str
    path: str
    width: int
    height: int
    size_bytes: int
    label: str
    extraction_level: str
    quality_signals: FigureQualitySignals
    candidate_status: str


class SectionExtractionCoverage(TypedDict, total=False):
    coverage_status: str
    recognized_sections: list[str]
    core_sections_found: list[str]
    missing_core_sections: list[str]
    section_text_chars: dict[str, int]
    fallback_sections: list[str]


class PdfCoverage(TypedDict, total=False):
    total_pages: int | None
    text_max_pages: int | None
    text_pages_scanned: int
    truncated_due_to_page_limit: bool
    appendix_detected: bool
    appendix_start_page: int | None
    references_start_page: int | None
    section_stop_reason: str
    section_stop_page: int | None


class AppendixIndex(TypedDict, total=False):
    appendix_detected: bool
    start_page: int | None
    sections: list[dict[str, Any]]
    figure_captions: list[dict[str, Any]]
    table_captions: list[dict[str, Any]]


class AppendixEvidenceItem(TypedDict, total=False):
    evidence: str
    source_section: str
    page_hint: str
    kind_hint: str


class EvidencePack(TypedDict, total=False):
    paper_id: str
    problem_evidence: list[EvidenceItem]
    task_evidence: list[EvidenceItem]
    data_evidence: list[EvidenceItem]
    method_evidence: list[EvidenceItem]
    mechanism_evidence: list[EvidenceItem]
    results_evidence: list[EvidenceItem]
    ablation_evidence: list[EvidenceItem]
    limitations_evidence: list[EvidenceItem]
    equation_candidates: list[EquationCandidate]
    reference_candidates: list[ReferenceCandidate]
    figure_captions: list[dict[str, Any]]
    table_captions: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    section_texts: dict[str, str]
    candidate_chunks: dict[str, list[CandidateChunk]]
    language_hint: str
    section_sources: dict[str, str]
    section_extraction_coverage: SectionExtractionCoverage
    pdf_coverage: PdfCoverage
    appendix_index: AppendixIndex
    appendix_evidence: dict[str, list[AppendixEvidenceItem]]
    quotes: list[dict[str, Any]]
    evidence_quality: str
    extraction_failures: list[str]


class FigurePlanItem(TypedDict, total=False):
    id: str
    caption: str
    kind: str
    section: str
    reason: str
    priority: int
    anchor_text: str
    insert_mode: str
    figure_asset_candidate: FigureAssetCandidate
    candidate_pages: list[dict[str, Any]]
    candidate_status: str
    matching_strategy: str


class FigurePlan(TypedDict, total=False):
    paper_id: str
    figures: list[FigurePlanItem]


class SynthesisBundle(TypedDict, total=False):
    paper_id: str
    title: str
    metadata: dict[str, Any]
    evidence_quality: str
    coverage: dict[str, Any]
    source_manifest: dict[str, Any]
    source_index: dict[str, Any]
    references: dict[str, Any]
    figure_table_manifest: dict[str, Any]
    writing_contract: dict[str, Any]


def empty_metadata() -> MetadataRecord:
    return MetadataRecord(
        title="",
        paper_id="",
        source_type="",
        source_url="",
        year="",
        authors=[],
        affiliations=[],
        metadata_sources=[],
        identity_confidence="",
        identity_confidence_reasons=[],
    )


def empty_evidence_pack() -> EvidencePack:
    return EvidencePack(
        paper_id="",
        problem_evidence=[],
        task_evidence=[],
        data_evidence=[],
        method_evidence=[],
        mechanism_evidence=[],
        results_evidence=[],
        ablation_evidence=[],
        limitations_evidence=[],
        equation_candidates=[],
        reference_candidates=[],
        figure_captions=[],
        table_captions=[],
        sections=[],
        section_texts={},
        candidate_chunks={},
        language_hint="unknown",
        section_sources={},
        section_extraction_coverage={},
        pdf_coverage={},
        appendix_index={},
        appendix_evidence={},
        quotes=[],
        extraction_failures=[],
        evidence_quality="unknown",
    )


def empty_figure_plan() -> FigurePlan:
    return FigurePlan(paper_id="", figures=[])


def empty_synthesis_bundle() -> SynthesisBundle:
    return SynthesisBundle(
        paper_id="",
        title="",
        metadata={},
        evidence_quality="unknown",
        coverage={},
        source_manifest={},
        source_index={},
        references={},
        figure_table_manifest={},
        writing_contract={},
    )
