#!/usr/bin/env python3
"""Scaffolded JSON contracts for the paper-deep-notes core workflow."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TypedDict

from localization import note_schema, normalize_output_language, required_sections

NOTE_REQUIRED_SECTIONS: tuple[str, ...] = (
    "核心信息",
    "原文摘要翻译",
    "创新点",
    "一句话总结",
    "研究问题",
    "数据与任务定义",
    "方法主线",
    "关键结果",
    "深度分析",
    "局限",
    "我的笔记",
    "引用",
)

def note_required_sections(language: str | None = None) -> tuple[str, ...]:
    return required_sections(language)

PAPER_TYPE_VALUES: tuple[str, ...] = (
    "AI_method",
    "benchmark_or_dataset",
    "clinical_or_psychology_empirical",
    "humanities_or_social_science",
    "survey_or_review",
)

NOTE_PLAN_STRING_FIELDS: tuple[str, ...] = (
    "paper_type",
    "paper_type_rationale",
    "dominant_domain",
)

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
    "section_plan",
)

NOTE_PLAN_REQUIRED_FIELDS: tuple[str, ...] = NOTE_PLAN_STRING_FIELDS + NOTE_PLAN_LIST_FIELDS
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

PAPER_TYPE_SECTION_PROFILES: dict[str, dict[str, dict[str, Any]]] = {
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

PAPER_TYPE_CONTRACTS: dict[str, dict[str, Any]] = {
    "AI_method": {
        "paper_type": "AI_method",
        "reader_lens": "面向能复现方法机制的技术读者",
        "section_focus": [
            "问题设置",
            "方法机制",
            "训练/推理流程",
            "关键公式",
            "比较基线",
            "消融与失败边界",
        ],
        "required_checks": ["需要说明机制流程、关键公式、实验设计、消融含义和失败边界。"],
        "formula_rules": ["仅保留理解方法必需的 1 到 3 个关键公式，并解释其工程含义。"],
        "avoid_rules": ["不要把非 AI_method 论文强行改写成模型架构。"],
        "boundary_questions": [
            "核心机制的收益由哪个实验或消融支撑，而不是只由主结果暗示？",
            "哪些比较只能证明在当前数据、基线、算力或协议下有效，不能外推到通用场景？",
            "论文是否给出失败、退化、不稳定或成本上升的证据；如果没有，结论边界是什么？",
        ],
        **PAPER_TYPE_SECTION_PROFILES["AI_method"],
        "mechanism_flow_contract": {
            "apply_when_paper_type_in": ["AI_method"],
            "required_step_count": "3_to_4",
            "required_step_fields": ["input", "operation", "output_destination"],
        },
    },
    "benchmark_or_dataset": {
        "paper_type": "benchmark_or_dataset",
        "reader_lens": "面向要判断 benchmark/dataset 可用性和偏差边界的研究者",
        "section_focus": [
            "任务拆分",
            "数据来源与构建流程",
            "标注协议",
            "评测指标",
            "覆盖范围与偏差",
            "样本统计与数据开放限制",
        ],
        "required_checks": [
            "需要说明数据来源、构建/标注流程、评测指标、基线表现、样本统计、数据开放或隐私限制和适用边界。"
        ],
        "formula_rules": ["仅保留核心评测指标、采样规则或划分定义。"],
        "avoid_rules": ["不要把数据构建流程写成模型 pipeline。"],
        "boundary_questions": [
            "这个 benchmark/dataset 实际测量的构念是什么，哪些能力只是间接近似？",
            "任务、标签、采样、过滤或评测协议会引入哪些覆盖缺口或偏差？",
            "基线结果证明了评测集有区分度，还是只证明某类模型适应该协议？",
            "样本时长、语料长度、人口统计、类别分布、数据可访问性或隐私限制如何影响复现和外推？",
        ],
        **PAPER_TYPE_SECTION_PROFILES["benchmark_or_dataset"],
    },
    "clinical_or_psychology_empirical": {
        "paper_type": "clinical_or_psychology_empirical",
        "reader_lens": "面向关注临床/心理学样本、变量关系和外推边界的研究读者",
        "section_focus": [
            "样本来源",
            "纳排标准",
            "变量或量表",
            "分析管线",
            "效应量与不确定性",
            "样本统计、伦理和数据可访问性",
        ],
        "required_checks": [
            "需要区分相关、预测、组间差异和因果解释，说明样本统计、伦理/隐私约束与外推边界。"
        ],
        "formula_rules": ["仅保留核心统计模型、效应量、置信区间或量表定义。"],
        "avoid_rules": ["不要把相关性、预测性能或组间差异写成未经证明的因果结论。"],
        "boundary_questions": [
            "样本来源、纳排标准、测量工具和标注流程如何限制外推？",
            "结果支持相关、预测、组间差异还是因果解释；不要越过论文设计能证明的范围。",
            "临床或心理学意义是否依赖未观测混杂、量表阈值、文本/语音缺失或场景约束？",
            "样本构成、数据缺失、隐私限制或材料不可公开会怎样限制复现与再分析？",
        ],
        **PAPER_TYPE_SECTION_PROFILES["clinical_or_psychology_empirical"],
    },
    "humanities_or_social_science": {
        "paper_type": "humanities_or_social_science",
        "reader_lens": "面向关注理论框架、材料解释和论证结构的研究读者",
        "section_focus": ["研究对象", "材料来源", "理论框架", "论证路径", "概念贡献", "解释边界"],
        "required_checks": ["需要区分作者论证、材料证据、规范性判断和实验事实。"],
        "formula_rules": ["通常不强行保留公式；仅保留核心形式化定义或编码规则。"],
        "avoid_rules": ["不要把规范性判断、文本解释或案例分析写成实验事实。"],
        "boundary_questions": [
            "作者的解释依赖哪些材料、案例或理论前提？",
            "是否存在同样能解释材料的替代解释，论文如何排除或没有排除？",
            "哪些结论是概念贡献或规范性判断，而不是可直接当作经验事实？",
        ],
        **PAPER_TYPE_SECTION_PROFILES["humanities_or_social_science"],
    },
    "survey_or_review": {
        "paper_type": "survey_or_review",
        "reader_lens": "面向需要梳理综述脉络、分类体系和证据边界的研究读者",
        "section_focus": [
            "综述范围",
            "纳入排除标准",
            "主题分类",
            "方法谱系",
            "共识与分歧",
            "开放问题",
        ],
        "required_checks": ["需要说明综述范围、文献选择、分类体系、共识分歧和开放问题。"],
        "formula_rules": ["仅保留分类轴、纳入排除准则、证据汇总规则或 meta-analysis 统计量。"],
        "avoid_rules": ["不要把综述中的代表性结论写成作者自己完成的单项实验结果。"],
        "boundary_questions": [
            "检索范围、纳入排除标准或分类轴会遗漏哪些研究路线？",
            "综述给出的是领域共识、作者分类，还是尚未解决的分歧？",
            "哪些趋势结论来自覆盖范围内的文献分布，不能直接当作技术成熟度判断？",
        ],
        **PAPER_TYPE_SECTION_PROFILES["survey_or_review"],
    },
}

PAPER_TYPE_CONTRACTS_EN: dict[str, dict[str, Any]] = {
    "AI_method": {
        "paper_type": "AI_method",
        "reader_lens": "A technical reader who may need to reproduce the method and its mechanism.",
        "section_focus": ["problem setting", "method mechanism", "training or inference flow", "key equations", "strong baselines", "ablations and failure boundaries"],
        "required_checks": ["Explain the mechanism flow, essential equations, experimental design, what the ablations establish, and the failure boundary."],
        "formula_rules": ["Keep only the one to three equations needed to understand the method and explain their engineering meaning."],
        "avoid_rules": ["Do not force a non-method paper into a model-architecture narrative."],
        "boundary_questions": [
            "Which experiment or ablation supports the claimed benefit of the core mechanism?",
            "Which comparisons apply only under the reported data, baselines, compute, or protocol?",
            "What evidence shows failure, degradation, instability, or rising cost; if none is reported, what remains unproven?",
        ],
        "section_semantics": {
            "Research Questions": "The specific technical problem and the shortcomings of existing methods.",
            "Data and Task Definition": "Datasets, inputs and outputs, evaluation tasks, and experimental settings.",
            "Method": "Model, algorithm, training, and inference mechanisms.",
            "Key Results": "Main results, strong baselines, ablations, and decisive numbers.",
            "Deep Analysis": "Why the method works, where it is fragile, and the cost of reproduction or extension.",
        },
        "recommended_subsections": {
            "Method": ["Analytical Flow", "Model Architecture", "Training Objective", "Inference and Sampling", "Implementation Details"],
            "Key Results": ["Main Results and Strong Baselines", "What the Ablations Establish", "Failure or Unstable Settings"],
            "Deep Analysis": ["Why It Works", "Complexity and Scalability", "Reproduction Notes"],
        },
        "mechanism_flow_contract": {"apply_when_paper_type_in": ["AI_method"], "required_step_count": "3_to_4", "required_step_fields": ["input", "operation", "output_destination"]},
    },
    "benchmark_or_dataset": {
        "paper_type": "benchmark_or_dataset",
        "reader_lens": "A researcher assessing whether a benchmark or dataset is useful and where it is biased.",
        "section_focus": ["task decomposition", "data sources and construction", "annotation protocol", "evaluation metrics", "coverage and bias", "sample statistics and access limits"],
        "required_checks": ["Explain sources, construction or annotation, metrics, baselines, sample statistics, access or privacy constraints, and applicability."],
        "formula_rules": ["Keep only essential metrics, sampling rules, or split definitions."],
        "avoid_rules": ["Do not describe data construction as a model pipeline."],
        "boundary_questions": [
            "What construct does the resource actually measure, and which capabilities are only proxies?",
            "Which coverage gaps or biases follow from its tasks, labels, sampling, filtering, or evaluation protocol?",
            "Do baseline results demonstrate discrimination, or only adaptation to this protocol?",
            "How do sample composition, access, and privacy limits affect reproduction and generalization?",
        ],
        "section_semantics": {
            "Research Questions": "The evaluation or data gap the resource is designed to address.",
            "Data and Task Definition": "Sources, task splits, labels, and sample scope.",
            "Method": "Construction, filtering, annotation, and evaluation protocol—not a model pipeline.",
            "Key Results": "Baseline performance, difficulty, coverage, and bias.",
            "Deep Analysis": "What the resource measures and what it cannot represent.",
        },
        "recommended_subsections": {
            "Data and Task Definition": ["Data Sources", "Task Splits", "Annotation and Filtering"],
            "Method": ["Construction Process", "Evaluation Protocol", "Baseline Setup"],
            "Key Results": ["Baseline Performance", "Difficulty Distribution", "Coverage and Bias"],
            "Deep Analysis": ["What It Actually Measures", "Applicability Boundary"],
        },
    },
    "clinical_or_psychology_empirical": {
        "paper_type": "clinical_or_psychology_empirical",
        "reader_lens": "A research reader focused on samples, variable relationships, uncertainty, and generalization.",
        "section_focus": ["sample source", "inclusion and exclusion", "variables and instruments", "analysis pipeline", "effect sizes and uncertainty", "ethics, access, and generalization"],
        "required_checks": ["Distinguish association, prediction, group difference, and causal interpretation; report sample, ethics, privacy, and generalization limits."],
        "formula_rules": ["Keep only essential statistical models, effect sizes, intervals, or instrument definitions."],
        "avoid_rules": ["Do not turn association, prediction, or group differences into unsupported causal claims."],
        "boundary_questions": [
            "How do recruitment, eligibility, measurement, and annotation constrain generalization?",
            "Does the design support association, prediction, group difference, or causality?",
            "Does the interpretation depend on unobserved confounding, thresholds, missingness, or setting?",
            "How do sample composition, missing data, privacy, and unavailable materials constrain reproduction?",
        ],
        "section_semantics": {
            "Research Questions": "The clinical, psychological, or behavioral question, hypothesis, or variable relationship.",
            "Data and Task Definition": "Recruitment, eligibility, variables, instruments, and measurement.",
            "Method": "Study design, grouping, measurement flow, and statistical analysis.",
            "Key Results": "Effects, associations, group differences, uncertainty, and significance.",
            "Deep Analysis": "Interpretation, causal boundary, substantive meaning, and generalization limits.",
        },
        "recommended_subsections": {
            "Data and Task Definition": ["Sample and Eligibility", "Variables and Instruments", "Measurement Process"],
            "Method": ["Study Design", "Analysis Model", "Primary Comparisons"],
            "Key Results": ["Primary Effects", "Uncertainty and Significance", "Clinical or Psychological Interpretation"],
            "Deep Analysis": ["Causal Interpretation Boundary", "Generalization Limits"],
        },
    },
    "humanities_or_social_science": {
        "paper_type": "humanities_or_social_science",
        "reader_lens": "A reader evaluating theoretical framing, material interpretation, and argument structure.",
        "section_focus": ["object of study", "materials", "theoretical framework", "argument path", "conceptual contribution", "interpretive boundary"],
        "required_checks": ["Distinguish the author's argument, material evidence, normative judgment, and empirical fact."],
        "formula_rules": ["Do not force equations; retain only essential formal definitions or coding rules."],
        "avoid_rules": ["Do not present normative judgment, textual interpretation, or case analysis as experimental fact."],
        "boundary_questions": [
            "Which materials, cases, or theoretical premises support the interpretation?",
            "What alternative explanations fit the same material, and how are they addressed?",
            "Which conclusions are conceptual or normative rather than directly empirical?",
        ],
        "section_semantics": {
            "Research Questions": "The social, cultural, historical, institutional, or theoretical problem.",
            "Data and Task Definition": "Materials, cases, texts, interviews, archives, or corpus scope—not an ML task.",
            "Method": "Theoretical framework, conceptual distinctions, and argument path.",
            "Key Results": "Interpretive findings, conceptual contribution, or revision of prior views.",
            "Deep Analysis": "Argument strength, material limits, alternative explanations, and transferability.",
        },
        "recommended_subsections": {
            "Data and Task Definition": ["Material Scope", "Selection Criteria", "Case or Corpus Boundary"],
            "Method": ["Theoretical Framework", "Conceptual Distinctions", "Argument Path"],
            "Key Results": ["Core Interpretive Findings", "Conceptual Contribution"],
            "Deep Analysis": ["Argument Strength", "Alternative Explanations", "Material Boundary"],
        },
    },
    "survey_or_review": {
        "paper_type": "survey_or_review",
        "reader_lens": "A reader mapping a literature, taxonomy, evidence boundary, and open questions.",
        "section_focus": ["review scope", "inclusion and exclusion", "taxonomy", "method families", "consensus and disagreement", "open questions"],
        "required_checks": ["Explain scope, study selection, taxonomy, consensus, disagreement, and open questions."],
        "formula_rules": ["Keep only classification axes, eligibility rules, evidence-synthesis rules, or meta-analytic statistics."],
        "avoid_rules": ["Do not present findings summarized from the literature as a new experiment by the review authors."],
        "boundary_questions": [
            "Which research routes may be missed by the search scope, eligibility criteria, or taxonomy?",
            "Which statements reflect consensus, author-defined categories, or unresolved disagreement?",
            "Which trends are artifacts of the covered literature and cannot establish technical maturity?",
        ],
        "section_semantics": {
            "Research Questions": "The field problem, controversy, or knowledge gap organized by the review.",
            "Data and Task Definition": "Literature scope, search and screening criteria, and review objects.",
            "Method": "Taxonomy, review organization, and evidence-synthesis logic—not a single method architecture.",
            "Key Results": "Consensus, disagreement, trends, representative directions, and open questions.",
            "Deep Analysis": "Coverage blind spots, explanatory power of the taxonomy, and future opportunities.",
        },
        "recommended_subsections": {
            "Data and Task Definition": ["Review Scope", "Inclusion and Exclusion", "Literature Coverage"],
            "Method": ["Taxonomy", "Method Families", "Evidence Organization"],
            "Key Results": ["Representative Directions", "Consensus and Disagreement", "Open Questions"],
            "Deep Analysis": ["Taxonomy Limits", "Uncovered Areas", "Future Research Opportunities"],
        },
    },
}


def paper_type_contracts(language: str | None = None) -> dict[str, dict[str, Any]]:
    return deepcopy(PAPER_TYPE_CONTRACTS_EN if normalize_output_language(language) == "en" else PAPER_TYPE_CONTRACTS)

WRITING_CONTRACT_RULES: dict[str, Any] = {
    "required_sections": NOTE_REQUIRED_SECTIONS,
    "paper_type_values": PAPER_TYPE_VALUES,
    "note_plan_required_fields": NOTE_PLAN_REQUIRED_FIELDS,
    "note_plan_field_types": NOTE_PLAN_FIELD_TYPES,
    "note_plan_required_field_checks": REQUIRED_FIELD_CHECKS,
    "grounding_required_sections": (
        "研究问题",
        "数据与任务定义",
        "方法主线",
        "关键结果",
        "深度分析",
        "局限",
    ),
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
        "review_status_values": ("pending", "pass", "fail", "repair_requested"),
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
        "final_quality_review_checks": (
            "central_claims_are_supported_by_raw_sections_or_pages",
            "key_experimental_settings_and_numbers_are_present",
            "mechanisms_or_protocol_choices_are_mapped_to_results",
            "comparisons_explain_positioning_against_alternatives",
            "discussion_or_limitation_claims_are_explained_mechanistically",
            "proven_claims_are_separated_from_unproven_or_unvalidated_claims",
            "research_or_engineering_takeaways_are_specific_and_reusable",
            "followup_questions_are_specific_to_replication_or_extension",
        ),
    },
}

def writing_contract_rules(language: str | None = None) -> dict[str, Any]:
    resolved = normalize_output_language(language)
    schema = note_schema(resolved)
    rules = deepcopy(WRITING_CONTRACT_RULES)
    rules["language"] = resolved
    rules["required_sections"] = tuple(schema["sections"].values())
    rules["grounding_required_sections"] = tuple(schema["sections"][key] for key in ("research_questions", "data_and_task", "method", "key_results", "deep_analysis", "limitations"))
    rules["core_info_fields"] = tuple(schema["core_info_fields"])
    rules["figure_labels"] = dict(schema["figure_labels"])
    rules["mechanism_flow_heading"] = schema["mechanism_flow"]
    return rules


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
    figure_plan: dict[str, Any]
    figure_table_manifest: dict[str, Any]
    pdf_assets: dict[str, Any]
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
        figure_plan={},
        figure_table_manifest={},
        pdf_assets={},
        writing_contract={},
    )
