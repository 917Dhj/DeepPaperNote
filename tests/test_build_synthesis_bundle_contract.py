from __future__ import annotations

import json

from build_synthesis_bundle import bundle
from contracts import WRITING_CONTRACT_RULES


def test_bundle_compact_writing_contract_keeps_depth_rules_without_old_bundle_fields() -> None:
    synthesis = bundle(
        metadata={"title": "Contract Paper"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={
            "paper_id": "paper:contract",
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
