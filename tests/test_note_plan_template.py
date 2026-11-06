from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from build_synthesis_bundle import compact_writing_contract
from contracts import WRITING_CONTRACT_RULES, writing_contract_rules
from lint_grounding import validate_note_plan
from lint_note import inspect_note_plan

EVIDENCE_FIRST = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "deeppapernote"
    / "references"
    / "evidence-first.md"
)

SOURCE_MANIFEST = {
    "sections": [
        {"section_id": section_id}
        for section_id in (
            "sec:introduction",
            "sec:data",
            "sec:method",
            "sec:experiments",
            "sec:ablation",
            "sec:limitations",
        )
    ],
    "coverage": {"total_pages": 12},
}


def template(language: str) -> dict:
    return compact_writing_contract(language)["note_plan_contract"]["template"]


def lint_plan_issues(tmp_path: Path, plan: dict, language: str) -> list[str]:
    plan_path = tmp_path / "note_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    found, issues = inspect_note_plan(plan_path, language)
    assert found is True
    return issues


@pytest.mark.parametrize("language", ["zh-CN", "en"])
def test_template_has_the_shape_the_gates_check(language: str) -> None:
    rules = writing_contract_rules(language)
    plan = template(language)

    contract = compact_writing_contract(language)["note_plan_contract"]
    assert list(plan) == contract["required_fields"] + contract["optional_fields"] + list(contract["type_fields"])
    assert plan["core_answers"] == {} and plan["workflow"] == []
    assert plan["reader_research_direction"] == ""
    assert plan["output_language"] == language
    claim_fields = WRITING_CONTRACT_RULES["analysis_coverage_contract"]["central_claim_fields"]
    assert [list(claim) for claim in plan["central_claims"]] == [list(claim_fields)]
    # The middle sections depend on the paper type, so the template leaves one blank entry before limitations.
    assert [item["section"] for item in plan["section_plan"]] == ["", rules["limitations_section"]]
    for item in plan["section_plan"]:
        assert item == {
            "section": item["section"],
            "focus": "",
            "subsections": [],
            "evidence_sources": [],
        }


@pytest.mark.parametrize("language", ["zh-CN", "en"])
def test_unfilled_template_fails_lint_and_grounding(tmp_path: Path, language: str) -> None:
    plan = template(language)
    rules = writing_contract_rules(language)

    issues = lint_plan_issues(tmp_path, plan, language)
    for field in ("paper_type", "must_cover", "key_numbers", "followup_questions"):
        assert f"planning_{field}_empty" in issues
    assert "planning_central_claims_claim_missing" in issues
    assert "planning_central_claims_supporting_evidence_missing" in issues

    codes = {
        (issue["code"], issue.get("section", ""))
        for issue in validate_note_plan(plan, SOURCE_MANIFEST, language)
    }
    assert ("section_plan_grounding_missing", rules["limitations_section"]) in codes
    assert ("note_plan_paper_type_invalid", "") in codes
    assert ("central_claim_supporting_evidence_missing", "") in codes


def test_documented_note_plan_example_passes_lint_and_grounding(tmp_path: Path) -> None:
    text = EVIDENCE_FIRST.read_text(encoding="utf-8")
    plan = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))

    assert lint_plan_issues(tmp_path, plan, "zh-CN") == []
    assert validate_note_plan(plan, SOURCE_MANIFEST, "zh-CN") == []
