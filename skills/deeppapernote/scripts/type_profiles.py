#!/usr/bin/env python3
"""Paper types: the middle sections, core questions, and workflow of each type.

A note keeps four fixed head sections and four fixed tail sections; the paper
type decides the sections in between, in reading order. Each type also names
the questions its note must answer (in note_plan `core_answers`) and, for work
that runs as a sequence of steps, a workflow subsection mirrored from note_plan
`workflow`. Question sets are v1, drawn from docs research on reviewer
guidelines and reporting checklists; they change only with a corpus comparison.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

LANGUAGES = ("zh-CN", "en")

HEAD_SECTION_KEYS = ("core_information", "abstract", "contributions", "one_sentence_summary")
TAIL_SECTION_KEYS = ("limitations", "takeaways", "connections", "my_notes")

POSITIONING_VALUES = ("technique", "new_problem")
SURVEY_MODE_VALUES = ("systematic", "narrative")
SECONDARY_QUESTION_LIMIT = 2
WORKFLOW_STEP_RANGE = (3, 7)

WORKFLOW_STEP_FIELDS = ("step", "input", "operation", "output", "novel")
BENCHMARK_WORKFLOW_STEP_FIELDS = ("step", "input", "operation", "output", "who", "quality_gate")
# Empirical studies follow an established design, so their steps record the key design choice, not novelty.
STUDY_WORKFLOW_STEP_FIELDS = ("step", "input", "operation", "output", "design_choice")
STEP_FIELDS = {
    "default": WORKFLOW_STEP_FIELDS,
    "benchmark": BENCHMARK_WORKFLOW_STEP_FIELDS,
    "study": STUDY_WORKFLOW_STEP_FIELDS,
}

WORKFLOW_TABLE_HEADERS = {
    "default": {
        "zh-CN": ("步骤", "输入", "做什么", "输出", "本文新做法"),
        "en": ("Step", "Input", "What happens", "Output", "New in this paper"),
    },
    "benchmark": {
        "zh-CN": ("步骤", "输入", "做什么", "输出", "谁来做", "质量关卡"),
        "en": ("Step", "Input", "What happens", "Output", "Who", "Quality gate"),
    },
    "study": {
        "zh-CN": ("步骤", "输入", "做什么", "输出", "关键设计选择"),
        "en": ("Step", "Input", "What happens", "Output", "Key design choice"),
    },
}

WEAK_EVIDENCE_CALLOUT = {
    "zh-CN": "> [!warning] 论文报告不足",
    "en": "> [!warning] Limited reporting",
}
NOT_REPORTED_PHRASE = {"zh-CN": "论文没有报告", "en": "The paper does not report"}


def _section(key: str, zh: str, en: str, zh_purpose: str, en_purpose: str, **flags: Any) -> dict[str, Any]:
    return {
        "key": key,
        "name": {"zh-CN": zh, "en": en},
        "purpose": {"zh-CN": zh_purpose, "en": en_purpose},
        "results": bool(flags.get("results")),
        "expects_numbers": bool(flags.get("expects_numbers")),
        "tables": flags.get("tables", ()),
    }


def _table(zh: str, en: str, zh_columns: str, en_columns: str) -> dict[str, Any]:
    return {"name": {"zh-CN": zh, "en": en}, "columns": {"zh-CN": zh_columns, "en": en_columns}}


def _question(qid: str, section: str, zh: str, en: str) -> dict[str, Any]:
    return {"id": qid, "section": section, "question": {"zh-CN": zh, "en": en}}


def _workflow(section: str, zh: str, en: str, *, steps: str = "default", may_be_unreported: bool = False) -> dict[str, Any]:
    return {
        "section": section,
        "heading": {"zh-CN": zh, "en": en},
        "step_fields": STEP_FIELDS[steps],
        "table_headers": WORKFLOW_TABLE_HEADERS[steps],
        "may_be_unreported": may_be_unreported,
    }


PROFILES: dict[str, dict[str, Any]] = {
    "method": {
        "label": {"zh-CN": "方法", "en": "Method"},
        "secondary_heading": {"zh-CN": "配套方法", "en": "Companion Method"},
        "plan_enums": {"positioning": POSITIONING_VALUES},
        "sections": (
            _section("background", "背景与问题", "Background and Problem",
                     "这项工作所处的场景、为什么重要，以及它要解决的具体问题。technique 论文讲清问题为什么难；new_problem 论文讲清问题如何定义、为什么这样定义合理。",
                     "The setting, why it matters, and the specific problem. For a technique paper, why the problem is hard; for a new-problem paper, how the problem is defined and why that definition is reasonable."),
            _section("prior_limits", "现有方法的局限", "Limitations of Prior Work",
                     "最多三条具体局限，每条写成\"已有工作 X 处理不了 Y\"，并能对应到后面的挑战。",
                     "At most three specific gaps, each phrased as \"prior work X does not handle Y\", each traceable to a later challenge."),
            _section("key_idea", "核心思路与挑战", "Key Idea and Challenges",
                     "一句话核心思路，以及实现它要克服的挑战（最多三条，说明朴素做法为什么不行）。",
                     "The one-sentence key idea and the challenges (at most three) that block a naive version of it, with why the naive approach fails."),
            _section("approach", "方法", "Method",
                     "先给方法流程，再按模块展开；每个模块对应一个挑战，说明输入、变换与输出。",
                     "The method workflow first, then each module; every module answers one challenge and states its input, transformation, and output."),
            _section("evidence", "实验证据", "Experimental Evidence",
                     "主结果、强基线、消融与稳定性；用表把挑战、模块和支撑实验对上。",
                     "Main results, strong baselines, ablations, and stability; a table lines up challenges, modules, and the experiments that support them.",
                     results=True, expects_numbers=True,
                     tables=(_table("挑战—模块—证据表", "Challenge–Module–Evidence Table",
                                    "挑战 / 解决它的模块 / 支撑实验 / 缺少的对照",
                                    "Challenge / Module that addresses it / Supporting experiment / Missing control"),)),
            _section("analysis", "深度分析", "Deep Analysis",
                     "方法为什么有效、在哪里脆弱、适用边界与代价。",
                     "Why the method works, where it is fragile, its operating boundary, and its cost."),
        ),
        "workflow": _workflow("approach", "方法流程", "Method Workflow"),
        "core_questions": (
            _question("method.problem", "background", "这篇论文要解决的具体问题是什么，为什么值得解决？",
                      "What specific problem does the paper solve, and why is it worth solving?"),
            _question("method.prior_gaps", "prior_limits", "现有方法具体卡在哪里？",
                      "Where exactly do existing methods fall short?"),
            _question("method.key_idea", "key_idea", "核心思路是什么，实现它要克服哪些挑战？",
                      "What is the key idea, and which challenges must be overcome to realize it?"),
            _question("method.claim_evidence", "evidence", "每条收益主张由哪个实验或消融支撑，哪些主张缺少对应证据？",
                      "Which experiment or ablation supports each claimed gain, and which claims lack matching evidence?"),
            _question("method.comparison", "evidence", "基线是否是当前强基线、是否同等调参，结果有多稳（运行次数、误差条或显著性）？",
                      "Are the baselines current and equally tuned, and how stable are the results (runs, error bars, significance)?"),
            _question("method.boundary_cost", "analysis", "在什么数据、规模和算力下成立，失败设置与代价是什么？",
                      "Under what data, scale, and compute does it hold, and what are its failure settings and costs?"),
        ),
        "secondary_question_ids": ("method.key_idea", "method.claim_evidence"),
        "formula_rules": {
            "zh-CN": ["只保留理解方法必需的 1 到 3 个关键公式，并解释其含义。"],
            "en": ["Keep only the one to three equations needed to understand the method and explain what they mean."],
        },
    },
    "system": {
        "label": {"zh-CN": "系统", "en": "System"},
        "secondary_heading": {"zh-CN": "系统实现", "en": "System Component"},
        "sections": (
            _section("problem", "问题与瓶颈", "Problem and Bottleneck",
                     "要解决的问题、瓶颈在哪，以及现有系统为什么不行。",
                     "The problem, where the bottleneck lies, and why existing systems fall short."),
            _section("design", "设计与权衡", "Design and Trade-offs",
                     "系统流程与核心设计，每个设计选择换来什么、付出什么。",
                     "The system workflow and core design; what each design choice buys and what it costs.",
                     tables=(_table("瓶颈与权衡表", "Bottleneck and Trade-off Table",
                                    "设计选择 / 收益 / 代价 / 论文是否量化代价",
                                    "Design choice / Gain / Cost / Is the cost quantified"),)),
            _section("implementation", "实现要点", "Implementation",
                     "让设计成立的关键实现细节与工程取舍。",
                     "The implementation details and engineering choices the design depends on."),
            _section("evaluation", "评测", "Evaluation",
                     "负载与基准、对比对象、平台与关键数字。",
                     "Workloads and benchmarks, comparison targets, platform, and decisive numbers.",
                     results=True, expects_numbers=True),
            _section("analysis", "深度分析", "Deep Analysis",
                     "收益从哪来、在哪些负载或规模下失效、未测的开销。",
                     "Where the gains come from, under which workloads or scales they fade, and unmeasured costs."),
        ),
        "workflow": _workflow("design", "系统流程", "System Workflow"),
        "core_questions": (
            _question("system.bottleneck", "problem", "要解决什么问题，瓶颈在哪，为什么现有系统不行？",
                      "What problem is solved, where is the bottleneck, and why do existing systems fall short?"),
            _question("system.tradeoffs", "design", "核心设计做了哪些权衡，换来什么、付出什么，代价是否量化？",
                      "What trade-offs does the design make, what does it gain and give up, and is the cost quantified?"),
            _question("system.workload", "evaluation", "评测用了什么负载，是否有代表性，子集或配置的选取是否说明理由？",
                      "Which workloads are evaluated, are they representative, and is the choice of subsets or settings justified?"),
            _question("system.comparison", "evaluation", "对比对象是谁，是否同等调优，是否报告绝对数值？",
                      "What is compared against, is it equally tuned, and are absolute numbers reported?"),
            _question("system.platform_costs", "analysis", "评测平台与规模是什么，有哪些开销或组件没有测？",
                      "What platform and scale are evaluated, and which costs or components go unmeasured?"),
        ),
        "secondary_question_ids": ("system.tradeoffs", "system.comparison"),
        "formula_rules": {
            "zh-CN": ["只保留刻画性能或代价的关键公式，例如延迟或吞吐的模型。"],
            "en": ["Keep only the equations that characterize performance or cost, such as a latency or throughput model."],
        },
    },
    "theory": {
        "label": {"zh-CN": "理论", "en": "Theory"},
        "secondary_heading": {"zh-CN": "理论分析", "en": "Theoretical Analysis"},
        "sections": (
            _section("background", "问题与背景", "Problem and Background",
                     "要回答的理论问题与已知结果。", "The theoretical question and what was known."),
            _section("setting", "设定与假设", "Setting and Assumptions",
                     "形式化设定与完整假设，哪些假设强。", "The formal setting and the full set of assumptions, flagging the strong ones.",
                     tables=(_table("假设—结论—证明思路表", "Assumption–Result–Proof Idea Table",
                                    "假设 / 依赖它的结论 / 证明中用在哪一步", "Assumption / Result that depends on it / Where the proof uses it"),)),
            _section("results", "主要结果", "Main Results",
                     "主要定理的精确陈述与它属于哪种贡献。", "The precise statement of the main results and the kind of contribution.",
                     results=True),
            _section("proof", "证明思路", "Proof Idea",
                     "证明的关键想法与新技术；说明证明在正文还是附录，笔记不逐步验证正确性。",
                     "The key idea and any new technique; say where the proof lives; the note does not verify it step by step."),
            _section("significance", "意义与紧致性", "Significance and Tightness",
                     "相对已知结果的进展、紧致性讨论与实验佐证。", "Progress over known results, discussion of tightness, and supporting experiments.",
                     tables=(_table("新旧结果对照表", "Prior vs. New Results Table",
                                    "已知结果 / 本文结果 / 差距来自哪里", "Known result / This paper / Where the gap comes from"),)),
        ),
        "workflow": None,
        "core_questions": (
            _question("theory.result", "results", "证明了什么（主要定理），属于哪种贡献？",
                      "What is proved (the main theorems), and what kind of contribution is it?"),
            _question("theory.assumptions", "setting", "完整假设是什么，哪些是强假设，不成立时结论会怎样？",
                      "What are the full assumptions, which are strong, and what happens when they fail?"),
            _question("theory.proof_idea", "proof", "证明的关键想法是什么，是否引入了新技术？",
                      "What is the key idea of the proof, and does it introduce a new technique?"),
            _question("theory.progress", "significance", "相对已知结果进展多大，是否讨论了紧致性（下界、匹配上界或已知差距）？",
                      "How far does it advance known results, and does it discuss tightness (lower bounds, matching upper bounds, known gaps)?"),
            _question("theory.empirical", "significance", "有没有实验或例子佐证结论？",
                      "Do experiments or examples support the results?"),
        ),
        "secondary_question_ids": ("theory.result", "theory.assumptions"),
        "formula_rules": {
            "zh-CN": ["公式是主角：给出主要定理与关键定义的形式化陈述，并用一句话解释含义。",
                      "复杂度类、语言类和计算模型（例如 NC¹、L、TC⁰）第一次出现时，用一句白话说明它代表多强的计算能力，再写符号。"],
            "en": ["Equations carry the paper: state the main theorems and key definitions formally, each with a one-sentence reading.",
                   "The first time a complexity class, language class, or model of computation appears (for example NC¹, L, TC⁰), say in one plain sentence how much computation it stands for before using the symbol."],
        },
    },
    "position": {
        "label": {"zh-CN": "立场", "en": "Position"},
        "secondary_heading": {"zh-CN": "立场", "en": "Position"},
        "sections": (
            _section("stance", "核心立场", "Core Position",
                     "一句话立场，以及为什么重要、为什么是现在。", "The position in one sentence, and why it matters now."),
            _section("support", "支撑论据", "Supporting Arguments",
                     "论据是什么：论证、证据还是例子，离立场有多远。", "The arguments: reasoning, evidence, or examples, and how far they are from the position.",
                     results=True,
                     tables=(_table("主张—论据—反方图", "Claim–Argument–Counterargument Map",
                                    "主张 / 论据 / 论据类型 / 对应的反方观点", "Claim / Argument / Kind of support / Opposing view"),)),
            _section("opposing", "反方观点", "Opposing Views",
                     "论文列出的对立观点与回应是否可信。", "The opposing views the paper raises and whether its responses are credible."),
            _section("call", "行动呼吁", "Call to Action",
                     "谁该做什么，以及立场是否可证伪。", "Who should do what, and whether the position is falsifiable.",
                     tables=(_table("行动呼吁表", "Call-to-Action Table", "谁 / 做什么 / 论文给出的判断标准", "Who / What / The paper's success criterion"),)),
        ),
        "workflow": None,
        "core_questions": (
            _question("position.stance", "stance", "立场是什么，为什么重要、为什么是现在？",
                      "What is the position, and why does it matter now?"),
            _question("position.support", "support", "用什么论据支撑（论证、证据还是例子），论据离立场有多远？",
                      "What supports it (reasoning, evidence, or examples), and how far is that support from the position?"),
            _question("position.opposing", "opposing", "论文列出了哪些对立观点，回应是否可信，有没有稻草人？",
                      "Which opposing views does the paper engage, are its responses credible, and are any of them strawmen?"),
            _question("position.call", "call", "行动呼吁是什么：谁该做什么，立场是否可证伪？",
                      "What is the call to action: who should do what, and is the position falsifiable?"),
        ),
        "secondary_question_ids": ("position.stance", "position.opposing"),
        "formula_rules": {"zh-CN": ["不写公式。"], "en": ["Do not write equations."]},
    },
    "benchmark_or_dataset": {
        "label": {"zh-CN": "Benchmark/数据集", "en": "Benchmark/Dataset"},
        "secondary_heading": {"zh-CN": "配套数据集与评测", "en": "Companion Benchmark or Dataset"},
        "sections": (
            _section("gap", "评测缺口", "Evaluation Gap",
                     "现有评测缺少什么能力维度，为什么需要一个新的 benchmark 或数据集。",
                     "What capability existing evaluations miss, and why a new benchmark or dataset is needed."),
            _section("task_design", "任务与设计目标", "Task and Design Goals",
                     "任务如何定义，设计目标是什么（覆盖、细粒度诊断、可复现、抗污染）。",
                     "How the task is defined and the design goals (coverage, fine-grained diagnosis, reproducibility, contamination resistance)."),
            _section("construction", "构造流程与质量控制", "Construction and Quality Control",
                     "构造流程、标注与质检，以及数据画像。", "The construction workflow, annotation and quality control, and a data profile.",
                     tables=(_table("数据画像表", "Data Profile Table",
                                    "来源 / 规模与单位 / 标签与获取方式 / 标注者与质检 / 划分 / 时间范围 / 覆盖 / 许可",
                                    "Source / Size and unit / Labels and how obtained / Annotators and QC / Splits / Time range / Coverage / License"),)),
            _section("eval_framework", "评测框架", "Evaluation Framework",
                     "指标、评分方式、难度分层与错误分类。", "Metrics, scoring, difficulty tiers, and error taxonomy."),
            _section("findings", "实验发现", "Findings",
                     "按论文的 Finding 逐条整理，每条后面跟支撑它的数字。", "The paper's findings one by one, each followed by the numbers behind it.",
                     results=True, expects_numbers=True),
            _section("validity", "它到底测到了什么", "What It Really Measures",
                     "评测主张卡：声称测什么、怎么操作化、效度证据、饱和与污染。",
                     "The evaluation-claim card: the claimed construct, how it is operationalized, validity evidence, saturation and contamination.",
                     tables=(_table("评测主张卡", "Evaluation Claim Card",
                                    "声称的构念 / 操作化 / 明说不测的部分 / 推断未覆盖的部分 / 效度证据 / 区分度与统计 / 饱和 / 污染（作者证据、可见风险、未报告）",
                                    "Claimed construct / Operationalization / Stated exclusions / Inferred gaps / Validity evidence / Discrimination and statistics / Saturation / Contamination (author evidence, visible risks, unreported)"),)),
        ),
        "workflow": _workflow("construction", "构造流程", "Construction Workflow", steps="benchmark"),
        "core_questions": (
            _question("benchmark.gap", "gap", "现有评测缺什么能力维度，为什么需要它？",
                      "Which capability do existing evaluations miss, and why is it needed?"),
            _question("benchmark.task", "task_design", "任务怎么定义，设计目标是什么？",
                      "How is the task defined, and what are the design goals?"),
            _question("benchmark.data", "construction", "数据从哪来、怎么抽样筛选和标注、怎么质检，覆盖了什么、没覆盖什么？",
                      "Where does the data come from, how is it sampled, filtered, annotated, and checked, and what does it cover and miss?"),
            _question("benchmark.protocol", "eval_framework", "评测协议能否重跑：指标、评分方式（LLM 评委是否与人对照）、人类与随机水平、不确定性？",
                      "Can the protocol be rerun: metrics, scoring (is an LLM judge checked against humans), human and random levels, uncertainty?"),
            _question("benchmark.findings", "findings", "主要发现是什么，模型差异说明的是区分度还是协议适配？",
                      "What are the main findings, and do model differences show discrimination or fit to the protocol?"),
            _question("benchmark.construct", "validity", "声称测什么构念，怎么落成任务和指标，作者给出了什么效度证据？",
                      "Which construct is claimed, how is it turned into tasks and metrics, and what validity evidence is given?"),
            _question("benchmark.saturation_contamination", "validity", "论文如何处理饱和与污染（作者证据 / 论文可见风险因子 / 论文没有报告）？",
                      "How does the paper handle saturation and contamination (author evidence / visible risk factors / not reported)?"),
        ),
        "secondary_question_ids": ("benchmark.data", "benchmark.protocol"),
        "formula_rules": {
            "zh-CN": ["只保留核心评测指标、采样规则或划分定义。"],
            "en": ["Keep only the core metrics, sampling rules, or split definitions."],
        },
    },
    "discovery_empirical": {
        "label": {"zh-CN": "发现型实证", "en": "Discovery Empirical"},
        "secondary_heading": {"zh-CN": "分析发现", "en": "Analysis Findings"},
        "sections": (
            _section("question", "研究问题与假设", "Question and Hypotheses",
                     "研究问题、假设与备择解释。", "The research question, hypotheses, and alternative explanations."),
            _section("design", "实验设计", "Experimental Design",
                     "实验流程、被测对象与操作化。", "The experiment workflow, what is measured, and how it is operationalized.",
                     tables=(_table("假设—实验—发现表", "Hypothesis–Experiment–Finding Table",
                                    "假设 / 检验它的实验 / 发现 / 备择解释是否排除",
                                    "Hypothesis / Experiment that tests it / Finding / Alternative ruled out?"),)),
            _section("findings", "主要发现", "Main Findings",
                     "主要发现与关键数字、跨设置的稳定性。", "The main findings, decisive numbers, and stability across settings.",
                     results=True, expects_numbers=True),
            _section("alternatives", "能否排除其他解释", "Ruling Out Alternatives",
                     "对照、干预与控制变量能否区分各种解释。", "Whether controls, interventions, and held-fixed variables separate the explanations."),
            _section("strength", "结论强度", "Strength of the Conclusion",
                     "结论强度是否超过证据，适用到哪里为止。", "Whether the conclusion outruns the evidence, and how far it extends."),
        ),
        "workflow": _workflow("design", "实验流程", "Experiment Workflow", steps="study"),
        "core_questions": (
            _question("discovery.hypothesis", "question", "研究问题和假设是什么，有哪些备择解释？",
                      "What are the question and hypotheses, and what alternative explanations exist?"),
            _question("discovery.measured", "design", "测的到底是什么：被测对象（如模型代际与规模、样本）、任务与操作化定义？",
                      "What exactly is measured: the subjects (such as model generation and scale, or samples), the tasks, and the operational definition?"),
            _question("discovery.robustness", "findings", "结果跨设置（模型、提示、种子、样本）是否稳，有没有统计？",
                      "Do the results hold across settings (models, prompts, seeds, samples), and are statistics reported?"),
            _question("discovery.discriminating", "alternatives", "实验能否区分各种解释（对照、干预），还是只有相关？",
                      "Can the experiments separate the explanations (controls, interventions), or do they show only correlation?"),
            _question("discovery.claim_strength", "strength", "结论强度是否超过证据？",
                      "Does the strength of the conclusion exceed the evidence?"),
        ),
        "secondary_question_ids": ("discovery.hypothesis", "discovery.discriminating"),
        "formula_rules": {
            "zh-CN": ["只保留定义被测量或统计检验所必需的公式。"],
            "en": ["Keep only the equations needed to define the measurement or the statistical test."],
        },
    },
    "human_subjects_empirical": {
        "label": {"zh-CN": "人类被试实证", "en": "Human-Subjects Empirical"},
        "secondary_heading": {"zh-CN": "人类被试研究", "en": "Human-Subjects Study"},
        "sections": (
            _section("question", "研究问题", "Research Question",
                     "研究问题、假设或变量关系。", "The research question, hypotheses, or variable relationships."),
            _section("design", "研究设计与对象", "Design and Participants",
                     "研究流程、设计类型与研究对象卡（PICO 家族，按设计变换四格）。",
                     "The study workflow, the design, and a study-object card (the PICO family, adapted to the design).",
                     tables=(_table("研究对象卡", "Study Object Card",
                                    "人群 / 干预或待评对象 / 对照或参照 / 结局（按设计调整名称）",
                                    "Population / Intervention or index object / Comparator or reference / Outcome (renamed per design)"),)),
            _section("measurement", "测量与分析", "Measurement and Analysis",
                     "主要结局的测量工具、效度、评分者与统计分析。", "How the primary outcome is measured, its validity, raters, and the statistical analysis."),
            _section("findings", "主要发现", "Main Findings",
                     "效应量与置信区间，主分析与探索分析分开写。", "Effect sizes with confidence intervals, keeping primary and exploratory analyses apart.",
                     results=True, expects_numbers=True),
            _section("bias", "偏倚与外推", "Bias and Generalization",
                     "偏倚风险表（按 RoB 2 或 ROBINS-I 的域，只写论文怎么处理，不评级）与外推边界。",
                     "A bias table (domains from RoB 2 or ROBINS-I, recording how the paper handles each, without ratings) and the limits of generalization.",
                     tables=(_table("偏倚风险表", "Bias Table", "偏倚域 / 论文怎么处理 / 原文依据或论文没有报告",
                                    "Bias domain / How the paper handles it / Source or not reported"),)),
        ),
        "workflow": _workflow("design", "研究流程", "Study Workflow", steps="study"),
        "core_questions": (
            _question("human.design_claim", "design", "这是什么设计，作者的结论（因果、预测或描述）有没有超出设计能支撑的范围？",
                      "What is the design, and does the conclusion (causal, predictive, or descriptive) go beyond what it can support?"),
            _question("human.population", "design", "研究对象是谁，评估的是什么，和什么比？",
                      "Who are the participants, what is evaluated, and what is it compared with?"),
            _question("human.outcome", "measurement", "主要结局是什么、是否预先指定，用什么工具测、效度如何、谁来评？",
                      "What is the primary outcome, was it prespecified, and how is it measured, validated, and rated?"),
            _question("human.effect", "findings", "效应量和置信区间是多少，主分析与探索分析是否分开？",
                      "What are the effect sizes and confidence intervals, and are primary and exploratory analyses kept apart?"),
            _question("human.bias", "bias", "最可能推翻结论的偏倚或危害是什么？",
                      "Which bias or harm is most likely to overturn the conclusion?"),
        ),
        "secondary_question_ids": ("human.population", "human.effect"),
        "formula_rules": {
            "zh-CN": ["不写模型公式；只保留核心统计模型、效应量或量表定义。"],
            "en": ["No model equations; keep only the core statistical model, effect sizes, or scale definitions."],
        },
    },
    "survey_or_review": {
        "label": {"zh-CN": "综述", "en": "Survey/Review"},
        "secondary_heading": {"zh-CN": "文献综述", "en": "Literature Review"},
        "plan_enums": {"survey_mode": SURVEY_MODE_VALUES},
        "sections": (
            _section("scope", "范围与检索", "Scope and Search",
                     "综述类型、目的与范围，以及文献怎么找、怎么选。", "The review type, aim, and scope, and how the literature was found and selected."),
            _section("taxonomy", "分类体系", "Taxonomy",
                     "分类轴是什么，什么落在轴外。", "The axes of the taxonomy and what falls outside them."),
            _section("directions", "各方向要点", "Directions",
                     "按分类组织的各方向要点与代表工作，区分强证据与个别主张。",
                     "Each direction in the taxonomy with representative work, separating strong evidence from isolated claims.",
                     results=True),
            _section("synthesis", "共识、分歧与空白", "Consensus, Disagreement, and Gaps",
                     "综合方式、结论靠什么，共识、分歧与开放问题。", "How the review synthesizes, what its conclusions rest on, and the consensus, disagreements, and open problems."),
        ),
        "workflow": _workflow("scope", "检索与筛选流程", "Search and Screening Workflow", may_be_unreported=True),
        "core_questions": (
            _question("survey.objective", "scope", "这是哪种综述（系统、范围或叙述性），要回答什么问题？",
                      "What kind of review is it (systematic, scoping, or narrative), and what question does it answer?"),
            _question("survey.search", "scope", "文献怎么找、怎么选：检索来源、截止日期、纳排标准、纳入多少篇？",
                      "How was the literature found and selected: sources, cutoff date, inclusion criteria, and number included?"),
            _question("survey.taxonomy", "taxonomy", "分类轴是什么，什么落在轴外？",
                      "What are the taxonomy's axes, and what falls outside them?"),
            _question("survey.evidence_quality", "directions", "被综合证据的质量与特征如何，综述是否区分强证据与个别主张？",
                      "How strong is the synthesized evidence, and does the review separate strong evidence from isolated claims?"),
            _question("survey.synthesis", "synthesis", "怎么综合，结论靠什么？",
                      "How is the evidence synthesized, and what do the conclusions rest on?"),
        ),
        "secondary_question_ids": ("survey.taxonomy", "survey.synthesis"),
        "formula_rules": {
            "zh-CN": ["只保留分类轴、纳入排除准则、证据汇总规则或 meta 分析统计量。"],
            "en": ["Keep only taxonomy axes, inclusion criteria, synthesis rules, or meta-analysis statistics."],
        },
    },
    "qualitative_empirical": {
        "label": {"zh-CN": "质性实证", "en": "Qualitative Empirical"},
        "secondary_heading": {"zh-CN": "质性研究", "en": "Qualitative Study"},
        "sections": (
            _section("question", "研究问题与取向", "Question and Approach",
                     "研究问题与方法论取向（扎根理论、现象学、主题分析等），以及为什么合适。",
                     "The question and methodological approach (grounded theory, phenomenology, thematic analysis, and so on), and why it fits."),
            _section("materials", "材料与参与者", "Materials and Participants",
                     "研究流程，材料或参与者怎么选、多少、何时停。", "The study workflow, and how materials or participants were chosen, how many, and when collection stopped."),
            _section("analysis", "分析过程", "Analysis",
                     "编码与主题归纳过程，以及可信度措施。", "The coding and theme-building process and its trustworthiness measures."),
            _section("themes", "主要主题", "Main Themes",
                     "主要主题，每个主题配原始材料。", "The main themes, each with source material.",
                     results=True,
                     tables=(_table("主题—证据对照表", "Theme–Evidence Table",
                                    "主题 / 原文引述 / 来源参与者类型 / 是否讨论反例", "Theme / Quotation / Participant type / Counter-examples discussed?"),)),
            _section("trust", "可信度与可迁移性", "Trustworthiness and Transferability",
                     "研究者立场、反例与替代解释、可迁移的边界。", "Researcher position, counter-examples and alternative readings, and the bounds of transferability."),
        ),
        "workflow": _workflow("materials", "研究流程", "Study Workflow", steps="study"),
        "core_questions": (
            _question("qual.approach", "question", "研究问题与方法论取向是什么，为什么适合？",
                      "What are the question and the methodological approach, and why do they fit?"),
            _question("qual.sampling", "materials", "材料或参与者怎么选、选了多少，是否讨论饱和？",
                      "How were materials or participants selected, how many, and is saturation discussed?"),
            _question("qual.analysis", "analysis", "分析怎么做的：编码者、主题来源、三角验证或成员检查？",
                      "How was the analysis done: coders, where themes came from, triangulation or member checking?"),
            _question("qual.grounding", "themes", "主题是否有原始材料支撑？",
                      "Are the themes supported by source material?"),
            _question("qual.reflexivity", "trust", "研究者立场如何影响数据与分析，作者承认的可迁移边界是什么？",
                      "How does the researchers' position shape the data and analysis, and what transferability limits do the authors state?"),
        ),
        "secondary_question_ids": ("qual.sampling", "qual.grounding"),
        "formula_rules": {"zh-CN": ["不写公式。"], "en": ["Do not write equations."]},
    },
    "humanities_argument": {
        "label": {"zh-CN": "人文/论证", "en": "Humanities/Argument"},
        "secondary_heading": {"zh-CN": "论证分析", "en": "Argument Analysis"},
        "sections": (
            _section("context", "问题与语境", "Question and Context",
                     "作者要回答的问题与它所处的语境。", "The question the author addresses and its context."),
            _section("claims", "核心主张", "Core Claims",
                     "核心主张及其类别（经验、概念或规范）。", "The core claims and their kind (empirical, conceptual, or normative).",
                     results=True),
            _section("structure", "论证结构", "Argument Structure",
                     "按论文自己的推理顺序还原论证：从哪些前提或材料出发，经过哪几步（分情形、反证、类比、概念区分等）推到结论；每一步写清它靠什么成立（桥接）以及这座桥的依据（支撑）。",
                     "Rebuild the argument in the paper's own order: the premises or material it starts from, and each step (cases, reductio, analogy, conceptual distinction, and so on) that leads to the conclusion; for each step, what makes it hold (the warrant) and what backs that warrant.",
                     tables=(_table("论证步骤表", "Argument Steps Table",
                                    "步骤 / 前提或材料 / 推出什么 / 靠什么成立 / 作者回应的反驳",
                                    "Step / Premises or material / What follows / What makes it hold / Objection the author answers"),)),
            _section("qualifiers", "限定与反驳", "Qualifiers and Rebuttals",
                     "主张被限定到什么程度，承认与遗漏的反例和替代解释。", "How far the claims are qualified, and the counter-examples and alternative readings admitted or missed."),
            _section("literature", "与既有研究的关系", "Relation to Prior Work",
                     "它挑战、扩展还是支持了谁。", "Whom it challenges, extends, or supports."),
        ),
        "workflow": None,
        "core_questions": (
            _question("hum.claim", "claims", "核心主张是什么，属于经验、概念还是规范判断？",
                      "What are the core claims, and are they empirical, conceptual, or normative?"),
            _question("hum.data", "structure", "凭什么材料：材料、案例或文本的范围与选择标准？",
                      "What material supports them: the scope of the material, cases, or texts, and how they were chosen?"),
            _question("hum.warrant", "structure", "从材料到主张靠什么桥接，这座桥靠什么站住？",
                      "What warrant bridges the material to the claims, and what backs that warrant?"),
            _question("hum.rebuttal", "qualifiers", "作者把主张限定到什么程度，处理了哪些反例与替代解释，遗漏了哪些？",
                      "How far are the claims qualified, which counter-examples and alternatives are handled, and which are missed?"),
            _question("hum.literature", "literature", "它和既有研究是什么关系：挑战、扩展还是支持？",
                      "How does it relate to prior work: challenge, extension, or support?"),
        ),
        "secondary_question_ids": ("hum.claim", "hum.rebuttal"),
        "formula_rules": {"zh-CN": ["不写公式。"], "en": ["Do not write equations."]},
    },
}

TYPE_KEYS: tuple[str, ...] = tuple(PROFILES)


def profile(paper_type: str) -> dict[str, Any] | None:
    found = PROFILES.get(paper_type)
    return deepcopy(found) if found else None


def middle_sections(paper_type: str, language: str) -> tuple[str, ...]:
    found = PROFILES.get(paper_type)
    return tuple(item["name"][language] for item in found["sections"]) if found else ()


def section_name(paper_type: str, key: str, language: str) -> str:
    for item in PROFILES[paper_type]["sections"]:
        if item["key"] == key:
            return item["name"][language]
    raise KeyError(key)


def sections_with(paper_type: str, flag: str, language: str) -> tuple[str, ...]:
    found = PROFILES.get(paper_type)
    if not found:
        return ()
    return tuple(item["name"][language] for item in found["sections"] if item[flag])


def question_ids(paper_type: str) -> tuple[str, ...]:
    found = PROFILES.get(paper_type)
    return tuple(item["id"] for item in found["core_questions"]) if found else ()


def required_question_ids(paper_type: str, secondary_type: str = "") -> tuple[str, ...]:
    ids = question_ids(paper_type)
    if secondary_type and secondary_type in PROFILES and secondary_type != paper_type:
        ids += PROFILES[secondary_type]["secondary_question_ids"]
    return ids


def question_lookup() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for found in PROFILES.values() for item in found["core_questions"]}


def localized_profiles(language: str) -> dict[str, dict[str, Any]]:
    """The per-type contract a writer reads: everything in one language."""
    contracts: dict[str, dict[str, Any]] = {}
    for paper_type, found in PROFILES.items():
        workflow = found["workflow"]
        contracts[paper_type] = {
            "paper_type": paper_type,
            "label": found["label"][language],
            "middle_sections": [
                {
                    "section": item["name"][language],
                    "purpose": item["purpose"][language],
                    "tables": [
                        {"name": table["name"][language], "columns": table["columns"][language]}
                        for table in item["tables"]
                    ],
                }
                for item in found["sections"]
            ],
            "core_questions": [
                {
                    "id": item["id"],
                    "section": section_name(paper_type, item["section"], language),
                    "question": item["question"][language],
                }
                for item in found["core_questions"]
            ],
            "workflow": None if workflow is None else {
                "section": section_name(paper_type, workflow["section"], language),
                "heading": workflow["heading"][language],
                "step_fields": list(workflow["step_fields"]),
                "table_headers": list(workflow["table_headers"][language]),
                "may_be_unreported": workflow["may_be_unreported"],
            },
            "secondary_heading": found["secondary_heading"][language],
            "secondary_question_ids": list(found["secondary_question_ids"]),
            "plan_enums": {key: list(values) for key, values in found.get("plan_enums", {}).items()},
            "formula_rules": list(found["formula_rules"][language]),
        }
    return contracts
