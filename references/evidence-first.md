# Evidence-First Note Writing

Use this guide when the goal is to approach the quality of a hand-written research note rather than a template-filled summary.

## Core Rule

Do not write the finished note directly from:
- the title
- the abstract
- one or two extracted snippets
- fixed headings alone

Instead, use a three-stage model-first pipeline:

1. build an evidence bundle
2. make a dynamic internal note plan around that evidence
3. let Codex write the note from the evidence and plan

## Evidence Bundle

The bundle should answer:
- what type of paper this is
- which parts of the PDF were actually found
- which numbers matter
- which datasets, metrics, baselines, or cohorts matter
- which figures are method figures, data figures, and result figures
- which conclusions are about scale, transfer, cost, limitations, or practical value

In `DeepPaperNote`, use:
- `scripts/run_pipeline.py`
- `scripts/build_synthesis_bundle.py`

## Internal Note Plan

Before drafting the final note, Codex should privately decide:
- which sections this paper actually deserves
- which sections need more technical depth
- which subsections deserve `###` headings
- which evidence feeds each section
- whether this is mostly a method note, system note, dataset note, benchmark note, or empirical/clinical note

Good note plans often add paper-specific sections such as:
- `### 数据构建`
- `### 量表代理特征抽取`
- `### 训练细节`
- `### 关键洞察`
- `### 为什么结果不等于临床可用`

## Writing Layer

Only after the evidence bundle and internal note plan exist should Codex draft the final note.

Good final notes should:
- prioritize numbers and comparisons over generic summary sentences
- add paper-specific subsections when the evidence supports them
- avoid abstract-only rewriting
- explain why a figure or table matters, not just attach it
- separate “作者声称了什么” from “论文真正证明了什么”

## Minimum Quality Bar

If the note does not clearly contain:
- the most important numbers
- the most important comparison
- one paper-specific insight
- one honest limitation
- one technically detailed subsection

then the note is still too close to a template summary.
