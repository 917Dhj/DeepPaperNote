from __future__ import annotations

import json

import pytest

from build_synthesis_bundle import bundle as build_bundle
from contracts import WRITING_CONTRACT_RULES


def accepted_source_manifest() -> dict:
    return {
        "paper_id": "paper:contract",
        "identity_contract": {
            "artifact_type": "canonical_identity",
            "schema_version": 2,
            "paper_id": "paper:contract",
            "identity_verdict": "accepted",
            "work_level_identity": {"title": "Contract Paper"},
            "accepted_metadata": {"title": "Contract Paper"},
        },
    }


def bundle(*args: object, **kwargs: object) -> dict:
    if not kwargs.get("figures_wrapper"):
        kwargs["figures_wrapper"] = {"output_language": "zh-CN", "figure_plan": {}}
    if not kwargs.get("figure_decisions_wrapper"):
        kwargs["figure_decisions_wrapper"] = {"output_language": "zh-CN", "decisions": []}
    return build_bundle(*args, **kwargs)


def test_bundle_rejects_mismatched_adjacent_artifact_language() -> None:
    with pytest.raises(
        ValueError,
        match="Figure Plan output_language en does not match resolved output_language zh-CN",
    ):
        bundle(
            metadata={"title": "Contract Paper"},
            evidence_wrapper={"evidence_pack": {}},
            figures_wrapper={"output_language": "en", "figure_plan": {}},
            assets_wrapper={},
            source_manifest=accepted_source_manifest(),
            figure_decisions_wrapper={"output_language": "zh-CN", "decisions": []},
            output_language="zh-CN",
        )


def test_bundle_refuses_raw_metadata_without_an_identity_contract() -> None:
    with pytest.raises(ValueError, match="accepted canonical identity contract"):
        bundle(
            metadata={"title": "Raw Candidate"},
            evidence_wrapper={"evidence_pack": {}},
            figures_wrapper={},
            assets_wrapper={},
        )


def test_bundle_compact_writing_contract_keeps_depth_rules_without_old_bundle_fields() -> None:
    synthesis = bundle(
        metadata={"title": "Contract Paper"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "paper_id": "paper:contract",
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "paper:contract",
                "identity_verdict": "accepted",
                "work_level_identity": {"title": "Contract Paper"},
                "accepted_metadata": {"title": "Contract Paper"},
            },
            "coverage": {"total_pages": 8, "text_truncated": False},
            "sections": [
                {
                    "section_id": "sec:method",
                    "title": "Method",
                    "page_start": 2,
                    "page_end": 4,
                }
            ],
            "pages": [{"page": 2, "section_ids": ["sec:method"]}],
        },
    )

    contract = synthesis["writing_contract"]

    assert contract["note_plan_contract"]["grounding_field"] == "section_plan[*].evidence_sources"
    assert contract["grounding_contract"]["source_of_truth"] == "source_manifest"
    assert contract["grounding_contract"]["source_index_source_of_truth"] == "source_manifest"
    assert contract["grounding_contract"]["truncation_source_of_truth"] == (
        "source_manifest.coverage_or_pdf"
    )
    assert contract["grounding_contract"]["partial_reading_acceptance_owner"] == (
        "note_plan_or_grounding"
    )
    assert contract["grounding_contract"]["excluded_model_input_fields"] == list(
        WRITING_CONTRACT_RULES["excluded_model_input_fields"]
    )
    assert contract["grounding_contract"]["required_sections"] == list(
        WRITING_CONTRACT_RULES["grounding_required_sections"]
    )
    assert contract["grounding_contract"]["note_plan_depth_requirements"] == {
        "required_section_focus_min_chars": WRITING_CONTRACT_RULES[
            "note_plan_depth_requirements"
        ]["required_section_focus_min_chars"],
        "required_section_focus_fields": list(
            WRITING_CONTRACT_RULES["note_plan_depth_requirements"][
                "required_section_focus_fields"
            ]
        ),
        "generic_focus_phrases": list(
            WRITING_CONTRACT_RULES["note_plan_depth_requirements"][
                "generic_focus_phrases"
            ]
        ),
    }
    assert contract["figure_table_contract"]["usable_insert_candidate"] == {
        "kinds": list(WRITING_CONTRACT_RULES["usable_insert_candidate"]["kinds"]),
        "visual_quality_status": WRITING_CONTRACT_RULES["usable_insert_candidate"][
            "visual_quality_status"
        ],
        "requires_source_image_path": WRITING_CONTRACT_RULES["usable_insert_candidate"][
            "requires_source_image_path"
        ],
    }
    assert contract["figure_table_contract"]["manual_visual_review_required_statuses"] == list(
        WRITING_CONTRACT_RULES["manual_visual_review_required_statuses"]
    )
    assert contract["figure_table_contract"]["automatic_fail_closed_visual_statuses"] == list(
        WRITING_CONTRACT_RULES["automatic_fail_closed_visual_statuses"]
    )
    assert contract["figure_table_contract"]["manual_review_claim_requires_image_inspection"] is True
    review_contract = contract["figure_table_contract"]["visual_review"]
    assert review_contract["selected_render_dpi"] == 300
    assert review_contract["page_preview_dpi"] == 96
    assert review_contract["repair_limit"] == 1
    assert review_contract["repairable_failure_reasons"] == [
        "caption_contamination",
        "surrounding_prose_contamination",
        "scientific_content_clipped",
        "insufficient_safety_margin",
    ]
    assert review_contract["terminal_failure_reasons"] == [
        "identity_mismatch",
        "caption_inseparable",
        "ambiguous_visual_body",
        "unreadable_source",
        "scientific_content_missing",
        "repair_limit_exhausted",
    ]
    assert "review_pending" in contract["figure_table_contract"]["decision_values"]
    assert contract["note_plan_contract"]["analysis_coverage_field"] == "central_claims[*]"
    assert contract["analysis_coverage_contract"]["required_plan_fields"] == list(
        WRITING_CONTRACT_RULES["analysis_coverage_contract"]["required_plan_fields"]
    )
    for old_key in WRITING_CONTRACT_RULES["excluded_model_input_fields"]:
        assert old_key not in synthesis


def test_bundle_truncation_warnings_use_source_manifest_not_evidence_pack() -> None:
    synthesis = bundle(
        metadata={},
        evidence_wrapper={
            "evidence_pack": {
                "pdf_coverage": {
                    "total_pages": 4,
                    "text_truncated": True,
                    "truncated_due_to_page_limit": True,
                }
            }
        },
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "paper:coverage",
                "identity_verdict": "accepted",
                "work_level_identity": {"title": "Coverage Paper"},
                "accepted_metadata": {"title": "Coverage Paper"},
            },
            "coverage": {
                "total_pages": 4,
                "text_truncated": False,
                "truncated_due_to_page_limit": False,
            }
        },
    )

    assert synthesis["coverage"]["source_coverage"] == {
        "total_pages": 4,
        "text_truncated": False,
        "truncated_due_to_page_limit": False,
    }
    assert "source_text_truncated" not in synthesis["coverage"]["truncation_warnings"]


def test_bundle_preserves_identity_equivalence_and_source_manifestation() -> None:
    synthesis = bundle(
        metadata={"title": "Published Work-Level Title"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "doi:10.1234/published",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Published Work-Level Title",
                    "doi": "10.1234/published",
                },
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "title": "Local Preprint Title",
                    "local_pdf_path": "/tmp/local_preprint.pdf",
                },
                "selected_identity_evidence": [],
                "equivalence_decision": {
                    "status": "equivalent",
                    "reason": "title_author_or_abstract_supports_equivalence",
                    "location_binding": "source_manifestation",
                    "evidence": [
                        {
                            "kind": "title_similarity",
                            "status": "match",
                            "score": 0.91,
                        }
                    ],
                },
                "warnings": [],
                "repair_trace_path": "/tmp/trace.json",
                "provenance": {},
            }
        },
    )

    identity_contract = synthesis["identity_contract"]
    assert identity_contract["work_level_identity"]["title"] == "Published Work-Level Title"
    assert identity_contract["source_manifestation"]["title"] == "Local Preprint Title"
    assert identity_contract["equivalence_decision"]["status"] == "equivalent"
    assert identity_contract["equivalence_decision"]["location_binding"] == "source_manifestation"


def test_bundle_uses_only_canonical_accepted_metadata_for_model_input() -> None:
    synthesis = bundle(
        metadata={
            "paper_id": "doi:10.9999/rejected",
            "title": "Rejected Candidate",
            "doi": "10.9999/rejected",
            "abstract": "Rejected abstract must not reach the model.",
            "pdf_url": "https://example.test/rejected.pdf",
        },
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "paper_id": "doi:10.1234/accepted",
            "title": "Accepted Paper",
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "schema_version": 2,
                "paper_id": "doi:10.1234/accepted",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Accepted Paper",
                    "doi": "10.1234/accepted",
                },
                "accepted_metadata": {
                    "paper_id": "doi:10.1234/accepted",
                    "title": "Accepted Paper",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.1234/accepted",
                    "abstract": "Accepted abstract.",
                    "metadata_sources": ["zotero", "crossref"],
                },
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "local_pdf_path": "/tmp/accepted.pdf",
                },
                "bound_sources": [],
                "accepted_observations": [],
                "rejected_observations": [
                    {
                        "provider": "crossref",
                        "reason": "conflicting_strong_identifier",
                        "record": {
                            "doi": "10.9999/rejected",
                            "pdf_url": "https://example.test/rejected.pdf",
                        },
                    }
                ],
                "selected_identity_evidence": [],
                "equivalence_decision": {"status": "equivalent"},
                "warnings": [],
            },
        },
    )

    assert synthesis["paper_id"] == "doi:10.1234/accepted"
    assert synthesis["title"] == "Accepted Paper"
    assert synthesis["metadata"] == {
        "title": "Accepted Paper",
        "translated_title": "",
        "authors": ["Alice Example"],
        "affiliations": [],
        "year": "2026",
        "venue": "",
        "doi": "10.1234/accepted",
        "source_url": "",
        "abstract": "Accepted abstract.",
        "arxiv_id": "",
        "zotero_key": "",
        "metadata_sources": ["zotero", "crossref"],
        "identity_confidence": "",
        "identity_confidence_reasons": [],
    }
    serialized_model_input = json.dumps(synthesis, ensure_ascii=False)
    assert "Rejected abstract must not reach the model" not in serialized_model_input
    assert "https://example.test/rejected.pdf" not in serialized_model_input


def test_bundle_rejects_noncanonical_artifact_disguised_as_schema_v2() -> None:
    with pytest.raises(ValueError, match="canonical identity"):
        bundle(
            metadata={"title": "Untrusted Paper"},
            evidence_wrapper={"evidence_pack": {}},
            figures_wrapper={},
            assets_wrapper={},
            source_manifest={
                "identity_contract": {
                    "artifact_type": "raw_metadata",
                    "schema_version": 2,
                    "paper_id": "doi:10.9999/untrusted",
                    "identity_verdict": "accepted",
                    "accepted_metadata": {
                        "title": "Untrusted Paper",
                        "doi": "10.9999/untrusted",
                    },
                }
            },
        )


def test_bundle_preserves_identity_warnings_without_body_writing_instruction() -> None:
    warning = {
        "reason": "source_manifestation_year_differs_from_work_identity",
        "scope": "metadata",
        "impact": "avoid_over_specific_year_claims",
    }
    synthesis = bundle(
        metadata={"title": "Published Work-Level Title"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "doi:10.1234/published",
                "identity_verdict": "accepted_with_warnings",
                "work_level_identity": {
                    "title": "Published Work-Level Title",
                    "doi": "10.1234/published",
                    "year": "2026",
                },
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "title": "Local Preprint Title",
                    "local_pdf_path": "/tmp/local_preprint.pdf",
                    "year": "2024",
                },
                "selected_identity_evidence": [],
                "equivalence_decision": {
                    "status": "equivalent",
                    "reason": "shared_work_identifier",
                    "location_binding": "source_manifestation",
                    "evidence": [],
                },
                "warnings": [warning],
                "repair_trace_path": "/tmp/trace.json",
                "provenance": {},
            }
        },
    )

    assert synthesis["identity_contract"]["identity_verdict"] == "accepted_with_warnings"
    assert synthesis["identity_contract"]["warnings"] == [warning]

    writing_contract_text = json.dumps(
        synthesis["writing_contract"],
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "accepted_with_warnings" not in writing_contract_text
    assert "source_manifestation_year_differs_from_work_identity" not in writing_contract_text
    assert "identity warning" not in writing_contract_text.lower()
