from __future__ import annotations

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
    assert "evidence" not in synthesis
    assert "candidate_chunks" not in synthesis
    assert "section_texts" not in synthesis
    assert "summary" not in synthesis
