from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import contracts
import lint_grounding
import lint_note
import type_profiles
from localization import note_schema
from test_lint_grounding import grounded_note_plan, source_manifest
from test_lint_note import _valid_note_text, _valid_plan_payload

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "deeppapernote" / "scripts"


# --- the profiles themselves -------------------------------------------------

def test_there_are_ten_types_and_old_values_are_gone() -> None:
    assert contracts.PAPER_TYPE_VALUES == (
        "method", "system", "theory", "position", "benchmark_or_dataset", "discovery_empirical",
        "human_subjects_empirical", "survey_or_review", "qualitative_empirical", "humanities_argument",
    )
    for old in ("AI_method", "clinical_or_psychology_empirical", "humanities_or_social_science"):
        assert old not in contracts.PAPER_TYPE_VALUES


@pytest.mark.parametrize("language", type_profiles.LANGUAGES)
@pytest.mark.parametrize("paper_type", type_profiles.TYPE_KEYS)
def test_every_type_has_a_consistent_profile(paper_type: str, language: str) -> None:
    found = type_profiles.PROFILES[paper_type]
    sections = contracts.note_required_sections(language, paper_type)
    assert len(sections) == len(set(sections)), "a middle section collides with a fixed one"
    keys = {item["key"] for item in found["sections"]}
    assert 4 <= len(keys) <= 7
    ids = [item["id"] for item in found["core_questions"]]
    assert len(ids) == len(set(ids)) and 4 <= len(ids) <= 7
    assert all(item["section"] in keys for item in found["core_questions"])
    assert len(found["secondary_question_ids"]) == type_profiles.SECONDARY_QUESTION_LIMIT
    assert set(found["secondary_question_ids"]) <= set(ids)
    if found["workflow"]:
        assert found["workflow"]["section"] in keys
    for item in found["sections"]:
        assert item["name"][language].strip() and item["purpose"][language].strip()


def test_workflow_types_match_the_design() -> None:
    with_workflow = {key for key, found in type_profiles.PROFILES.items() if found["workflow"]}
    assert with_workflow == {
        "method", "system", "benchmark_or_dataset", "human_subjects_empirical",
        "qualitative_empirical", "discovery_empirical", "survey_or_review",
    }
    assert type_profiles.PROFILES["survey_or_review"]["workflow"]["may_be_unreported"] is True


def test_method_and_benchmark_follow_the_supervisor_skills_order() -> None:
    assert type_profiles.middle_sections("method", "zh-CN") == (
        "背景与问题", "现有方法的局限", "核心思路与挑战", "方法", "实验证据", "深度分析",
    )
    assert type_profiles.middle_sections("benchmark_or_dataset", "zh-CN") == (
        "评测缺口", "任务与设计目标", "构造流程与质量控制", "评测框架", "实验发现", "它到底测到了什么",
    )


def test_note_sections_keep_the_fixed_head_and_tail() -> None:
    sections = contracts.note_required_sections("zh-CN", "position")
    assert sections[:4] == ("核心信息", "原文摘要翻译", "创新点", "一句话总结")
    assert sections[-4:] == ("局限", "阅读收获", "关联", "我的笔记")
    assert contracts.grounding_required_sections("zh-CN", "position")[-1] == "局限"


# --- plan checks -------------------------------------------------------------

def codes(plan: dict, language: str = "zh-CN") -> set[str]:
    return {item["code"] for item in contracts.type_plan_issues(plan, language)}


def test_the_fixture_plan_is_clean() -> None:
    assert codes(_valid_plan_payload()) == set()


def test_every_core_question_needs_an_answer_or_a_not_reported_reason() -> None:
    plan = _valid_plan_payload()
    del plan["core_answers"]["method.problem"]
    plan["core_answers"]["method.key_idea"] = {"answer": "x", "evidence_refs": []}
    plan["core_answers"]["method.prior_gaps"] = {"not_reported": True, "reason": ""}
    plan["core_answers"]["theory.result"] = {"answer": "x", "evidence_refs": [{"section_id": "sec:a"}]}
    assert codes(plan) == {
        "note_plan_core_answer_missing", "note_plan_core_answer_invalid", "note_plan_core_answer_unexpected",
    }


def test_type_specific_enums() -> None:
    plan = _valid_plan_payload()
    plan["positioning"] = ""
    plan["survey_mode"] = "narrative"
    assert codes(plan) == {"note_plan_positioning_invalid", "note_plan_survey_mode_not_applicable"}


def test_workflow_shape() -> None:
    plan = _valid_plan_payload()
    plan["workflow"][0]["steps"] = plan["workflow"][0]["steps"][:2]
    plan["workflow"][0]["steps"][0]["novel"] = "yes"
    assert codes(plan) == {"note_plan_workflow_step_count_invalid", "note_plan_workflow_step_invalid"}
    plan["workflow"] = []
    assert codes(plan) == {"note_plan_workflow_missing"}


def test_types_without_workflow_refuse_one() -> None:
    plan = position_plan()
    plan["workflow"] = _valid_plan_payload()["workflow"]
    assert codes(plan) == {"note_plan_workflow_not_applicable"}


def test_survey_may_leave_the_workflow_unreported() -> None:
    plan = position_plan()
    plan.update(paper_type="survey_or_review", survey_mode="narrative", core_answers=answers_for("survey_or_review"))
    assert codes(plan) == set()


def test_benchmark_steps_name_who_and_the_quality_gate() -> None:
    plan = position_plan()
    plan.update(paper_type="benchmark_or_dataset", core_answers=answers_for("benchmark_or_dataset"))
    step = {"step": "s", "input": "i", "operation": "o", "output": "out", "who": "LLM", "quality_gate": "human check"}
    plan["workflow"] = [{"name": "build", "steps": [dict(step) for _ in range(3)]}]
    assert codes(plan) == set()
    plan["workflow"][0]["steps"][0] = {**step, "novel": True}
    assert codes(plan) == {"note_plan_workflow_step_invalid"}


def test_secondary_type_adds_two_questions_and_needs_a_host_section() -> None:
    plan = _valid_plan_payload()
    plan["secondary_type"] = "benchmark_or_dataset"
    assert codes(plan) == {"note_plan_secondary_host_section_invalid", "note_plan_core_answer_missing"}
    plan["secondary_host_section"] = "实验证据"
    for qid in ("benchmark.data", "benchmark.protocol"):
        plan["core_answers"][qid] = {"not_reported": True, "reason": "No data card."}
    assert codes(plan) == set()
    plan["secondary_type"] = "method"
    assert "note_plan_secondary_type_invalid" in codes(plan)


def test_weak_evidence_needs_more_than_half_unreported() -> None:
    plan = _valid_plan_payload()
    assert contracts.weak_evidence_question_ids(plan) == []
    for qid in ("method.prior_gaps", "method.claim_evidence"):
        plan["core_answers"][qid] = {"not_reported": True, "reason": "Not in the paper."}
    assert contracts.weak_evidence_question_ids(plan) == []  # three of six is not more than half
    plan["core_answers"]["method.boundary_cost"] = {"not_reported": True, "reason": "Not in the paper."}
    assert contracts.weak_evidence_question_ids(plan) == [
        "method.prior_gaps", "method.claim_evidence", "method.comparison", "method.boundary_cost",
    ]


def answers_for(paper_type: str) -> dict:
    return {
        qid: {"answer": f"Answer for {qid}.", "evidence_refs": [{"section_id": "sec:method"}]}
        for qid in type_profiles.question_ids(paper_type)
    }


def position_plan() -> dict:
    plan = _valid_plan_payload()
    plan.update(paper_type="position", positioning="", workflow=[], core_answers=answers_for("position"))
    return plan


# --- grounding ---------------------------------------------------------------

def test_grounding_requires_the_types_middle_sections_and_grounded_answers() -> None:
    plan = grounded_note_plan()
    assert lint_grounding.validate_note_plan(plan, source_manifest(), "zh-CN") == []
    plan["core_answers"]["method.problem"]["evidence_refs"] = [{"section_id": "sec:nowhere"}]
    plan["section_plan"] = [item for item in plan["section_plan"] if item["section"] != "实验证据"]
    found = {item["code"] for item in lint_grounding.validate_note_plan(plan, source_manifest(), "zh-CN")}
    assert {"section_plan_required_section_missing", "source_reference_missing_valid_section_or_pages"} <= found


def test_grounding_rejects_an_old_paper_type() -> None:
    plan = grounded_note_plan()
    plan["paper_type"] = "AI_method"
    found = {item["code"] for item in lint_grounding.validate_note_plan(plan, source_manifest(), "zh-CN")}
    assert "note_plan_paper_type_invalid" in found


# --- note lint ---------------------------------------------------------------

def run_lint(tmp_path: Path, note: str, plan: dict) -> dict:
    note_path = tmp_path / "Paper.md"
    plan_path = tmp_path / "Paper.plan.json"
    note_path.write_text(note, encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "lint_note.py"), "--input", str(note_path), "--plan-file", str(plan_path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def reasons(payload: dict) -> set[str]:
    return {str(item["reason"]) for item in payload["substantive_content_issues"]}


def test_fixture_note_passes_structure_and_substance(tmp_path: Path) -> None:
    payload = run_lint(tmp_path, _valid_note_text(), _valid_plan_payload())
    assert payload["missing_sections"] == []
    assert payload["passes_basic_structure"] and payload["passes_substantive_content"], payload["warnings"]
    assert payload["passes_plan_gate"], payload["planning_artifact_issues"]


def test_old_sections_are_missing_sections_now(tmp_path: Path) -> None:
    note = _valid_note_text().replace("## 实验证据", "## 关键结果")
    payload = run_lint(tmp_path, note, _valid_plan_payload())
    assert payload["missing_sections"] == ["实验证据"]


def test_unknown_paper_type_fails_basic_structure(tmp_path: Path) -> None:
    plan = _valid_plan_payload()
    plan["paper_type"] = "AI_method"
    payload = run_lint(tmp_path, _valid_note_text(), plan)
    assert "paper_type_unknown" in payload["warnings"] and not payload["passes_basic_structure"]


@pytest.mark.parametrize(
    ("edit", "reason"),
    [
        (lambda t: t.replace("### 方法流程", "### 机制流程"), "workflow_subsection_missing"),
        (lambda t: t.replace("| 答案生成 | 状态日志 | 结合日志输出结论 | 可追溯答案 | 是 |\n", ""), "workflow_step_count_mismatch"),
        (lambda t: t.replace("| 步骤 | 输入 | 做什么 | 输出 | 本文新做法 |", "| 步骤 | 输入 | 操作 | 输出 | 新做法 |"), "workflow_table_header_invalid"),
        (lambda t: t.replace("证据筛选 → 工具规划 → 答案生成\n", ""), "workflow_overview_missing"),
    ],
)
def test_workflow_subsection_mirrors_the_plan(tmp_path: Path, edit, reason: str) -> None:
    payload = run_lint(tmp_path, edit(_valid_note_text()), _valid_plan_payload())
    assert reason in reasons(payload)
    assert not payload["passes_substantive_content"]


def test_two_flows_need_two_tables(tmp_path: Path) -> None:
    plan = _valid_plan_payload()
    plan["workflow"].append(deepcopy(plan["workflow"][0]))
    assert "workflow_table_count_mismatch" in reasons(run_lint(tmp_path, _valid_note_text(), plan))


def test_weak_evidence_callout_both_ways(tmp_path: Path) -> None:
    plan = _valid_plan_payload()
    for qid in ("method.prior_gaps", "method.claim_evidence", "method.boundary_cost"):
        plan["core_answers"][qid] = {"not_reported": True, "reason": "Not in the paper."}
    assert "weak_evidence_callout_missing" in reasons(run_lint(tmp_path, _valid_note_text(), plan))
    callout = "# Paper\n\n> [!warning] 论文报告不足\n> 论文没有报告：现有方法的局限、收益主张的支撑、稳定性、边界与代价。\n"
    with_callout = _valid_note_text().replace("# Paper\n", callout, 1)
    assert not {"weak_evidence_callout_missing", "weak_evidence_callout_unexpected"} & reasons(run_lint(tmp_path, with_callout, plan))
    assert "weak_evidence_callout_unexpected" in reasons(run_lint(tmp_path, with_callout, _valid_plan_payload()))


def test_secondary_type_needs_its_subsection_in_the_host_section(tmp_path: Path) -> None:
    plan = _valid_plan_payload()
    plan.update(secondary_type="benchmark_or_dataset", secondary_host_section="实验证据")
    for qid in ("benchmark.data", "benchmark.protocol"):
        plan["core_answers"][qid] = {"not_reported": True, "reason": "No data card."}
    assert "secondary_subsection_missing" in reasons(run_lint(tmp_path, _valid_note_text(), plan))
    note = _valid_note_text().replace(
        "## 深度分析\n", "### 配套数据集与评测\n\n论文同时发布了一个小型评测集，但没有说明标注流程。\n\n## 深度分析\n", 1
    )
    assert "secondary_subsection_missing" not in reasons(run_lint(tmp_path, note, plan))


def test_results_section_numbers_only_where_expected() -> None:
    lint_note.configure_output_language("zh-CN")
    lint_note.configure_paper_type("position")
    assert lint_note.NUMBER_SECTIONS == ()
    assert lint_note.RESULTS_SECTIONS == ("支撑论据",)
    lint_note.configure_paper_type("method")
    assert lint_note.NUMBER_SECTIONS == ("实验证据",)


def test_english_type_sections(tmp_path: Path) -> None:
    sections = contracts.note_required_sections("en", "method")
    assert sections[4:10] == (
        "Background and Problem", "Limitations of Prior Work", "Key Idea and Challenges",
        "Method", "Experimental Evidence", "Deep Analysis",
    )
    assert note_schema("en")["sections"]["limitations"] == sections[10]
