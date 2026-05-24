from __future__ import annotations

import json
import re
from pathlib import Path

from build_synthesis_bundle import bundle
from contracts import NOTE_REQUIRED_SECTIONS, PAPER_TYPE_VALUES
from lint_note import REQUIRED_SECTIONS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTE_PLAN_REFERENCE_DOCS = (
    "workflow.md",
    "evidence-first.md",
    "final-writing.md",
    "model-synthesis.md",
    "note-quality.md",
)
NOTE_PLAN_REQUIRED_FIELDS = (
    "paper_type",
    "paper_type_rationale",
    "dominant_domain",
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
    "section_plan",
)
REFERENCE_ROUTING_DOCS = (
    "SKILL.md",
    "references/model-synthesis.md",
)
PDF_CONTRACT_DOCS = (
    "SKILL.md",
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
    text = (PROJECT_ROOT / "references" / "note-quality.md").read_text(encoding="utf-8")
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
            f"references/{path.name}": path.read_text(encoding="utf-8")
            for path in sorted((PROJECT_ROOT / "references").glob("*.md"))
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

    assert "evidence" not in synthesis
    assert "candidate_chunks" not in synthesis
    assert "section_texts" not in synthesis
    assert "summary" not in synthesis
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


def test_paper_types_doc_uses_typed_profiles_without_legacy_common_subheadings() -> None:
    text = (PROJECT_ROOT / "references" / "paper-types.md").read_text(encoding="utf-8")

    assert "Common subheadings" not in text
    assert "unless a section truly does not apply" not in text
    assert "section_semantics" in text
    assert "recommended_subsections" in text
    assert "fixed top-level sections" in text or "12 top-level sections" in text


def test_note_quality_structural_sections_match_canonical_contract() -> None:
    assert note_quality_structural_sections() == NOTE_REQUIRED_SECTIONS


def test_note_plan_docs_make_json_file_canonical() -> None:
    for doc_name in NOTE_PLAN_REFERENCE_DOCS:
        text = (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8")

        assert "canonical" in text.lower()
        assert "short JSON" in text
        assert "scripts/lint_note.py --plan-file ..." in text
        assert "<note>.plan.json" in text
        assert "*_note_plan.json" in text


def test_note_plan_xml_mentions_are_display_only() -> None:
    for doc_name in NOTE_PLAN_REFERENCE_DOCS:
        lines = (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8").splitlines()

        for line in lines:
            if "<note_plan>" in line:
                normalized = line.lower()
                assert "interactive" in normalized
                assert "display-only" in normalized


def test_note_plan_docs_do_not_offer_xml_or_temporary_files_as_alternatives() -> None:
    combined = "\n".join(
        (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8")
        for doc_name in NOTE_PLAN_REFERENCE_DOCS
    )

    note_plan_tag = "`<note_" + "plan>...</note_" + "plan>`"
    conjunction = "o" + "r"
    banned_phrases = (
        "equivalent temporary " + "planning file",
        "equivalent temporary " + "plan file",
        "dynamic internal note " + "plan",
        "planning block such as " + note_plan_tag,
        "planning artifact such as " + note_plan_tag,
        "- a compact " + note_plan_tag + " block\n- " + conjunction,
    )
    for phrase in banned_phrases:
        assert phrase not in combined


def test_normal_execution_docs_do_not_force_broad_reference_reads() -> None:
    for doc_name in REFERENCE_ROUTING_DOCS:
        text = (PROJECT_ROOT / doc_name).read_text(encoding="utf-8")

        assert "Read [references/" not in text
        assert "Use [references/" not in text

    skill_text = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    model_synthesis_text = (PROJECT_ROOT / "references" / "model-synthesis.md").read_text(
        encoding="utf-8"
    )

    assert "not a default reading checklist" in skill_text
    assert "not a second router" in model_synthesis_text


def test_normal_execution_docs_require_obsidian_yaml_frontmatter() -> None:
    skill_text = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    final_writing_text = (PROJECT_ROOT / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )

    for text in (skill_text, final_writing_text):
        assert "Obsidian YAML" in text
        assert "above the `#` title heading" in text
        assert "`tags`" in text
        assert "`aliases`" in text


def test_final_writing_defines_fixed_core_info_schema() -> None:
    final_writing_text = (PROJECT_ROOT / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )
    obsidian_format_text = (PROJECT_ROOT / "references" / "obsidian-format.md").read_text(
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
    final_writing_text = (PROJECT_ROOT / "references" / "final-writing.md").read_text(
        encoding="utf-8"
    )

    assert "three or more compared systems" in final_writing_text
    assert "use a compact Markdown table" in final_writing_text
    assert "loose bullet list" in final_writing_text


def test_evidence_first_note_plan_example_matches_lint_contract() -> None:
    text = (PROJECT_ROOT / "references" / "evidence-first.md").read_text(encoding="utf-8")

    assert "```xml" not in text
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
    skill_text = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow_text = (PROJECT_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
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

    assert (
        "Accepted inputs: title, DOI, URL, arXiv ID, local PDF path, Zotero item key."
        in workflow_text
    )
    assert "Acquire the best available PDF" in workflow_text
    assert "stop and report the blocked stage honestly" in workflow_text
    assert "A title, DOI, URL, arXiv ID, or local PDF all work." in readme_text
    assert "标题、DOI、URL、本地 PDF 都可以" in readme_zh_text
