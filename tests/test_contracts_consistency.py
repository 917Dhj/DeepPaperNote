from __future__ import annotations

import json
import re
from pathlib import Path

from build_synthesis_bundle import bundle
from contracts import (
    NOTE_PLAN_LIST_FIELDS,
    NOTE_PLAN_REQUIRED_FIELDS,
    NOTE_PLAN_STRING_FIELDS,
    NOTE_REQUIRED_SECTIONS,
    PAPER_TYPE_VALUES,
    WRITING_CONTRACT_RULES,
)
from lint_grounding import validate_central_claims, validate_note_plan
from lint_note import REQUIRED_SECTIONS, inspect_central_claims_plan, inspect_note_plan
from plan_figure_table_decisions import DECISION_VALUES, INSERTABLE_KINDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / "skills" / "deeppapernote"
NOTE_PLAN_REFERENCE_DOCS = (
    "evidence-first.md",
    "final-writing.md",
    "note-quality.md",
)
NOTE_PLAN_PROTOCOL_RE = re.compile(
    r"<note>\.plan\.json|\*_note_plan\.json|scripts/lint_(?:note|grounding)\.py|<note_plan>"
)
REFERENCE_ROUTING_DOCS = (
    "skills/deeppapernote/SKILL.md",
)
PDF_CONTRACT_DOCS = (
    "skills/deeppapernote/SKILL.md",
    "README.md",
    "README.zh-CN.md",
)
PDF_FAIL_CLOSED_BANNED_PHRASES = (
    "clearly labeled degraded",
    "degraded note",
    "provisional rather than finished",
    "abstract only, as the weakest fallback",
    "trustworthy full-text substitute",
)
PDF_FAIL_CLOSED_NEGATIONS = (
    "do not",
    "does not",
    "must not",
    "rather than",
    "instead of",
)


def test_deleted_reference_routers_stay_removed() -> None:
    references = SKILL_ROOT / "references"

    assert not (references / "workflow.md").exists()
    assert not (references / "model-synthesis.md").exists()

    for readme_name in ("README.md", "README.zh-CN.md"):
        readme = (PROJECT_ROOT / readme_name).read_text(encoding="utf-8")
        assert "references/workflow.md" not in readme
        assert "references/model-synthesis.md" not in readme


def test_topic_references_do_not_redefine_canonical_workflow() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    deep_analysis = (SKILL_ROOT / "references" / "deep-analysis.md").read_text(encoding="utf-8")
    evidence_first = (SKILL_ROOT / "references" / "evidence-first.md").read_text(encoding="utf-8")

    assert "every reported `passes_*` gate is `true`" in skill
    assert "Preferred usage pattern:" not in skill
    assert "## Recommended Workflow" not in deep_analysis
    assert "- `method`" not in deep_analysis
    assert "- `system/framework`" not in deep_analysis
    assert "- `benchmark/dataset`" not in deep_analysis
    assert "weak-but-honest note" not in deep_analysis
    assert "based mostly on abstract plus metadata" not in deep_analysis
    assert "three-stage model-first pipeline" not in evidence_first


def test_codex_adapter_stays_thin() -> None:
    adapter = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert adapter == (
        "interface:\n"
        '  display_name: "DeepPaperNote"\n'
        '  short_description: "Generate a high-quality deep-reading note for one paper with a '
        'raw-source manifest workflow and Obsidian-oriented save semantics."\n'
        '  default_prompt: "Use $deeppapernote to create the deep-reading note for this paper."\n'
    )


EXPECTED_PAPER_TYPE_SECTION_PROFILES = {
    "AI_method": {
        "section_semantics": {
            "研究问题": "方法要解决的具体技术问题和现有方法短板。",
            "数据与任务定义": "数据集、输入输出、评测任务和实验设置。",
            "方法主线": "模型、算法、训练或推理机制。",
            "关键结果": "主结果、强基线、消融和关键数字。",
            "深度分析": "方法为什么有效、何处脆弱、复现和扩展代价。",
        },
        "recommended_subsections": {
            "方法主线": ["机制流程", "模型结构", "训练目标", "推理与采样链路", "关键实现细节"],
            "关键结果": ["主结果与强基线", "消融到底说明了什么", "失败或不稳定设置"],
            "深度分析": ["为什么有效", "复杂度与扩展性", "复现注意点"],
        },
    },
    "benchmark_or_dataset": {
        "section_semantics": {
            "研究问题": "这个 benchmark/dataset 想补足的评测或数据缺口。",
            "数据与任务定义": "数据来源、任务拆分、标签/题目定义、样本范围。",
            "方法主线": "数据构建、筛选、标注和评测协议，不写成模型 pipeline。",
            "关键结果": "基线表现、难度分布、覆盖范围和偏差。",
            "深度分析": "它真正测到了什么，以及不能代表什么。",
        },
        "recommended_subsections": {
            "数据与任务定义": ["数据来源", "任务拆分", "标注/筛选协议"],
            "方法主线": ["构建流程", "评测协议", "Baseline 设置"],
            "关键结果": ["基线表现", "难度分布", "覆盖与偏差"],
            "深度分析": ["benchmark 真正测到了什么", "适用边界"],
        },
    },
    "clinical_or_psychology_empirical": {
        "section_semantics": {
            "研究问题": "临床、心理学或行为科学中的研究问题、假设或变量关系。",
            "数据与任务定义": "样本来源、纳排标准、变量/量表、测量方式。",
            "方法主线": "研究设计、分组、测量流程和统计分析路径。",
            "关键结果": "主要效应、相关性、组间差异、不确定性或显著性。",
            "深度分析": "结果解释、因果边界、临床/心理学意义和外推限制。",
        },
        "recommended_subsections": {
            "数据与任务定义": ["样本与纳排标准", "变量与量表", "测量流程"],
            "方法主线": ["研究设计", "分析模型", "主要比较"],
            "关键结果": ["主要效应", "不确定性与显著性", "临床或心理学解释"],
            "深度分析": ["因果解释边界", "外推限制"],
        },
    },
    "humanities_or_social_science": {
        "section_semantics": {
            "研究问题": "作者要解释的社会、文化、历史、制度或理论问题。",
            "数据与任务定义": "材料、案例、文本、访谈、档案或语料范围，不写成 ML task。",
            "方法主线": "理论框架、概念区分和论证路径。",
            "关键结果": "核心解释性发现、概念贡献或对既有观点的修正。",
            "深度分析": "论证强度、材料边界、解释替代性和可迁移性。",
        },
        "recommended_subsections": {
            "数据与任务定义": ["材料范围", "选择标准", "案例或语料边界"],
            "方法主线": ["理论框架", "概念区分", "论证路径"],
            "关键结果": ["核心解释性发现", "概念贡献"],
            "深度分析": ["论证强度", "替代解释", "材料边界"],
        },
    },
    "survey_or_review": {
        "section_semantics": {
            "研究问题": "综述试图整理的领域问题、争议或知识缺口。",
            "数据与任务定义": "纳入文献范围、检索/筛选标准和综述对象。",
            "方法主线": "分类体系、综述组织方式和证据综合逻辑，不写成单篇方法架构。",
            "关键结果": "领域共识、分歧、趋势、代表性方向和开放问题。",
            "深度分析": "综述覆盖的盲区、分类体系的解释力和未来研究机会。",
        },
        "recommended_subsections": {
            "数据与任务定义": ["综述范围", "纳入/排除标准", "文献覆盖"],
            "方法主线": ["分类体系", "方法谱系", "证据组织方式"],
            "关键结果": ["代表性方向", "共识与分歧", "开放问题"],
            "深度分析": ["分类体系的局限", "未覆盖区域", "后续研究机会"],
        },
    },
}


def note_quality_structural_sections() -> tuple[str, ...]:
    text = (SKILL_ROOT / "references" / "note-quality.md").read_text(encoding="utf-8")
    start = text.index("The note should usually include:")
    end = text.index("For non-trivial papers", start)
    sections: list[str] = []
    for line in text[start:end].splitlines():
        line = line.strip()
        if line.startswith("- `") and line.endswith("`"):
            sections.append(line.removeprefix("- `").removesuffix("`"))
    return tuple(sections)


def pdf_contract_docs() -> dict[str, str]:
    docs = {
        doc_name: (PROJECT_ROOT / doc_name).read_text(encoding="utf-8")
        for doc_name in PDF_CONTRACT_DOCS
    }
    docs.update(
        {
            f"skills/deeppapernote/references/{path.name}": path.read_text(encoding="utf-8")
            for path in sorted((SKILL_ROOT / "references").glob("*.md"))
        }
    )
    return docs


def allows_banned_pdf_fallback(text: str, phrase: str) -> bool:
    start = text.find(phrase)
    while start != -1:
        context = text[max(0, start - 80) : start]
        if not any(negation in context for negation in PDF_FAIL_CLOSED_NEGATIONS):
            return True
        start = text.find(phrase, start + len(phrase))
    return False


def test_lint_required_sections_use_canonical_contract() -> None:
    assert tuple(REQUIRED_SECTIONS) == NOTE_REQUIRED_SECTIONS


def test_bundle_required_sections_use_canonical_contract() -> None:
    synthesis = bundle(metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={})

    assert tuple(synthesis["writing_contract"]["must_include_sections"]) == NOTE_REQUIRED_SECTIONS


def test_bundle_paper_type_contracts_use_canonical_enum() -> None:
    synthesis = bundle(
        metadata={},
        evidence_wrapper={"summary": {"paper_type": "benchmark_or_dataset"}},
        figures_wrapper={},
        assets_wrapper={},
    )
    writing_contract = synthesis["writing_contract"]

    assert tuple(writing_contract["contracts_by_paper_type"]) == PAPER_TYPE_VALUES
    assert (
        tuple(writing_contract["paper_type_selection"]["allowed_paper_types"])
        == PAPER_TYPE_VALUES
    )
    assert writing_contract["paper_type_selection"]["source_of_truth"] == "note_plan.paper_type"
    assert writing_contract["paper_type_selection"]["suggested_paper_type_role"] == "none"


def test_bundle_paper_type_contracts_expose_exact_section_profiles() -> None:
    synthesis = bundle(metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={})
    contracts = synthesis["writing_contract"]["contracts_by_paper_type"]

    assert tuple(EXPECTED_PAPER_TYPE_SECTION_PROFILES) == PAPER_TYPE_VALUES
    for paper_type, expected_profile in EXPECTED_PAPER_TYPE_SECTION_PROFILES.items():
        typed_contract = contracts[paper_type]
        assert typed_contract["section_semantics"] == expected_profile["section_semantics"]
        assert (
            typed_contract["recommended_subsections"]
            == expected_profile["recommended_subsections"]
        )
        assert typed_contract["boundary_questions"]


def test_bundle_exposes_exact_note_plan_types_and_grounding_command() -> None:
    writing_contract = bundle(
        metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={}
    )["writing_contract"]
    note_plan_contract = writing_contract["note_plan_contract"]

    assert note_plan_contract["field_types"] == {
        **{field: "string" for field in NOTE_PLAN_STRING_FIELDS},
        **{field: "array" for field in NOTE_PLAN_LIST_FIELDS},
    }
    assert note_plan_contract["required_field_checks"] == {
        "string": {"non_empty": True},
        "array": {"non_empty": True},
    }
    analysis_contract = writing_contract["analysis_coverage_contract"]
    assert analysis_contract["central_claim_field_types"] == {
        "claim": "string",
        "supporting_evidence": "array",
        "what_it_actually_proves": "string",
        "what_it_does_not_prove": "string",
    }
    assert analysis_contract["central_claim_required_field_checks"] == (
        note_plan_contract["required_field_checks"]
    )
    assert writing_contract["grounding_contract"]["lint_command"] == (
        "scripts/lint_grounding.py --note-plan ... "
        "--source-manifest ... --bundle-json ... --figure-decisions ..."
    )


def test_note_plan_validators_consume_required_field_checks(
    tmp_path: Path, monkeypatch
) -> None:
    plan = {
        **{field: "" for field in NOTE_PLAN_STRING_FIELDS},
        **{field: [] for field in NOTE_PLAN_LIST_FIELDS},
    }
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    _, lint_issues = inspect_note_plan(plan_path)
    grounding_issues = validate_note_plan(plan, {})
    assert any(issue.endswith("_empty") for issue in lint_issues)
    assert any(issue["code"] == "note_plan_required_field_empty" for issue in grounding_issues)

    monkeypatch.setitem(
        WRITING_CONTRACT_RULES,
        "note_plan_required_field_checks",
        {"string": {"non_empty": False}, "array": {"non_empty": False}},
    )
    _, lint_issues = inspect_note_plan(plan_path)
    grounding_issues = validate_note_plan(plan, {})
    assert not any(issue.endswith("_empty") for issue in lint_issues)
    assert not any(
        issue["code"] == "note_plan_required_field_empty" for issue in grounding_issues
    )


def test_central_claim_validators_consume_analysis_contract(monkeypatch) -> None:
    analysis_contract = WRITING_CONTRACT_RULES["analysis_coverage_contract"]
    monkeypatch.setitem(
        analysis_contract,
        "central_claim_fields",
        (*analysis_contract["central_claim_fields"], "new_required_field"),
    )
    monkeypatch.setitem(
        analysis_contract,
        "central_claim_field_types",
        {
            "claim": "string",
            "supporting_evidence": "array",
            "what_it_actually_proves": "string",
            "what_it_does_not_prove": "string",
            "new_required_field": "string",
        },
    )
    monkeypatch.setitem(
        analysis_contract,
        "central_claim_required_field_checks",
        {"string": {"non_empty": True}, "array": {"non_empty": True}},
    )
    claim = {
        "claim": "claim",
        "supporting_evidence": [{"section_id": "sec:result"}],
        "what_it_actually_proves": "supported result",
        "what_it_does_not_prove": "bounded result",
    }

    lint_issues = inspect_central_claims_plan([claim])
    grounding_issues = validate_central_claims(
        {"central_claims": [claim]}, {"sec:result"}, 1
    )
    assert "planning_central_claims_new_required_field_missing" in lint_issues
    assert any(
        issue["code"] == "central_claim_required_field_missing"
        and issue["field"] == "new_required_field"
        for issue in grounding_issues
    )


def test_bundle_exposes_depth_and_figure_decision_contracts_without_old_inputs() -> None:
    synthesis = bundle(
        metadata={},
        evidence_wrapper={"evidence_pack": {"section_texts": {"method": "legacy"}}},
        figures_wrapper={},
        assets_wrapper={},
        source_manifest={"raw_sections_path": "/tmp/raw_sections.jsonl"},
        figure_decisions_wrapper={"decisions": []},
    )
    writing_contract = synthesis["writing_contract"]

    for old_key in WRITING_CONTRACT_RULES["excluded_model_input_fields"]:
        assert old_key not in synthesis
    assert writing_contract["grounding_contract"]["excluded_model_input_fields"] == list(
        WRITING_CONTRACT_RULES["excluded_model_input_fields"]
    )
    assert (
        writing_contract["grounding_contract"]["note_plan_depth_requirements"][
            "required_section_focus_min_chars"
        ]
        >= 20
    )
    assert writing_contract["figure_table_contract"]["usable_insert_candidate"] == {
        "kinds": ["figure", "table"],
        "visual_quality_status": "usable_candidate",
        "requires_source_image_path": True,
    }
    assert "materialization_blocked" in writing_contract["figure_table_contract"][
        "allowed_usable_placeholder_reasons"
    ]
    assert writing_contract["analysis_coverage_contract"]["central_claim_fields"] == [
        "claim",
        "supporting_evidence",
        "what_it_actually_proves",
        "what_it_does_not_prove",
    ]


def test_figure_decision_script_consumes_canonical_contract() -> None:
    decision_script = (
        SKILL_ROOT / "scripts" / "plan_figure_table_decisions.py"
    ).read_text(encoding="utf-8")

    assert DECISION_VALUES == set(WRITING_CONTRACT_RULES["figure_decision_values"])
    assert INSERTABLE_KINDS == set(
        WRITING_CONTRACT_RULES["usable_insert_candidate"]["kinds"]
    )
    assert "from contracts import WRITING_CONTRACT_RULES" in decision_script
    assert 'DECISION_VALUES = {"insert"' not in decision_script
    assert 'INSERTABLE_KINDS = {"figure"' not in decision_script


def test_bundle_exposes_complete_canonical_figure_contract() -> None:
    figure_contract = bundle(
        metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={}
    )["writing_contract"]["figure_table_contract"]

    assert figure_contract == {
        "placeholder_first": True,
        "visual_quality_gate": "fail_closed",
        "decision_table_required": True,
        "decision_values": list(WRITING_CONTRACT_RULES["figure_decision_values"]),
        "usable_insert_candidate": {
            "kinds": list(
                WRITING_CONTRACT_RULES["usable_insert_candidate"]["kinds"]
            ),
            "visual_quality_status": WRITING_CONTRACT_RULES[
                "usable_insert_candidate"
            ]["visual_quality_status"],
            "requires_source_image_path": WRITING_CONTRACT_RULES[
                "usable_insert_candidate"
            ]["requires_source_image_path"],
        },
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
    }


def test_figure_protocol_docs_keep_single_owners() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    references = SKILL_ROOT / "references"
    placement = (references / "figure-placement.md").read_text(encoding="utf-8")
    final_writing = (references / "final-writing.md").read_text(encoding="utf-8")
    obsidian_format = (references / "obsidian-format.md").read_text(encoding="utf-8")

    assert "placeholder-first figures" in skill
    assert "writing_contract.figure_table_contract" in skill
    assert "complete figure/table decision table" in skill
    assert "grounding and final-note figure gates" in skill
    assert "Formal Save materializes the selected image" in skill
    for duplicate in (
        "needs_visual_quality_check",
        "reject_visual_quality",
        "asset_candidate_missing",
        "relative_markdown_embed",
        "write_obsidian_note.py --figure-decisions",
    ):
        assert duplicate not in skill

    assert "writing_contract.figure_table_contract" in placement
    assert "identity match" in placement
    assert "visual usability" in placement
    assert "asset_candidate_missing" in placement
    for duplicate in (
        "kept_placeholder_visual_defect",
        "kept_placeholder_materialization_blocked",
        "relative_markdown_embed",
        "write_obsidian_note.py --figure-decisions",
        "> [!figure]",
        "```md",
        "same note-generation task",
        "text-only note first",
        "final response",
    ):
        assert duplicate not in placement

    assert "figure-placement.md" in final_writing
    assert "obsidian-format.md" in final_writing
    for duplicate in (
        "usable_candidate",
        "needs_visual_quality_check",
        "reject_visual_quality",
        "asset_candidate_missing",
        "relative_markdown_embed",
        "write_obsidian_note.py",
        "> [!figure]",
        "![[.../images",
    ):
        assert duplicate not in final_writing

    assert "> [!figure]" in obsidian_format
    assert "![[Research/Papers/DeepPaperNote/paper_slug/images/" in obsidian_format
    assert "*论文原图编号：Fig. 2。" in obsidian_format


def test_paper_types_doc_uses_typed_profiles_without_legacy_common_subheadings() -> None:
    text = (PROJECT_ROOT / "skills" / "deeppapernote" / "references" / "paper-types.md").read_text(encoding="utf-8")

    assert "Common subheadings" not in text
    assert "unless a section truly does not apply" not in text
    assert "section_semantics" in text
    assert "recommended_subsections" in text
    assert "fixed top-level sections" in text or "12 top-level sections" in text


def test_note_quality_structural_sections_match_canonical_contract() -> None:
    assert note_quality_structural_sections() == NOTE_REQUIRED_SECTIONS


def test_skill_owns_note_plan_creation_and_grounding_gates() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = text.split("## Workflow", 1)[1].split("## Core Execution Contract", 1)[0]
    non_negotiable_rules = text.split("Non-negotiable rules:", 1)[1].split(
        "Reference usage policy:", 1
    )[0]
    model_first_rule = text.split("Model-first rule:", 1)[1].split(
        "The topic references above", 1
    )[0]

    assert workflow.count(
        "create a short JSON `note_plan` that satisfies the generated bundle contract"
    ) == 1
    assert workflow.count(
        "draft from the plan only after the grounding gate passes"
    ) == 1
    assert "lint the final note against the same `note_plan`" in workflow
    assert NOTE_PLAN_PROTOCOL_RE.search(non_negotiable_rules) is None
    assert NOTE_PLAN_PROTOCOL_RE.search(model_first_rule) is None


def test_skill_owns_formal_save_state_policy() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    obsidian_format_text = (SKILL_ROOT / "references" / "obsidian-format.md").read_text(
        encoding="utf-8"
    )

    marker = "Formal Save states:"
    assert skill_text.count(marker) == 1
    assert marker not in obsidian_format_text
    assert "After such a refusal" not in skill_text
    assert "do not switch to workspace" in skill_text
    assert "explicitly chooses not to use a vault" in skill_text
    for policy_phrase in ("permission escalation", "workspace fallback", "explicit user consent"):
        assert policy_phrase not in obsidian_format_text


def test_topic_references_keep_separate_note_plan_responsibilities() -> None:
    evidence_first = (SKILL_ROOT / "references" / "evidence-first.md").read_text(
        encoding="utf-8"
    )
    writing_and_rubric = [
        (SKILL_ROOT / "references" / doc_name).read_text(encoding="utf-8")
        for doc_name in ("final-writing.md", "note-quality.md")
    ]

    assert "Recommended shape:" in evidence_first
    assert "scripts/lint_grounding.py --note-plan" in evidence_first
    for text in writing_and_rubric:
        assert NOTE_PLAN_PROTOCOL_RE.search(text) is None


def test_normal_execution_docs_do_not_force_broad_reference_reads() -> None:
    for doc_name in REFERENCE_ROUTING_DOCS:
        text = (PROJECT_ROOT / doc_name).read_text(encoding="utf-8")

        assert "Read [references/" not in text
        assert "Use [references/" not in text

    skill_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "SKILL.md").read_text(encoding="utf-8")
    assert "not a default reading checklist" in skill_text


def test_normal_execution_docs_require_obsidian_yaml_frontmatter() -> None:
    skill_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "SKILL.md").read_text(encoding="utf-8")
    final_writing_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )

    for text in (skill_text, final_writing_text):
        assert "Obsidian YAML" in text
        assert "above the `#` title heading" in text
        assert "`tags`" in text
        assert "`aliases`" in text


def test_final_writing_defines_fixed_core_info_schema() -> None:
    final_writing_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )
    obsidian_format_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "references" / "obsidian-format.md").read_text(
        encoding="utf-8"
    )

    required_fields = [
        "标题",
        "标题翻译",
        "作者",
        "机构",
        "发表时间",
        "发表渠道",
        "DOI",
        "arXiv",
        "论文链接",
        "代码 / 项目",
        "数据 / 资源",
        "论文类型",
    ]

    for text in (final_writing_text, obsidian_format_text):
        assert "Core info field schema" in text
        assert "only the following fields" in text
        assert "no free prose" in text
        for field in required_fields:
            assert f"`{field}`" in text


def test_final_writing_requires_tables_for_central_quantitative_comparisons() -> None:
    final_writing_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )

    assert "three or more compared systems" in final_writing_text
    assert "use a compact Markdown table" in final_writing_text
    assert "loose bullet list" in final_writing_text


def test_evidence_first_is_only_note_plan_json_example() -> None:
    json_examples: dict[str, list[str]] = {}
    for doc_name in NOTE_PLAN_REFERENCE_DOCS:
        text = (SKILL_ROOT / "references" / doc_name).read_text(encoding="utf-8")
        matches = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
        if matches:
            json_examples[doc_name] = matches

    assert tuple(json_examples) == ("evidence-first.md",)
    assert len(json_examples["evidence-first.md"]) == 1


def test_evidence_first_note_plan_example_matches_lint_contract() -> None:
    text = (SKILL_ROOT / "references" / "evidence-first.md").read_text(
        encoding="utf-8"
    )
    match = re.search(r"Recommended shape:\n\n```json\n(.*?)\n```", text, flags=re.DOTALL)

    assert match is not None
    example = json.loads(match.group(1))

    assert tuple(example.keys()) == NOTE_PLAN_REQUIRED_FIELDS
    assert all(isinstance(example[field], str) for field in NOTE_PLAN_REQUIRED_FIELDS[:3])
    assert all(isinstance(example[field], list) for field in NOTE_PLAN_REQUIRED_FIELDS[3:])
    assert example["paper_type"] in PAPER_TYPE_VALUES
    assert example["section_plan"]


def test_pdf_contract_docs_do_not_allow_degraded_finished_notes() -> None:
    offending: list[str] = []
    for doc_name, text in pdf_contract_docs().items():
        normalized = text.lower()
        for phrase in PDF_FAIL_CLOSED_BANNED_PHRASES:
            if allows_banned_pdf_fallback(normalized, phrase):
                offending.append(f"{doc_name}: {phrase}")

    assert offending == []


def test_pdf_contract_banned_phrase_matcher_catches_allowed_fallbacks() -> None:
    for phrase in PDF_FAIL_CLOSED_BANNED_PHRASES:
        assert allows_banned_pdf_fallback(f"you may produce a {phrase}.", phrase)

    assert not allows_banned_pdf_fallback(
        "ask for OCR or a better source rather than finishing a degraded note.",
        "degraded note",
    )


def test_pdf_contract_docs_try_supported_acquisition_before_stopping() -> None:
    skill_text = (PROJECT_ROOT / "skills" / "deeppapernote" / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh_text = (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    source_priority = skill_text.index("## Tool and Source Priority")
    stop_policy = skill_text.index("If PDF or evidence quality is insufficient")
    assert source_priority < stop_policy

    for required_source in (
        "local PDF path given by the user",
        "local Zotero item and local Zotero attachment if available",
        "DOI and publisher metadata",
        "arXiv or open-access PDF sources",
    ):
        assert required_source in skill_text[source_priority:stop_policy]

    assert "A title, DOI, URL, arXiv ID, or local PDF all work." in readme_text
    assert "标题、DOI、URL、本地 PDF 都可以" in readme_zh_text


def test_regression_workflow_documents_acquisition_identity_audit_contract() -> None:
    texts = [
        (PROJECT_ROOT / "evals" / "regression-workflow.md").read_text(encoding="utf-8"),
        (PROJECT_ROOT / "evals" / "regression-workflow-zh.md").read_text(encoding="utf-8"),
    ]

    for text in texts:
        for artifact in (
            "resolve",
            "metadata",
            "fetch",
            "canonical identity",
            "repair trace",
        ):
            assert artifact in text.lower()
        for verdict in ("pass", "partial", "fail", "unknown"):
            assert f"`{verdict}`" in text
        for scenario in (
            "repaired identity",
            "accepted-with-warnings identity",
            "repair-exhausted failure",
            "equivalent manifestation",
        ):
            assert scenario in text.lower()
        for downstream_failure in (
            "wrong identity",
            "wrong PDF",
            "metadata contradiction",
            "missing source evidence",
            "broken path",
            "citation damage",
        ):
            assert downstream_failure.lower() in text.lower()
        assert "`architectural_improvement_only`" in text
        assert "note-visible" in text.lower()
