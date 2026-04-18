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

   Before this step, if local bibliography integration is available and the user did not provide an exact local PDF path, do a local-library-first preflight:
   - search the local Zotero library for the paper
   - if the hit is confident, materialize a trusted JSON input record with `scripts/create_input_record.py`
   - if the hit has an attachment but the integration does not expose the full path, use `scripts/locate_zotero_attachment.py`
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
   Do not rely on a hidden `I'll think about it and then write` step.
   The plan should decide:
   - which sections deserve the most weight
   - which sections need `###` subheadings
   - which 3 to 6 numbers matter most
   - which comparisons are the real ones
   - which paper-specific sections should be added
   Examples:
   - `### 数据构建`
   - `### 量表代理特征抽取`
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
   - `原文摘要翻译`
   - `创新点`
   - `一句话总结`
   If abstract metadata is available, include it explicitly rather than letting the summary replace it.
   Inside `原文摘要翻译`, use a single Chinese translation block rather than bilingual subheadings.
   The `原文摘要翻译` section itself must stay Chinese-only; do not place English abstract sentences or excerpted English original text there.
   Treat `原文摘要翻译` as a translation task: translate the original abstract into Chinese, do not rewrite it into your own paper summary.
   Do not mix in later judgments, innovation bullets, or deep-analysis content when writing `原文摘要翻译`.
   The `创新点` section should be a dedicated `##` section, not just a casual sentence inside `一句话总结` or `深度分析`.
   It should usually list 3 to 5 real innovations and briefly explain what each innovation changes or adds.

6. Run `scripts/lint_note.py` on the drafted note.
   If lint fails:
   - revise the note
   - rerun lint
   - do not write to Obsidian yet

7. After the first successful lint pass, perform `final_readability_review`.
   This is a required model-side reread of the full note.
   It is for language and expression only:
   - smooth awkward prose
   - remove stiff translations
   - rewrite ordinary English phrase leftovers into natural Chinese
   - keep stable proper nouns when forcing a translation would sound worse
   Do not use this stage to:
   - invent new facts
   - change core numbers or conclusions
   - flatten the note into a safer but shallower summary

8. If `final_readability_review` edited the note, rerun `scripts/lint_note.py`.
   Do not treat the first lint pass as still valid after language edits.

9. Only after lint passes and `final_readability_review` is complete, run `scripts/write_obsidian_note.py`.
   The save step should also create the paper-local `images/` directory even when no real image was inserted.

## Workflow Check Before Final Report

Before giving the final user-facing report, mentally or explicitly verify each required stage:
- `resolve_paper`
- `collect_metadata`
- `fetch_pdf`
- `extract_evidence`
- `extract_pdf_assets`
- `plan_figures`
- `build_synthesis_bundle`
- `note_plan`
- `write_note`
- `lint_note`
- `final_readability_review`
- `write_obsidian_note`

Rules:
- do not describe the workflow as fully completed unless every required stage above is actually complete
- if the workflow stops early, explicitly state:
  - the current blocked or pending stage
  - which stages are already complete
  - which downstream required stages are still incomplete
  - why the workflow cannot yet be treated as complete
- do not let slowness, inconvenience, or imperfect intermediate outputs justify skipping a remaining required stage

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
- Do not reinterpret `vault configured but permission unavailable` as permission to silently downgrade into workspace mode.
- Do not skip creation of the paper-local `images/` directory just because the current environment cannot write it yet.
- Do not present a vault-external save as if the formal Obsidian save already succeeded.
- Do not present a partially executed workflow as if it were the full DeepPaperNote workflow.
- Do not let convenience language hide which required stage is still pending.
- Do not collapse `draft complete` into `note complete`.
- Do not write for the linter.
- Do not invent facts, failed settings, mechanism details, or comparisons just to satisfy lint or section checks.
- Do not insert empty compliance prose whose only purpose is to look structurally complete.
- Do not twist a sentence into unnatural Chinese just to avoid a mixed-language warning.

## Minimal Save Protocol

Recommended sequence:
1. draft note to a temporary Markdown file
2. lint it
3. run `final_readability_review`
4. rerun lint if the readability review edited the note
5. save with `write_obsidian_note.py --lint-json ...`

Save-mode rule:
- if no Obsidian vault is configured, workspace fallback is allowed
- if an Obsidian vault is configured, treat that vault as the required target
- if the configured vault or its `images/` subdirectory is not currently writable, request permission escalation before saving
- if permission is refused, stop and clearly report that the note has not been written to Obsidian
- only if the user is asked again and explicitly approves workspace fallback may the save target change

If you already have the final Markdown in memory, `write_obsidian_note.py` also supports `--stdin`.
If you selected a real figure image, use `materialize_figure_asset.py` before the final save.
If you did not select any real figure image, still save the final note in one pass with placeholders intact.

## Completion-Language Rule

Use completion language precisely:
- say `已完成` only when the required workflow is actually complete
- say `已生成草稿` when synthesis finished but lint or save is still pending
- say `已通过校验` only when lint actually ran and passed
- say `已保存到 Obsidian` only when the formal write step actually succeeded
- do not treat `lint passed` as meaning the note is fully polished
- if `final_readability_review` has not been completed yet, say the draft passed script lint but is still pending final language review
- do not treat temporary Markdown files, partial figure work, or incomplete downstream stages as equivalent to full workflow completion

## Pre-Save Self-Review

Before final save, explicitly review the draft against this checklist:
- does it contain concrete numbers and real comparisons?
- if this is a method paper, does it explain training, inference, and core mechanism rather than only summarize the idea?
- if formulas or complexity expressions are central to the paper, did you include the key ones in LaTeX?
- are formulas written with `$...$` or `$$...$$` rather than backticks or fenced code blocks?
- if the note includes LaTeX formulas, did you verify that the final Markdown uses directly renderable TeX rather than double-escaped commands such as `\\tau` or `\\begin`?
- would a reader familiar with Python and deep learning tooling understand the implementation logic from the note?
- are there suspicious mid-sentence line breaks or PDF-style line wrapping artifacts left in the prose?
- after script lint passes, have you reread the note once more for readability rather than stopping at formal compliance?
- are there still any ordinary English phrase leftovers that should become natural Chinese?
- are there any stiff translations, empty compliance sentences, or lines that sound written for lint rather than for a human reader?

If any answer is clearly `no`, revise before lint and save.

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
