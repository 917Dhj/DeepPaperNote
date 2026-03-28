# Deep Analysis

Use this guide when the user wants a note that feels like a real research note rather than a cleaned-up summary.

## Goal

Produce a Chinese paper note that helps future rereading answer:
- this paper is really solving what problem
- the core route or method chain is what
- which evidence actually supports the claim
- where the paper is weak, bounded, or easy to misread
- whether it is worth follow-up, comparison, implementation, or citation

## Key Principle

Do not treat deterministic script output as the final note.

Scripts in `DeepPaperNote` are for:
- resolving the paper
- fetching metadata and PDF
- extracting evidence and PDF assets
- planning figure/table candidates
- linting and writing files

The real value comes from Codex reading the available material and writing the note in its own words.

## Source Priority

Use sources in this order:

1. existing Obsidian note, if the user wants an update rather than a fresh note
2. synthesis bundle metadata
3. evidence extracted from the full PDF
4. figure/table captions and candidate assets
5. abstract only, as the weakest fallback

For a finished long-term note, prefer the complete PDF over the abstract.

If you only have the abstract, say so clearly and treat the note as provisional rather than finished.

## Recommended Workflow

1. Resolve the paper and build the synthesis bundle.
2. Read the bundle closely before writing.
3. Infer the paper type yourself:
   - `method`
   - `system/framework`
   - `benchmark/dataset`
   - `clinical/psychology empirical`
   - `survey/tutorial`
   - `humanities/social science`
4. Make a short internal note plan before drafting.
   The plan should decide:
   - which sections deserve the most weight
   - which details need `###` subheadings
   - which 3 to 6 numbers matter most
   - which figure/table placeholders are essential
   - whether the paper needs explicit formulas, objective functions, or complexity expressions
5. Write the final note in Chinese.
6. Lint it.
7. Save into the Obsidian vault only after the note passes.

## Writing Rules

- Write for future rereading, not for one-time display.
- Prefer interpretation over translation.
- Prefer “这篇论文真正有价值的点是...” over “本文提出了...” style filler.
- Avoid pasting long English sentences into Chinese sections.
- Do not fabricate metrics, ablations, or claims not supported by evidence.
- If evidence is weak, write a weak-but-honest note instead of pretending the paper was fully analyzed.
- For method papers, write like a replication-minded researcher rather than a summary assistant.

## Section Guide

### 核心信息

Must include:
- title
- authors
- affiliations or institutions when available
- published date
- venue or journal when available
- DOI
- source URL
- code repo or project page when available
- domain

### 一句话总结

Do not paraphrase the abstract.

Answer:
- what the paper's real contribution is
- what the title may overstate

### 研究问题

Answer:
- the concrete pain point
- why existing methods are not enough
- whether this is a new problem, a new angle on an old problem, or a more realistic reformulation

### 数据与任务定义

Must separate:
- where the data comes from
- what labels or supervision exist
- what the actual task is
- what the paper is not predicting

For clinical or social-science papers, spell out:
- collection setting
- weak supervision risks
- annotation or rating assumptions
- whether the task is realistic or simplified

### 方法主线

This is usually where a shallow note fails.

Explain:
- the information flow
- what each stage consumes and produces
- what the model is actually doing
- what is standard versus paper-specific
- what the training target or optimization target really is
- how inference or sampling actually proceeds
- which implementation details matter for reproducing the claimed gain

For complex papers, use `###` subheadings such as:
- `### 数据构建`
- `### 中间表征抽取`
- `### 模型结构`
- `### 训练与推理`

### 关键结果

Do not dump all metrics.

Include:
- the most important comparison
- the most important numbers
- at least one result that looks strong
- at least one result that limits the claim

For method papers, also ask:
- does the result support the claimed mechanism
- is the gain internal-only or external too

### 深度分析

This is the most important part.

Include:
- research value
- practical value
- why the method may work
- where the evidence is still thin
- hidden assumptions
- what the paper does not prove

Good subsections often include:
- `### 真正贡献是什么`
- `### 为什么结果成立`
- `### 哪些地方容易被误读`
- `### 训练目标`
- `### 推理与采样链路`
- `### 复杂度与扩展性`

### 局限

Write real limitations, not polite filler.

Prefer:
- dataset or sampling boundaries
- label leakage or weak-supervision risks
- evaluation mismatch
- deployment gap
- missing baselines
- unrealistic task framing

### 我的笔记

Seed future follow-up with prompts such as:
- one reusable idea
- one questionable assumption
- one experiment worth replicating
- one related paper to compare next

## Figures And Tables

When the paper has useful visuals:
- preserve placeholders for the important ones
- prioritize one method figure, one data/task figure, and one result figure or table
- explain why each figure matters
- keep original paper numbering such as `Fig. 1` or `Table 2`

Do not dump every extracted image into the note body.

## Formula Guidance

If a formula is central to understanding the method, do not leave it out just because the rest of the prose reads smoothly.

Typical cases where a formula should appear:
- probability factorization
- optimization objective
- loss definition
- complexity comparison
- scaling-law fit

Prefer a few stable, well-explained formulas over many noisy ones.

## Minimum Honesty Standard

If the note is based mostly on abstract plus metadata, say so explicitly and soften the judgment.
If the note uses full PDF evidence, figures, and key numbers, the judgment can be stronger.
