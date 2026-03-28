# Final Writing

The final note should not read like raw extracted evidence.

Use the structured artifacts as inputs:
- `metadata.json`
- `evidence_pack.json`
- `figure_plan.json`
- `synthesis_bundle.json`

Then draft the final note in natural language.

## Front-Matter Structure

Near the beginning of the note, include:
- `## 核心信息`
- `## 原始摘要`
- `## 一句话总结`

The `原始摘要` section should preserve the paper's original abstract in readable Chinese note context:
- if the abstract is available, include it before the one-sentence summary
- do not let the summary replace the abstract
- the summary should explain the paper's real value, while the abstract section preserves the author's original framing
- do not stop at only the English abstract
- inside this section, prefer:
  - `### 英文原文`
  - `### 中文翻译`
- the Chinese translation should be fluent and faithful, not a second “一句话总结”

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
- infer the paper type from the evidence bundle
- make an explicit short `note_plan` before drafting
- decide which sections need more weight
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

The final Chinese note must also pass a language-cleanliness check:
- no half-English half-Chinese prose lines
- English is allowed only for stable proper nouns or citation metadata
- if the style gate fails, do not write the note into Obsidian yet

For non-trivial papers, the note should usually not stop at only broad `##` sections.
It should use meaningful `###` subheadings where they improve technical clarity.

Before the final draft exists, there should already be a compact structured planning artifact such as `<note_plan>...</note_plan>` or an equivalent temporary planning file.
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
- `### 训练目标`
- `### 推理与采样链路`
- `### 关键实现细节`
- `### 复杂度与扩展性`
- `### 消融到底说明了什么`

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
- still make the final decision yourself rather than trusting the candidate ranking blindly

Final-note figure rules:
- keep the original paper numbering, such as `Fig. 1`, `Fig. 3`, `Table 2`
- do not rename them to `图 1`, `图 2` just because of note order
- if you replace a placeholder with a real image, keep the same paper figure id in the caption
- if an important figure cannot be confidently extracted, keep a placeholder with a short explanation
- text may be complete even when figures are partial; do not let missing images erase textual coverage
- complete the figure decision inside the same task as the note generation
- do not stop after the text draft and ask the user whether to continue with figures unless they explicitly asked for a staged workflow
- prefer a stable figure callout format in the final note:
  - `> [!figure] Fig. 3 ...`
  - `> 建议位置：...`
  - `> 放置原因：...`
  - `> 当前状态：...`

## Final Self-Review

Before outputting the final Markdown, explicitly check:
- does the note contain concrete numbers, dimensions, complexity terms, or formulas when the paper clearly depends on them?
- can a reader familiar with Python and deep learning frameworks follow the core method from this note alone?
- does the method section explain the mechanism rather than only summarize the claim?
- does the note contain at least one honest limitation and one paper-specific insight?
- are there any suspicious mid-sentence line breaks left in the prose?

If the answer to the first three questions is "no", the draft is still too shallow and should be revised before save.
