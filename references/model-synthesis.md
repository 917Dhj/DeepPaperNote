# Model Synthesis

This file describes the preferred final-mile workflow.

The rule is simple:
- scripts gather evidence
- the language model writes the note
- scripts verify and save the note

## Preferred Execution Loop

1. Run `scripts/run_pipeline.py`.
   This should produce:
   - `metadata.json`
   - `evidence.json`
   - `assets.json`
   - `figure_plan.json`
   - `synthesis_bundle.json`

   Before this step, if local Zotero is available and the user did not provide an exact local PDF path, do a Zotero-first preflight:
   - search the local Zotero library for the paper
   - if the hit is confident, materialize a trusted JSON input record with `scripts/create_input_record.py`
   - if the hit has an attachment but MCP does not expose the full path, use `scripts/locate_zotero_attachment.py`
   - prefer that JSON record over a raw title string

2. Read:
   - `references/evidence-first.md`
   - `references/deep-analysis.md`
   - `references/final-writing.md`
   - `references/note-quality.md`
   - `references/obsidian-format.md`
   - the generated `synthesis_bundle.json`

   If `pdf_assets` is present in the bundle, use it for semantic figure selection:
   - inspect page-level image metadata
   - inspect figure candidate pages and candidate images from `figure_plan`
   - match likely figures by page proximity, caption context, and candidate snippets
   - keep the final semantic matching decision on the model side
   Build the note in placeholder-first order:
   - plan placeholders for all major figures/tables that matter to the note
   - replace a placeholder with a real image only when the candidate is good enough
   - keep the original paper figure/table id in either case
   - when keeping a placeholder, use the stable four-line callout format:
     - `> [!figure] Fig. 3 ...`
     - `> 建议位置：...`
     - `> 放置原因：...`
     - `> 当前状态：...`
   If you decide to insert a real image instead of leaving a placeholder:
   - call `scripts/materialize_figure_asset.py`
   - copy the chosen candidate image into the vault
   - insert the returned Obsidian embed into the note
   This figure step belongs to the same note-generation task:
   - do not stop after a text-only draft just to ask the user whether figures should be inserted
   - finish the replacement-or-placeholder decision before final save
   - if no image is good enough, keep the placeholder and still finish the note

3. Infer the paper type yourself from the bundle.
   Do not rely on old script classifications unless you are debugging.

4. Make an explicit short `note_plan` artifact before drafting.
   Do not rely on a hidden "I'll think about it and then write" step.
   The plan should decide:
   - which sections deserve the most weight
   - which sections need `###` subheadings
   - which 3 to 6 numbers matter most
   - which comparisons are the real ones
   - which paper-specific sections should be added
   Examples:
   - `### 数据构建`
   - `### 量表代理特征抽取`
   - `### 关键创新`
   - `### 为什么结果成立`
   - `### 哪些地方容易被误读`
   Prefer a compact visible block such as:
   - `<note_plan>...</note_plan>`
   - or a temporary planning file saved before the final note
   The plan should be concise and structured, not a long free-form chain-of-thought dump.
   The plan should also explicitly decide:
   - whether formulas are needed
   - which training objective, factorization, or complexity expression must appear
   - which method subsections must be deep enough for a replication-minded engineer

5. Write the full Markdown note yourself in Chinese.
   The note should be based on evidence, section previews, and the explicit `note_plan`, but the prose should be your own.
   Write as a top-tier researcher preparing a replication-oriented lab note, not as a summary assistant.
   Keep the early section order stable:
   - `核心信息`
   - `原始摘要`
   - `一句话总结`
   If abstract metadata is available, include it explicitly rather than letting the summary replace it.
   Inside `原始摘要`, prefer:
   - `### 英文原文`
   - `### 中文翻译`
   The Chinese translation should preserve the author's abstract meaning rather than collapsing into a short summary.

6. Run `scripts/lint_note.py` on the drafted note.
   If lint fails:
   - revise the note
   - rerun lint
   - do not write to Obsidian yet

7. Only after lint passes, run `scripts/write_obsidian_note.py`.
   The save step should also create the paper-local `images/` directory even when no real image was inserted.

## What The Model Must Decide

The language model, not the scripts, must decide:
- what the real contribution is
- which result matters most
- what is easy to misread
- where the paper is weak
- how much weight each section deserves
- which technical details need to be unpacked with subheadings
- how to phrase the note naturally in Chinese
- how to turn the explicit `note_plan` into the final note without exposing raw chain-of-thought
- when the note needs key LaTeX formulas
- whether the method explanation is deep enough for a technically fluent reader

## What The Model Must Not Do

- Do not quote long English evidence chunks into the final note.
- Do not repeat every extracted number just because it exists.
- Do not copy the bundle structure mechanically.
- Do not treat heuristic figure labels as paper conclusions.
- Do not delete important figure/table placeholders just because extraction only found partial crops.
- Do not flatten a technically rich paper into only broad `##` sections with no internal structure.

## Minimal Save Protocol

Recommended sequence:
1. draft note to a temporary Markdown file
2. lint it
3. save with `write_obsidian_note.py --lint-json ...`

If you already have the final Markdown in memory, `write_obsidian_note.py` also supports `--stdin`.
If you selected a real figure image, use `materialize_figure_asset.py` before the final save.
If you did not select any real figure image, still save the final note in one pass with placeholders intact.

## Pre-Save Self-Review

Before final save, explicitly review the draft against this checklist:
- does it contain concrete numbers and real comparisons?
- if this is a method paper, does it explain training, inference, and core mechanism rather than only summarize the idea?
- if formulas or complexity expressions are central to the paper, did you include the key ones in LaTeX?
- are formulas written with `$...$` or `$$...$$` rather than backticks or fenced code blocks?
- would a reader familiar with Python and deep learning tooling understand the implementation logic from the note?
- are there suspicious mid-sentence line breaks or PDF-style line wrapping artifacts left in the prose?

If any answer is clearly "no", revise before lint and save.

## Planning Artifact Rule

The model should not skip planning just because the final output looks fluent enough.

Require one explicit planning artifact per note:
- keep it short
- keep it structured
- make it inspectable
- do not turn it into a verbose hidden chain-of-thought transcript

Preferred content:
- `paper_type`
- `dominant_domain`
- `must_cover`
- `key_numbers`
- `real_comparisons`
- `section_plan`
