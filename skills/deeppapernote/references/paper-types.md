# Paper Types

The paper type decides the note's middle: which sections sit between the fixed head (`核心信息`, `原文摘要翻译`, `创新点`, `一句话总结`) and the fixed tail (`局限`, `阅读收获`, `关联`, `我的笔记`), in what order, which core questions the note must answer, and whether it has a workflow subsection. The section order is the note's storyline, so keep it.

`synthesis_bundle.writing_contract.contracts_by_paper_type[<type>]` is the source of truth, already in the output language: `middle_sections` (name, purpose, suggested tables), `core_questions` (id, home section, question), `workflow` (host section, heading, step fields, table header), `secondary_heading`, `secondary_question_ids`, `plan_enums`, and `formula_rules`.

## Choosing the type

Pick the type by what the paper contributes, and record the deciding signals in `paper_type_rationale` (a `Position:` title, theorems, a workload evaluation, a released dataset, interviews, and so on).

| `paper_type` | Choose it when the main contribution is |
|---|---|
| `method` | a new method or mechanism; set `positioning`: `technique` (a known problem, solved better) or `new_problem` (a new problem or setting, defined and made feasible) |
| `system` | a built system judged by its design trade-offs and measured performance |
| `theory` | proved results |
| `position` | an argued stance on how a field should work, with a call to action; this includes a conceptual framework or definition proposed for CS or AI, such as levels of AGI |
| `benchmark_or_dataset` | a new benchmark or dataset; a paper that audits existing benchmarks is `discovery_empirical` or `survey_or_review` instead |
| `discovery_empirical` | a finding from experiments or measurement: an analysis of model behavior ("does the model have capability X"), a study of systems, source code, or other artifacts, or a natural-science discovery |
| `human_subjects_empirical` | a quantitative study of people: clinical, psychological, or social-science experiments and surveys |
| `survey_or_review` | a synthesis of prior literature; set `survey_mode`: `systematic` (reports search and screening, PRISMA-style) or `narrative` |
| `qualitative_empirical` | interviews, focus groups, observation, or thematic analysis of texts |
| `humanities_argument` | an interpretive or conceptual argument in philosophy or another humanities field |

Two boundaries decide most hard cases:

- **Position or humanities argument.** A conceptual paper that tells a CS or AI community what to adopt, measure, or build is `position`, even when it reasons like philosophy. `humanities_argument` is for an argument whose audience is a humanities field, for example about what a concept means.
- **Survey or empirical study.** A survey's material is prior papers. A paper whose material is systems, code, products, or data it examined itself is `discovery_empirical`, even when it compares many systems and reads like a survey; when it also argues a thesis, add `position` as its `secondary_type`.

A paper with a second, real contribution gets one `secondary_type`, for example a benchmark with a companion method. Its `secondary_question_ids` join the core questions, and the note answers them under one `### <secondary_heading>` subsection placed in the primary section named by `secondary_host_section`. Leave both fields empty otherwise.

## Core questions

`note_plan.core_answers` maps every required question id to one of two forms:

- `{"answer": "...", "evidence_refs": [...]}`, with the same `section_id` or `pages` references as `section_plan`;
- `{"not_reported": true, "reason": "..."}`, when the paper does not report it.

Unreported is a finding, not a failure: write it in the note as "论文没有报告 X" (`en`: "The paper does not report X") and carry it into `局限` only when it limits a conclusion the paper draws. Never turn it into "the authors did not do X", and never score or rate (no low/high risk labels). The note answers each question in its home section.

Use `not_reported` only for what this kind of paper would report. When a question does not fit the work, answer it with what the paper does instead: a conceptual argument has no measurement, so its evidence question is answered by the cases or reasoning it rests on, and the note does not list the missing measurement as a weakness.

When more than half of the primary type's questions are `not_reported`, put this callout between the title and `核心信息`, followed by one line naming the unreported questions:

```md
> [!warning] 论文报告不足
```

(`en`: `> [!warning] Limited reporting`.) Final Note Lint requires the callout exactly in that case.

## Workflow

Types with `workflow` need that `###` subsection in the host section, mirroring `note_plan.workflow`: one or more flows (for example training and inference, or offline and online), each with 3 to 7 steps holding the type's `step_fields`. For each flow, write an overview chain on its own line, then the step table:

```md
### 方法流程

预处理 → 构建记忆 → 联合检索 → 停止或继续

| 步骤 | 输入 | 做什么 | 输出 | 本文新做法 |
| --- | --- | --- | --- | --- |
| 预处理 | 原始视频 | 切窗并生成多粒度摘要 | 基础工件 | 否 |
| … | … | … | … | … |
```

Keep one short phrase per cell and put details in the module subsections after the table. The last column depends on the type: method, system, and survey steps say whether the step is new in this paper (`novel`); benchmark steps name who does it and its quality gate; discovery, human-subjects, and qualitative studies follow an established design, so each step names its key design choice (`design_choice`), such as randomizing by site or sampling until saturation. The table needs one row per planned step and the header from `workflow.table_headers`. The paper's own pipeline or framework figure goes right after the table. A survey whose paper does not report search and screening keeps the subsection with the not-reported sentence and an empty `workflow`; types without `workflow` keep `workflow` empty.
