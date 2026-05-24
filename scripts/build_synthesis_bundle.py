#!/usr/bin/env python3
"""Assemble a model-facing synthesis bundle from deterministic DeepPaperNote artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from citation_links import resolve_reference_links
from common import maybe_load_json_record, normalize_whitespace, runtime_config
from contracts import (
    NOTE_PLAN_REQUIRED_FIELDS,
    NOTE_REQUIRED_SECTIONS,
    PAPER_TYPE_CONTRACTS,
    PAPER_TYPE_VALUES,
    WRITING_CONTRACT_RULES,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "build synthesis bundle")
    p.add_argument("--metadata", required=True, help="Metadata JSON path or string.")
    p.add_argument("--evidence", required=True, help="Evidence JSON path or string.")
    p.add_argument("--figures", default="", help="Figure plan JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument("--source-manifest", required=True, help="Source manifest JSON path or string.")
    p.add_argument(
        "--figure-decisions",
        required=True,
        help="Figure/table decision JSON path or string.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def load_record(value: str) -> dict:
    return maybe_load_json_record(value) or {}


def sanitize_reference_candidates(evidence_pack: dict, *, limit: int = 20) -> list[dict]:
    candidates = evidence_pack.get("reference_candidates", []) or []
    if not isinstance(candidates, list):
        return []
    try:
        matched_candidates = resolve_reference_links(candidates[:limit], runtime_config())
    except Exception:
        matched_candidates = [
            {
                **candidate,
                "wikilink": "",
                "vault_target": "",
                "match_status": "vault_unavailable",
                "match_reason": "none",
            }
            for candidate in candidates[:limit]
            if isinstance(candidate, dict)
        ]

    sanitized: list[dict] = []
    for item in matched_candidates:
        if not isinstance(item, dict):
            continue
        raw_text = normalize_whitespace(str(item.get("raw_text", "")))
        display_text = normalize_whitespace(str(item.get("display_text", "")))
        if not raw_text and not display_text:
            continue
        sanitized.append(
            {
                "raw_text": raw_text,
                "display_text": display_text,
                "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
                "doi": normalize_whitespace(str(item.get("doi", ""))),
                "arxiv_id": normalize_whitespace(str(item.get("arxiv_id", ""))),
                "wikilink": normalize_whitespace(str(item.get("wikilink", ""))),
                "vault_target": normalize_whitespace(str(item.get("vault_target", ""))),
                "match_status": normalize_whitespace(
                    str(item.get("match_status", "no_vault_match"))
                ),
                "match_reason": normalize_whitespace(str(item.get("match_reason", "none"))),
            }
        )
    return sanitized


def figure_quality_summary(assets_wrapper: dict) -> dict[str, int]:
    summary = {"usable": 0, "review": 0, "reject": 0, "unknown": 0}
    for item in assets_wrapper.get("figure_assets", []) or []:
        if not isinstance(item, dict):
            summary["unknown"] += 1
            continue
        quality_signals = item.get("quality_signals", {})
        if not isinstance(quality_signals, dict):
            summary["unknown"] += 1
            continue
        status = normalize_whitespace(str(quality_signals.get("visual_quality_status", ""))).lower()
        if status == "needs_review":
            status = "review"
        if status not in summary:
            status = "unknown"
        summary[status] += 1
    return summary


def truncation_warnings(source_coverage: dict, asset_coverage: dict) -> list[str]:
    warnings: list[str] = []
    if source_coverage.get("text_truncated") or source_coverage.get("truncated_due_to_page_limit"):
        warnings.append("source_text_truncated")
    if asset_coverage.get("truncated_due_to_asset_page_limit"):
        warnings.append("asset_page_limit")
    return warnings


def coverage_summary(
    evidence_pack: dict,
    metadata: dict | None = None,
    assets_wrapper: dict | None = None,
    source_manifest: dict | None = None,
) -> dict:
    metadata = metadata or {}
    assets_wrapper = assets_wrapper or {}
    source_manifest = source_manifest or {}
    pdf_coverage = evidence_pack.get("pdf_coverage", {}) or {}
    asset_coverage = assets_wrapper.get("asset_coverage", {}) or {}
    source_coverage = (
        source_manifest.get("coverage", {})
        if isinstance(source_manifest.get("coverage"), dict)
        else {}
    )
    if not source_coverage and isinstance(source_manifest.get("pdf"), dict):
        pdf = source_manifest.get("pdf", {})
        source_coverage = {
            "total_pages": pdf.get("total_pages"),
            "text_max_pages": pdf.get("text_max_pages"),
            "text_pages_extracted": pdf.get("text_pages_extracted"),
            "text_truncated": pdf.get("text_truncated"),
        }
    return {
        "language_hint": source_manifest.get("language_hint")
        or evidence_pack.get("language_hint", "unknown"),
        "section_extraction_coverage": evidence_pack.get("section_extraction_coverage", {}) or {},
        "pdf_coverage": pdf_coverage,
        "source_coverage": source_coverage,
        "source_manifest": {
            "raw_sections_path": source_manifest.get("raw_sections_path", ""),
            "full_text_md_path": source_manifest.get("full_text_md_path", ""),
            "section_count": len(source_manifest.get("sections", []) or []),
            "page_count": len(source_manifest.get("pages", []) or []),
            "text_hash_sha256": source_manifest.get("text_hash_sha256", ""),
        },
        "appendix_evidence_counts": appendix_evidence_counts(evidence_pack),
        "extraction_failures": evidence_pack.get("extraction_failures", []) or [],
        "asset_coverage": asset_coverage if isinstance(asset_coverage, dict) else {},
        "figure_quality_summary": figure_quality_summary(assets_wrapper),
        "truncation_warnings": truncation_warnings(
            source_coverage if isinstance(source_coverage, dict) else {},
            asset_coverage if isinstance(asset_coverage, dict) else {},
        ),
        "identity_confidence": metadata.get("identity_confidence", ""),
        "identity_confidence_reasons": metadata.get("identity_confidence_reasons", []) or [],
    }


def appendix_evidence_counts(evidence_pack: dict) -> dict[str, int]:
    appendix_evidence = evidence_pack.get("appendix_evidence", {}) or {}
    if not isinstance(appendix_evidence, dict):
        return {}
    return {
        normalize_whitespace(str(category)): len(items)
        for category, items in appendix_evidence.items()
        if isinstance(items, list)
    }


def sanitize_page_assets(assets_wrapper: dict, *, limit: int = 24) -> list[dict]:
    sanitized: list[dict] = []
    for item in (assets_wrapper.get("page_assets", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "page_number": item.get("page_number", 0),
                "searchable_text_chars": item.get("searchable_text_chars", 0),
                "text_extraction_method": item.get("text_extraction_method", ""),
                "ocr_used": item.get("ocr_used", False),
                "image_count": item.get("image_count", 0),
                "text_preview": item.get("text_preview", ""),
            }
        )
    return sanitized


def sanitize_figure_assets(assets_wrapper: dict, *, limit: int = 48) -> list[dict]:
    sanitized: list[dict] = []
    for item in (assets_wrapper.get("figure_assets", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        record = {
            "filename": item.get("filename", ""),
            "path": item.get("path", ""),
            "page_number": item.get("page_number", 0),
            "label": item.get("label", ""),
            "kind": item.get("kind", ""),
            "caption_text": normalize_whitespace(str(item.get("caption_text", ""))),
            "width": item.get("width", 0),
            "height": item.get("height", 0),
            "size_bytes": item.get("size_bytes", 0),
            "extraction_level": item.get("extraction_level", ""),
        }
        if isinstance(item.get("quality_signals"), dict):
            record["quality_signals"] = item.get("quality_signals")
        sanitized.append(record)
    return sanitized


def source_index(source_manifest: dict) -> dict:
    if not isinstance(source_manifest, dict):
        return {}
    return {
        "raw_sections_path": source_manifest.get("raw_sections_path", ""),
        "full_text_md_path": source_manifest.get("full_text_md_path", ""),
        "sections": source_manifest.get("sections", []) or [],
        "pages": source_manifest.get("pages", []) or [],
        "captions": source_manifest.get("captions", {}) or {},
        "math_index": source_manifest.get("math_index", []) or [],
        "appendix_index": source_manifest.get("appendix_index", {}) or {},
        "language_hint": source_manifest.get("language_hint", "unknown"),
        "text_hash_sha256": source_manifest.get("text_hash_sha256", ""),
    }


def figure_table_manifest(
    figure_decisions_wrapper: dict,
    source_manifest: dict,
    figure_plan: dict,
) -> dict:
    decisions = (
        figure_decisions_wrapper.get("decisions", [])
        if isinstance(figure_decisions_wrapper, dict)
        else []
    )
    if not isinstance(decisions, list):
        decisions = []
    captions = (
        source_manifest.get("captions", {})
        if isinstance(source_manifest.get("captions"), dict)
        else {}
    )
    decisions_path = (
        figure_decisions_wrapper.get("decisions_path", "")
        if isinstance(figure_decisions_wrapper, dict)
        else ""
    )
    planned_items = (
        len(figure_plan.get("figures", []) or []) if isinstance(figure_plan, dict) else 0
    )
    return {
        "decisions_path": decisions_path,
        "decisions": decisions,
        "caption_counts": {
            "figures": len(captions.get("figures", []) or []),
            "tables": len(captions.get("tables", []) or []),
        },
        "planned_items": planned_items,
        "requires_full_decision_table": True,
    }


def compact_writing_contract() -> dict:
    depth_requirements = dict(WRITING_CONTRACT_RULES["note_plan_depth_requirements"])
    depth_requirements["required_section_focus_fields"] = list(
        depth_requirements["required_section_focus_fields"]
    )
    depth_requirements["generic_focus_phrases"] = list(
        depth_requirements["generic_focus_phrases"]
    )
    usable_insert_candidate = dict(WRITING_CONTRACT_RULES["usable_insert_candidate"])
    usable_insert_candidate["kinds"] = list(usable_insert_candidate["kinds"])
    analysis_coverage = dict(WRITING_CONTRACT_RULES["analysis_coverage_contract"])
    analysis_coverage["central_claim_fields"] = list(
        analysis_coverage["central_claim_fields"]
    )
    analysis_coverage["required_plan_fields"] = list(
        analysis_coverage["required_plan_fields"]
    )
    analysis_coverage["final_quality_review_checks"] = list(
        analysis_coverage["final_quality_review_checks"]
    )
    return {
        "language": "zh-CN",
        "contract_role": "manifest_quality_contract",
        "canonical_source": (
            "SKILL.md defines the workflow; scripts/contracts.py defines "
            "machine-checkable contract data."
        ),
        "must_include_sections": list(NOTE_REQUIRED_SECTIONS),
        "note_plan_contract": {
            "required_fields": list(NOTE_PLAN_REQUIRED_FIELDS),
            "artifact_preference": "short_json_planning_file",
            "grounding_field": "section_plan[*].evidence_sources",
            "analysis_coverage_field": "central_claims[*]",
        },
        "paper_type_selection": {
            "source_of_truth": "note_plan.paper_type",
            "suggested_paper_type_role": "none",
            "allowed_paper_types": list(PAPER_TYPE_VALUES),
        },
        "contracts_by_paper_type": PAPER_TYPE_CONTRACTS,
        "grounding_contract": {
            "source_of_truth": "source_manifest",
            "accepted_reference_forms": list(
                WRITING_CONTRACT_RULES["allowed_grounding_reference_forms"]
            ),
            "required_sections": list(WRITING_CONTRACT_RULES["grounding_required_sections"]),
            "note_plan_depth_requirements": depth_requirements,
            "reject_old_references": list(WRITING_CONTRACT_RULES["old_bundle_reference_prefixes"]),
            "lint_command": (
                "scripts/lint_grounding.py --note-plan ... "
                "--source-manifest ... --bundle-json ..."
            ),
        },
        "figure_table_contract": {
            "placeholder_first": True,
            "visual_quality_gate": "fail_closed",
            "decision_table_required": True,
            "decision_values": list(WRITING_CONTRACT_RULES["figure_decision_values"]),
            "usable_insert_candidate": usable_insert_candidate,
            "allowed_usable_placeholder_reasons": list(
                WRITING_CONTRACT_RULES["allowed_usable_placeholder_reasons"]
            ),
            "manual_visual_review_required_statuses": list(
                WRITING_CONTRACT_RULES["manual_visual_review_required_statuses"]
            ),
            "automatic_fail_closed_visual_statuses": list(
                WRITING_CONTRACT_RULES["automatic_fail_closed_visual_statuses"]
            ),
            "manual_review_claim_requires_image_inspection": True,
        },
        "analysis_coverage_contract": analysis_coverage,
    }


def bundle(
    metadata: dict,
    evidence_wrapper: dict,
    figures_wrapper: dict,
    assets_wrapper: dict,
    source_manifest: dict | None = None,
    figure_decisions_wrapper: dict | None = None,
) -> dict:
    evidence_pack = (
        evidence_wrapper.get("evidence_pack", {})
        if isinstance(evidence_wrapper.get("evidence_pack"), dict)
        else {}
    )
    figure_plan = (
        figures_wrapper.get("figure_plan", {})
        if isinstance(figures_wrapper.get("figure_plan"), dict)
        else {}
    )
    source_manifest = source_manifest or {}
    figure_decisions_wrapper = figure_decisions_wrapper or {}

    return {
        "status": "ok",
        "script": "build_synthesis_bundle.py",
        "paper_id": metadata.get("paper_id") or evidence_wrapper.get("paper_id", ""),
        "title": metadata.get("title") or evidence_wrapper.get("title", ""),
        "metadata": {
            "title": metadata.get("title", ""),
            "translated_title": metadata.get("translated_title", ""),
            "authors": metadata.get("authors", []),
            "affiliations": metadata.get("affiliations", []),
            "year": metadata.get("year", ""),
            "venue": metadata.get("venue", ""),
            "doi": metadata.get("doi", ""),
            "source_url": metadata.get("source_url", ""),
            "abstract": metadata.get("abstract", ""),
            "arxiv_id": metadata.get("arxiv_id", ""),
            "zotero_key": metadata.get("zotero_key", ""),
            "metadata_sources": metadata.get("metadata_sources", []),
            "identity_confidence": metadata.get("identity_confidence", ""),
            "identity_confidence_reasons": metadata.get("identity_confidence_reasons", []) or [],
        },
        "evidence_quality": evidence_pack.get("evidence_quality", "unknown"),
        "coverage": coverage_summary(evidence_pack, metadata, assets_wrapper, source_manifest),
        "source_manifest": {
            "paper_id": source_manifest.get("paper_id", ""),
            "title": source_manifest.get("title", ""),
            "source_kind": source_manifest.get("source_kind", ""),
            "raw_sections_path": source_manifest.get("raw_sections_path", ""),
            "full_text_md_path": source_manifest.get("full_text_md_path", ""),
            "pdf": source_manifest.get("pdf", {}) or {},
            "coverage": source_manifest.get("coverage", {}) or {},
        },
        "source_index": source_index(source_manifest),
        "references": {"candidates": sanitize_reference_candidates(evidence_pack)},
        "figure_plan": figure_plan,
        "figure_table_manifest": figure_table_manifest(
            figure_decisions_wrapper,
            source_manifest,
            figure_plan,
        ),
        "pdf_assets": {
            "asset_root": assets_wrapper.get("asset_root", ""),
            "images_dir": assets_wrapper.get("images_dir", ""),
            "page_assets": sanitize_page_assets(assets_wrapper),
            "image_assets": assets_wrapper.get("image_assets", []),
            "figure_assets": sanitize_figure_assets(assets_wrapper),
            "ocr_available": assets_wrapper.get("ocr_available", False),
        },
        "writing_contract": compact_writing_contract(),
    }


def main() -> None:
    from common import emit

    args = parser().parse_args()
    metadata = load_record(args.metadata)
    evidence = load_record(args.evidence)
    figures = load_record(args.figures) if args.figures else {}
    assets = load_record(args.assets) if args.assets else {}
    source_manifest = load_record(args.source_manifest) if args.source_manifest else {}
    figure_decisions = load_record(args.figure_decisions) if args.figure_decisions else {}
    if args.figure_decisions and isinstance(figure_decisions, dict):
        decision_path = Path(args.figure_decisions).expanduser()
        if decision_path.exists():
            figure_decisions.setdefault("decisions_path", str(decision_path.resolve()))
    emit(
        bundle(metadata, evidence, figures, assets, source_manifest, figure_decisions),
        args.output,
    )


if __name__ == "__main__":
    main()
