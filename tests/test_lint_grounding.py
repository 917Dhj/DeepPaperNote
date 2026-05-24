from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from contracts import PAPER_TYPE_CONTRACTS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINT_GROUNDING_SCRIPT = PROJECT_ROOT / "scripts" / "lint_grounding.py"


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def run_lint_grounding(
    tmp_path: Path,
    note_plan: dict,
    source_manifest: dict,
    bundle: dict | None = None,
    figure_decisions: dict | None = None,
) -> dict:
    note_plan_path = write_json(tmp_path / "note_plan.json", note_plan)
    source_manifest_path = write_json(tmp_path / "source_manifest.json", source_manifest)
    figure_decisions_path = write_json(
        tmp_path / "figure_decisions.json",
        figure_decisions if figure_decisions is not None else {"decisions": []},
    )
    output_path = tmp_path / "grounding.json"
    cmd = [
        sys.executable,
        str(LINT_GROUNDING_SCRIPT),
        "--note-plan",
        str(note_plan_path),
        "--source-manifest",
        str(source_manifest_path),
        "--figure-decisions",
        str(figure_decisions_path),
        "--output",
        str(output_path),
    ]
    if bundle is not None:
        bundle_path = write_json(tmp_path / "bundle.json", bundle)
        cmd.extend(["--bundle-json", str(bundle_path)])
    subprocess.run(cmd, check=True)
    return json.loads(output_path.read_text(encoding="utf-8"))


def source_manifest(*, truncated: bool = False) -> dict:
    return {
        "paper_id": "paper:grounded",
        "coverage": {"total_pages": 12, "text_truncated": truncated},
        "sections": [
            {
                "section_id": "sec:introduction",
                "title": "Introduction",
                "page_start": 1,
                "page_end": 2,
            },
            {"section_id": "sec:method", "title": "Method", "page_start": 3, "page_end": 6},
            {"section_id": "sec:experiment", "title": "Experiment", "page_start": 7, "page_end": 9},
        ],
        "pages": [
            {"page": 1, "section_ids": ["sec:introduction"]},
            {"page": 4, "section_ids": ["sec:method"]},
        ],
        "captions": {"figures": [], "tables": []},
    }


def note_plan_with_sources(sources_by_section: dict[str, list[dict] | list[str]]) -> dict:
    section_plan = [
        {
            "section": section,
            "focus": f"Explain how SWE-bench repository issue repair shapes {section}.",
            "evidence_sources": sources,
        }
        for section, sources in sources_by_section.items()
    ]
    return {
        "paper_type": "AI_method",
        "paper_type_rationale": "method paper",
        "dominant_domain": "AI",
        "must_cover": ["method"],
        "key_numbers": ["91.2"],
        "real_comparisons": ["baseline"],
        "central_claims": [
            {
                "claim": "The method improves issue repair reliability.",
                "supporting_evidence": [{"section_id": "sec:method"}],
                "what_it_actually_proves": "The paper describes and evaluates the repair mechanism in its reported setting.",
                "what_it_does_not_prove": "It does not prove arbitrary repository repair robustness.",
            }
        ],
        "claim_boundaries": ["The claim is bounded by the reported benchmark and baselines."],
        "negative_or_limiting_results": ["The plan records limiting evidence rather than inventing failures."],
        "mechanism_result_map": ["The repair-state mechanism explains the lower unrecoverable-error rate."],
        "comparative_positioning": ["The plan distinguishes the method from answer-only baselines."],
        "reuse_takeaways": ["Track evidence and repair steps separately."],
        "followup_questions": ["Check whether the mechanism still works with missing tool outputs."],
        "section_plan": section_plan,
    }


def grounded_note_plan() -> dict:
    return note_plan_with_sources(
        {
            "研究问题": [{"section_id": "sec:introduction"}],
            "数据与任务定义": [{"pages": [2, 3]}],
            "方法主线": [{"section_id": "sec:method"}],
            "关键结果": [{"pages": [7, 9]}],
            "深度分析": [{"section_id": "sec:experiment"}],
            "局限": [{"pages": {"start": 10, "end": 12}}],
        }
    )


def slim_bundle() -> dict:
    return {
        "writing_contract": {
            "contracts_by_paper_type": PAPER_TYPE_CONTRACTS,
            "paper_type_selection": {"source_of_truth": "note_plan.paper_type"},
        }
    }


def test_lint_grounding_accepts_section_id_or_page_range(tmp_path: Path) -> None:
    result = run_lint_grounding(tmp_path, grounded_note_plan(), source_manifest(), slim_bundle())

    assert result["passes_grounding"] is True
    assert [issue for issue in result["issues"] if issue.get("severity", "error") == "error"] == []


def test_lint_grounding_rejects_missing_section_id_and_invalid_page(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][0]["evidence_sources"] = [{"section_id": "sec:missing"}]
    plan["section_plan"][1]["evidence_sources"] = [{"pages": [13]}]

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "source_reference_missing_valid_section_or_pages" in codes


def test_lint_grounding_rejects_malformed_page_range_without_crashing(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][1]["evidence_sources"] = [
        {"page_range": {"start": "p.3", "end": 5}}
    ]

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "source_reference_missing_valid_section_or_pages" in codes


def test_lint_grounding_rejects_old_evidence_references(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][2]["evidence_sources"] = ["synthesis_bundle.evidence.method_evidence"]

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "old_bundle_reference" in codes
    assert "note_plan_old_bundle_reference_present" in codes


def test_lint_grounding_blocks_truncated_source_without_partial_acceptance(tmp_path: Path) -> None:
    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        source_manifest(truncated=True),
        slim_bundle(),
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "source_manifest_truncated_without_partial_acceptance" in codes


def test_lint_grounding_allows_truncated_source_when_partial_accepted(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["source_coverage"] = {"partial_reading_accepted": True}

    result = run_lint_grounding(tmp_path, plan, source_manifest(truncated=True), slim_bundle())

    assert result["passes_grounding"] is True


def test_lint_grounding_requires_contract_lookup_by_note_plan_paper_type(tmp_path: Path) -> None:
    bundle = {"writing_contract": {"paper_type_contracts": PAPER_TYPE_CONTRACTS}}

    result = run_lint_grounding(tmp_path, grounded_note_plan(), source_manifest(), bundle)
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "bundle_contracts_by_paper_type_missing" in codes


def test_lint_grounding_rejects_old_bundle_summary_field(tmp_path: Path) -> None:
    bundle = slim_bundle()
    bundle["summary"] = {"paper_type": "AI_method"}

    result = run_lint_grounding(tmp_path, grounded_note_plan(), source_manifest(), bundle)
    fields = {issue.get("field") for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "summary" in fields


def test_lint_grounding_rejects_old_evidence_pack_refs(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][2]["evidence_sources"] = ["evidence_pack.method_evidence"]
    plan["paper_type_rationale"] = "copied from summary.paper_type"
    bundle = slim_bundle()
    bundle["evidence_pack"] = {"method_evidence": []}

    result = run_lint_grounding(tmp_path, plan, source_manifest(), bundle)
    codes = {issue["code"] for issue in result["issues"]}
    fields = {issue.get("field") for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "old_bundle_reference" in codes
    assert "note_plan_old_bundle_reference_present" in codes
    assert "evidence_pack" in fields


def test_lint_grounding_rejects_thin_required_section_focus(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][2]["focus"] = "method"

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "section_plan_focus_too_thin" in codes


def test_lint_grounding_rejects_ungrounded_central_claim(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["central_claims"][0]["supporting_evidence"] = [{"section_id": "sec:missing"}]

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "source_reference_missing_valid_section_or_pages" in codes


def test_lint_grounding_rejects_incomplete_central_claim(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    del plan["central_claims"][0]["what_it_does_not_prove"]

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "central_claim_required_field_missing" in codes


def test_lint_grounding_rejects_generic_required_section_focus(tmp_path: Path) -> None:
    plan = grounded_note_plan()
    plan["section_plan"][0]["focus"] = (
        "Use the raw source to explain the paper-specific role of this section."
    )

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "section_plan_focus_too_thin" in codes


def test_lint_grounding_blocks_caption_without_figure_table_decision(tmp_path: Path) -> None:
    manifest = source_manifest()
    manifest["captions"] = {
        "figures": [{"id": "Figure 1", "caption": "Architecture", "page": 4}],
        "tables": [],
    }

    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        manifest,
        slim_bundle(),
        figure_decisions={"decisions": []},
    )
    codes = {issue["code"] for issue in result["issues"]}
    severities = {issue["code"]: issue.get("severity", "error") for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "figure_table_caption_missing_decision" in codes
    assert severities["figure_table_caption_missing_decision"] == "error"


def test_lint_grounding_treats_fig_abbreviation_as_same_decision(tmp_path: Path) -> None:
    manifest = source_manifest()
    manifest["captions"] = {
        "figures": [
            {"id": "Figure 14", "caption": "Main result.", "page": 4},
            {"id": "Fig 14", "caption": "shows the result in text.", "page": 4},
        ],
        "tables": [],
    }

    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        manifest,
        slim_bundle(),
        figure_decisions={
            "decisions": [
                {
                    "source_id": "Figure 14",
                    "kind": "figure",
                    "decision": "placeholder",
                    "reason": "selected_by_figure_plan",
                    "visual_quality_status": "",
                    "priority": 2,
                    "plan_kind": "main_result",
                    "skip_reason": "asset_candidate_missing",
                }
            ]
        },
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert "figure_table_caption_missing_decision" not in codes


def test_lint_grounding_rejects_placeholder_decision_for_usable_candidate(tmp_path: Path) -> None:
    manifest = source_manifest()
    manifest["captions"] = {
        "figures": [{"id": "Figure 1", "caption": "Architecture", "page": 4}],
        "tables": [],
    }
    plan = grounded_note_plan()
    decisions = {
        "decisions": [
            {
                "source_id": "Figure 1",
                "kind": "figure",
                "decision": "placeholder",
                "reason": "selected_by_figure_plan",
                "visual_quality_status": "usable_candidate",
                "priority": 1,
                "plan_kind": "method_overview",
                "source_image_path": "/tmp/images/page_004_fig_figure_1.png",
                "skip_reason": "not_auto_insertable_by_kind_or_priority",
            }
        ]
    }

    result = run_lint_grounding(tmp_path, plan, manifest, slim_bundle(), decisions)

    assert result["passes_grounding"] is False


def test_lint_grounding_rejects_shallow_section_plan_with_valid_section_ids(
    tmp_path: Path,
) -> None:
    plan = grounded_note_plan()
    for item in plan["section_plan"]:
        item["evidence_sources"] = [{"section_id": "sec:method"}]
        item["focus"] = "shallow"

    result = run_lint_grounding(tmp_path, plan, source_manifest(), slim_bundle())

    assert result["passes_grounding"] is False


def test_lint_grounding_rejects_high_priority_usable_figure_placeholder(
    tmp_path: Path,
) -> None:
    decisions = {
        "decisions": [
            {
                "source_id": "Figure 1",
                "kind": "figure",
                "decision": "placeholder",
                "visual_quality_status": "usable_candidate",
                "priority": 1,
                "plan_kind": "method_overview",
                "source_image_path": "/tmp/images/page_004_fig_figure_1.png",
                "skip_reason": "not_auto_insertable_by_kind_or_priority",
            }
        ]
    }

    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        source_manifest(),
        slim_bundle(),
        figure_decisions=decisions,
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "usable_insert_candidate_left_placeholder" in codes


def test_lint_grounding_rejects_lower_priority_usable_figure_placeholder(
    tmp_path: Path,
) -> None:
    decisions = {
        "decisions": [
            {
                "source_id": "Figure 2",
                "kind": "figure",
                "decision": "placeholder",
                "visual_quality_status": "usable_candidate",
                "priority": 3,
                "plan_kind": "data_or_task",
                "source_image_path": "/tmp/images/page_003_fig_figure_2.png",
                "skip_reason": "not_auto_insertable_by_kind_or_priority",
            }
        ]
    }

    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        source_manifest(),
        slim_bundle(),
        figure_decisions=decisions,
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "usable_insert_candidate_left_placeholder" in codes


def test_lint_grounding_rejects_insert_decision_without_source_image(
    tmp_path: Path,
) -> None:
    decisions = {
        "decisions": [
            {
                "source_id": "Figure 1",
                "kind": "figure",
                "decision": "insert",
                "visual_quality_status": "usable_candidate",
                "priority": 1,
            }
        ]
    }

    result = run_lint_grounding(
        tmp_path,
        grounded_note_plan(),
        source_manifest(),
        slim_bundle(),
        figure_decisions=decisions,
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert result["passes_grounding"] is False
    assert "figure_insert_decision_missing_source_image" in codes
