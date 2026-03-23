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

4. Make a short internal note plan before drafting.
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

5. Write the full Markdown note yourself in Chinese.
   The note should be based on evidence and section previews, but the prose should be your own.

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
