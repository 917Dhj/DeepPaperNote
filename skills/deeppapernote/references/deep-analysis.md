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

The real value comes from the model reading the available material and writing the note in its own words.

## Source Priority

Use sources in this order:

1. synthesis bundle metadata
2. evidence extracted from the full PDF
3. figure/table captions and candidate assets
4. abstract metadata only for identity and context, not as a substitute for a finished deep note

For a finished long-term note, require a usable PDF-backed evidence path.

If you only have the abstract after the supported PDF acquisition paths have failed, stop and ask for a usable PDF, OCR, or source material rather than writing a provisional or abstract-only note.

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
4. Make a short explicit note plan before drafting.
   The plan should decide:
   - which sections deserve the most weight
   - which details need `###` subheadings
   - which 3 to 6 numbers matter most
   - which central claims are supported by which source sections or pages
   - what each central claim actually proves and does not prove
   - which negative, weak, missing, or limiting results constrain the conclusion
   - which research or engineering takeaways are specific enough to reuse
   - which figure/table placeholders are essential
   - whether the paper needs explicit formulas, objective functions, or complexity expressions
5. Write the final note in Chinese.
6. Lint it.
7. Run the final readability review.
8. Save into the Obsidian vault only after the note passes lint and the final readability review.

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
- even if an extracted Algorithm block is broken, reconstruct the mechanism in plain engineering language rather than giving up
- make the reader feel the Input -> key transformation -> Output flow, not just the paper's terminology

For method, framework, or system papers:
- default to an explicit `### 机制流程` subsection inside `方法主线`
- write it as a 3 to 4 step numbered list rather than a long paragraph
- each step should say what goes in, what operation happens, and where the output goes next
- if the paper has both training and inference details, use `### 机制流程` for the dominant execution chain and leave training recipe details to neighboring subsections

For complex papers, use `###` subheadings such as:
- `### 机制流程`
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
- if the paper reports ablations or removed-module comparisons, include at least one setting that hurt performance, made training unstable, or revealed a trade-off
- if the evidence bundle contains no such negative ablation signal, say explicitly that the paper did not clearly report failed or unstable settings

### 深度分析

This is the most important part.

Include:
- research value
- practical value
- why the method may work
- where the evidence is still thin
- hidden assumptions
- what the paper does not prove

Use the plan's `central_claims` as the spine of this section:
- connect each major claim to the evidence that supports it
- say exactly what the evidence proves
- say what remains unproven, untested, or only indirectly supported
- use `mechanism_result_map` to explain why the paper's mechanism, protocol, construct, or data decision should produce the observed result pattern
- use `comparative_positioning` to say what changes relative to strong baselines or obvious alternatives, not only that the paper is better
- when the paper has Discussion or Limitations, explain the mechanism behind those caveats rather than copying them as a list

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
- if a high-confidence pipeline or architecture figure clearly matches the core execution chain, place it in `### 机制流程` first
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
- after each retained formula, add one short engineering explanation of what it means in implementation terms
- do not stop at naming variables; explain what operation, objective term, or state update the formula corresponds to

## Minimum Honesty Standard

If the note is based mostly on abstract plus metadata, say so explicitly and soften the judgment.
If the note uses full PDF evidence, figures, and key numbers, the judgment can be stronger.
