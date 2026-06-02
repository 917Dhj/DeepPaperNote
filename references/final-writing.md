# Final Writing

The final note should not read like raw extracted evidence.

Use the structured artifacts as inputs:
- `metadata.json`
- `source_manifest.json`
- `raw_sections.jsonl`
- `figure_table_decisions.json`
- `synthesis_bundle.json`

Then let the model draft the final note in natural language.

## Front-Matter Structure

Every final note must start with an Obsidian YAML properties block above the `#` title heading.
Include at least:
- `tags`: a `papers/<domain>` hierarchy tag
- `aliases`: a short English name, acronym, or stable title alias useful for wikilinks
- `date`: when publication date or year is known
- `doi` or `arxiv_id`: when available

Do not invent placeholder metadata values. Omit unavailable fields instead.

Near the beginning of the note, include:
- `## 核心信息`
- `## 原文摘要翻译`
- `## 创新点`
- `## 一句话总结`

`## 核心信息` is a fixed metadata block, not an analysis block.
Rules for this section:
- Core info field schema: use only the following fields, in this order, and no free prose:
  `标题`, `标题翻译`, `作者`, `机构`, `发表时间`, `发表渠道`, `DOI`, `arXiv`, `论文链接`, `代码 / 项目`, `数据 / 资源`, `论文类型`
- keep each line in `- 字段名: 值` form
- omit fields that are unavailable or not applicable; do not add `未知`, `无`, or placeholder rows just to fill the schema
- do not add ad hoc fields such as judgments, takeaways, or mini-summaries
- do not move explanatory prose, evaluation, or "my view" sentences into this section
- move any paper-positioning or guide sentence to `一句话总结` or an analysis section, not under `核心信息`

The `原文摘要翻译` section should be a Chinese translation of the paper's original abstract:
- if the abstract is available, translate the original abstract into Chinese before the one-sentence summary
- do not let the summary replace the abstract
- do not treat `原文摘要翻译` as your own summary of the full paper; it is the original abstract translated into Chinese
- do not split this section into `### 英文原文` and `### 中文翻译`
- keep the section title exactly as `原文摘要翻译`
- the `原文摘要翻译` section itself must be written in Chinese; do not output English abstract sentences or English-original paragraphs here
- the Chinese abstract should be fluent and faithful, not a second `一句话总结`
- do not turn `原文摘要翻译` into a selective excerpt or a compressed highlight list
- do not add judgments, hindsight, or details learned from later sections of the paper into `原文摘要翻译`; only translate what the original abstract says

The `创新点` section should be a dedicated top-level section after `原文摘要翻译` rather than a hidden bullet buried later.
It should usually:
- enumerate 3 to 5 paper-specific innovations
- explain what problem each innovation addresses
- explain what new capability, mechanism, or evaluation angle it enables
- avoid generic praise such as `the paper is novel` without locating the novelty

## Writer Persona

Default to a high-bar technical reader and writer persona:
- you are a top-tier AI researcher and algorithm engineer
- you are preparing an internal replication-oriented reading note for your lab
- you are not writing a science-pop summary
- you should assume the reader is comfortable with Python, PyTorch, training loops, evaluation protocols, and ablation logic

For technical or method papers, write as if the note may later be used for:
- implementation planning
- reproduction
- comparison against later papers
- deciding whether the method is actually novel or just well-packaged

## Writing Priorities

1. explain the paper rather than quote it
2. distinguish research problem from task definition
3. explain the method or analysis flow in your own words
4. choose the most meaningful results rather than repeating every number
5. say what the paper does not prove
6. keep the note readable weeks later
7. make the technical core understandable enough for an engineer to re-explain it

## What Scripts Should Not Try To Fully Replace

Scripts are good at:
- resolution
- extraction
- formatting
- linting
- placeholder planning

Scripts are not enough on their own for:
- nuanced judgment
- identifying what is easy to misread
- deciding what the paper's real contribution is
- writing strong, natural Chinese analytical prose

The language model should do all of the following:
- choose `note_plan.paper_type` from the allowed bundle contract values after reading the raw source records
- make an explicit short `note_plan` before drafting
- decide which sections need more weight
- write `central_claims` so each major claim carries source-grounded evidence, what it actually proves, and what it does not prove
- write `claim_boundaries`, `negative_or_limiting_results`, `mechanism_result_map`, `comparative_positioning`, `reuse_takeaways`, and `followup_questions` before drafting, so the final note has a planned place for judgment rather than only summary
- decide where `###` subheadings are needed
- select the truly central results
- reconstruct the method or analysis flow
- decide whether the paper needs explicit LaTeX formulas for the core objective, factorization, or complexity
- write the final note in clean Chinese

## Final-Draft Standard

The note should feel like:
- a careful reading note
- not an abstract rewrite
- not a raw evidence dump
- not a benchmark table converted into bullets

For quantitative results, preserve the central numbers instead of replacing them with only qualitative claims.
When the source comparison is naturally tabular, especially with three or more compared systems, settings, tasks, datasets, metrics, ablations, or experimental conditions, use a compact Markdown table for the central comparison rather than prose-only or a loose bullet list.
Keep only the rows and metrics that matter for understanding the paper, and follow the table with interpretation of what the numbers mean.
If a paper is short, do not make the final note shallow; use the saved space to explain protocol details, ablations, limitations, and deployment or replication implications.

The final Chinese note must also pass a language-cleanliness check:
- no half-English half-Chinese prose lines
- English is allowed only for stable proper nouns or citation metadata
- if the style gate fails, do not write the note into Obsidian yet
- do not write for the linter; lint is only a minimum floor, not the writing objective
- after script lint passes, `final_quality_review` and then `final_readability_review` are still required before the note should be treated as polished and ready to save

正文术语策略:
- default to natural Chinese prose in正文分析
- keep English only when it is a stable proper noun or source-faithful technical label
- stable English that may remain:
  - model names
  - dataset names
  - metric names
  - method names
  - math symbols
  - code tokens
  - original paper figure/table ids
- when any of the above retained English terms or standalone key numbers appear inline within Chinese prose, wrap them in backticks for visual separation
- English that should usually be rewritten into natural Chinese:
  - ordinary English phrases
  - abstract descriptive phrases in analytical prose
  - leftover English wording that has no clear reason to remain
- when a first mention benefits from both forms, prefer Chinese-first wording with an English gloss in parentheses
- do not leave phrases such as `reasoning dataset`, `distillation risk`, or `reward model quality` directly inside Chinese prose when a natural Chinese rendering is available

For non-trivial papers, the note should usually not stop at only broad `##` sections.
It should use meaningful `###` subheadings where they improve technical clarity.

Before the final draft exists, there should already be a compact structured planning artifact.
The canonical artifact is a short JSON file such as `<note>.plan.json` or a run-scoped `*_note_plan.json`.
Pass that file to `scripts/lint_note.py --plan-file ...` when linting; if omitted, lint looks for a sibling `<note>.plan.json`.
In interactive contexts, you may additionally show a compact `<note_plan>...</note_plan>` block as display-only context, but it does not replace the JSON file.
The plan's `paper_type` is the authoritative paper-type selection; choose it from the allowed values in the synthesis bundle.
Before drafting from the plan, run `scripts/lint_grounding.py` against the source manifest, bundle, and figure/table decisions so every substantive section cites valid `section_id` values or page ranges.
The plan must include `central_claims`, `claim_boundaries`, `negative_or_limiting_results`, `mechanism_result_map`, `comparative_positioning`, `reuse_takeaways`, and `followup_questions`.
Each `central_claims` item should contain `claim`, `supporting_evidence`, `what_it_actually_proves`, and `what_it_does_not_prove`.
This plan should be short and inspectable.
Do not require or expose a long free-form `<thinking>` block.

Examples:
- `### 数据来源`
- `### 任务定义`
- `### 中间特征抽取`
- `### 训练细节`
- `### 哪些结果最重要`
- `### 哪些地方容易被误读`

For technical papers, also strongly consider subsections such as:
- `### 机制流程`
- `### 训练目标`
- `### 推理与采样链路`
- `### 关键实现细节`
- `### 复杂度与扩展性`
- `### 消融到底说明了什么`

For method, framework, and system papers, prefer an explicit `### 机制流程` subsection instead of hiding the execution chain inside generic prose.
That subsection should usually be a 3 to 4 step numbered list covering:
- what the Input is
- what the main intermediate transformations are
- what the Output is
- what the training or inference loop is actually doing
- do not rely on a damaged Algorithm block to carry this explanation for you
- do not let the steps collapse into module-name listing; each step should describe an operation
- if a high-confidence pipeline or architecture figure matches this execution chain, place it in `### 机制流程`

## Formula Rule

Do not avoid formulas by default.
When the paper's method or claim depends on:
- a training objective
- a probability factorization
- a complexity expression
- a scaling-law fit
- a key update rule or optimization target

the note should usually include 1 to 3 essential LaTeX formulas in the relevant section.

Use formulas sparingly and purposefully:
- each formula should help explain the method
- do not dump many formulas just to look technical
- if the source extraction is noisy, prefer reconstructing a small, stable core formula rather than copying broken math verbatim
- after each retained formula, add one sentence explaining what it corresponds to in engineering or code terms
- do not only translate variable names; explain the concrete operation, loss term, update rule, or control effect
- formulas in the final Markdown should be written as directly renderable Obsidian/MathJax math, not as JSON-style escaped strings
- do not double-escape TeX commands such as `\\tau`, `\\frac`, `\\bar`, `\\begin`, or `\\end` when the final note should contain `\tau`, `\frac`, `\bar`, `\begin`, or `\end`
- use real math delimiters:
  - inline math: `$...$`
  - display math: `$$ ... $$`
- do not format formulas as inline code with backticks
- do not put formulas inside fenced code blocks unless you are literally discussing source code or pseudocode

## Prose Cleanliness

Chinese paragraphs should read like natural prose, not like PDF fragments.

Do not leave:
- mid-sentence line breaks after commas or semicolons
- one sentence broken into many short physical lines
- raw PDF folding artifacts inside normal paragraphs

Allowed line breaks:
- between paragraphs
- bullet lists
- block quotes
- figure callouts
- fenced code or formula blocks

## Figure Placeholders

Start from placeholders, not from extracted images.
The note should preserve the full figure/table structure even when image extraction is partial.

If the bundle contains candidate figure pages or candidate image files:
- use them as evidence for semantic matching
- prefer the candidate with the strongest caption/page-context agreement
- treat identity match and visual usability as separate gates
- never treat a matching label or caption as sufficient approval to insert an image
- reject caption-only crops, missing table bodies, table crops contaminated by running prose outside the table body or another Figure/Table caption, large text/title/abstract crops, and crops with very low visual body ratio
- if visual quality is missing, ambiguous, or failed, keep the placeholder
- still make the final decision yourself rather than trusting the candidate ranking blindly
- for `usable_candidate` or `needs_visual_quality_check` / `review`, make that final decision only after opening and inspecting the actual candidate image file; do not say manual visual review found no reliable candidate unless that inspection actually happened
- treat `reject_visual_quality` and `asset_candidate_missing` as automatic fail-closed script outcomes that do not require manual visual review
- if a candidate is usable and has a real image path, insert it
- do not keep a usable candidate as a placeholder merely because it is lower priority, supplemental, already summarized in text, or less central than another inserted figure/table
- keep a placeholder only when there is a concrete visual defect, missing candidate, unresolved visual review, identity mismatch, contamination, or materialization/copy/write failure
- never describe a missing image asset, empty `source_image_path`, `asset_candidate_missing`, or absent independent crop as a materialization/copy failure
- if the crop contains a different Figure/Table caption or another figure body, describe that as contamination/visual defect or lack of an independent crop, not as a usable clean candidate
- do not keep a usable candidate as a placeholder only because the note should stay light, the values were transcribed, the figure can be checked later, or it is convenient as a back-reference

Final-note figure rules:
- keep the original paper numbering, such as `Fig. 1`, `Fig. 3`, `Table 2`
- do not rename them to `图 1`, `图 2` just because of note order
- if you replace a placeholder with a real image, keep the same paper figure id in the caption
- if you replace a placeholder with a real image, use the `relative_markdown_embed` from `figure_table_decisions.json`; let `write_obsidian_note.py --figure-decisions ...` copy the image during final save
- if you replace a placeholder with a real image, render only the embed plus one italic caption line; do not keep a redundant `[!figure]` callout for that same figure
- if `figure_table_decisions.json` marks an item as `insert`, the final note must reference its `images/<filename>` path and `write_obsidian_note.py` must be run with `--figure-decisions ...`
- if an important figure cannot be confidently extracted, keep a placeholder with a short explanation
- every kept placeholder must appear directly under its most relevant analytical section; do not create catch-all sections such as `剩余图表占位`, `未放置图表`, `Remaining figures`, or `Leftover figures`
- every kept placeholder must use the standard `[!figure]` callout format; never use ordinary paragraph markers such as `[图表占位 | Fig. 1]`, `图表占位：Table 2`, or `Figure Placeholder | Fig. 3`
- `[!figure]` callouts are only valid for kept placeholders, not for real images already inserted into the note
- `reject_visual_quality` means the candidate image is unsafe to insert, not that the final note must keep a placeholder for that rejected candidate
- for survey papers, summarize repetitive representative-work figures or appendix tables in prose when they do not materially help the reader as standalone callouts
- text may be complete even when figures are partial; do not let missing images erase textual coverage
- complete the figure decision inside the same task as the note generation
- do not stop after the text draft and ask the user whether to continue with figures unless they explicitly asked for a staged workflow
- prefer a stable figure callout format in the final note:
  - `> [!figure] Fig. 3 ...`
  - `> 建议位置：...`
  - `> 放置原因：...`
  - `> 当前状态：...`
- prefer a stable inserted-image format in the final note:
  - `![[.../images/page_003_img_01.png]]` or `![Fig. 2 ...](images/page_003_img_01.png)`
  - `*论文原图编号：Fig. 2。...*`

## Final Self-Review

Before outputting the final Markdown, first run `final_quality_review` and explicitly check:
- does the note reconstruct the central evidence chain rather than only restating claims?
- does it separate what the evidence actually proves from what the paper has not proven?
- does it map mechanisms, protocols, constructs, data decisions, or study design choices to the result pattern they explain?
- does it position the paper against strong baselines, prior routes, human references, or obvious alternatives?
- does it explain the paper's own Discussion/Limitations claims mechanistically when those sections exist?
- are the planned `claim_boundaries`, `negative_or_limiting_results`, `mechanism_result_map`, `comparative_positioning`, `reuse_takeaways`, and `followup_questions` reflected in the final prose?
- does the note contain concrete numbers, dimensions, complexity terms, or formulas when the paper clearly depends on them?
- can a reader familiar with Python and deep learning frameworks follow the core method from this note alone?
- does the method section explain the mechanism rather than only summarize the claim?
- if this is a method/system/framework paper, does `方法主线` explicitly contain `### 机制流程` with a 3 to 4 step numbered list?
- if the raw source reports negative or unstable ablation settings, did the note include at least one of them?
- if the raw source does not clearly report such settings, did the note avoid inventing failed or unstable cases?
- does the note contain at least one honest limitation and one paper-specific insight?
- are there any suspicious mid-sentence line breaks left in the prose?
- if the note includes LaTeX formulas, did you quickly check that the final Markdown uses directly renderable TeX rather than double-escaped commands or broken math delimiters?

If `final_quality_review` finds missing evidence-chain coverage, missing mechanism-to-result explanation, missing comparative positioning, missing boundary judgment, missing negative/limiting result discussion, or generic reusable takeaways or follow-up questions, return to the source artifacts and revise the note before saving.

After `final_quality_review`, run `final_readability_review`.
This review is a language-and-expression pass, not a second evidence-judgment pass:
- improve fluency and readability
- remove stiff translations
- convert ordinary English phrase leftovers into natural Chinese
- remove mechanical term-replacement artifacts such as `KV缓存 of`, `批量ing`, `In相关 Researcher`, or `Single 序列 generation`; figure/table callout titles and captions count too
- keep stable proper nouns when forcing a translation would sound worse
- do not invent new facts, numbers, comparisons, or failure cases during this pass
- do not use polish as an excuse to flatten the note into a safer but shallower summary

If the answer to the first four quality-review questions is `no`, the draft is still too shallow and should be revised before save.
