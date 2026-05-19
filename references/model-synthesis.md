# Model Synthesis

This file is a lightweight final-mile guide.
It is not a second router that requires reading the rest of `references/`.
For normal runs, `SKILL.md` plus the generated `synthesis_bundle.json` is the required context; use topic references only when a specific stage needs more detail.

## Execution Loop

1. Run `scripts/run_pipeline.py` from the resolved paper input.
   This should produce deterministic artifacts such as metadata, evidence, PDF assets, figure plan, and `synthesis_bundle.json`.

2. Read `synthesis_bundle.json` directly.
   Inspect:
   - `coverage`
   - `evidence`
   - `candidate_chunks`
   - `section_texts`
   - `references.candidates`
   - `figure_plan`
   - `pdf_assets`
   - `writing_contract`

3. Create the canonical planning artifact before drafting.
   The canonical artifact is a short JSON file such as `<note>.plan.json` or a run-scoped `*_note_plan.json`.
   Pass it to `scripts/lint_note.py --plan-file ...` when linting.
   In interactive contexts, a compact `<note_plan>...</note_plan>` block may additionally be shown as display-only context, but it does not replace the JSON file.
   Keep the plan short, structured, and inspectable; do not expose a verbose chain-of-thought transcript.

4. Draft the note in Chinese from the bundle and the explicit plan.
   The model must decide emphasis, contribution, mechanism, limitations, formula needs, figure semantics, and natural Chinese phrasing.
   Do not copy the bundle mechanically or treat script heuristics as conclusions.

5. Finish the figure decision inside the same task.
   Start from semantic placeholders.
   Insert a real image only when identity match and visual usability are both strong; otherwise keep the placeholder.
   If a real image is selected, materialize it before the final save and prefer the returned Obsidian embed.

6. Run `scripts/lint_note.py`.
   If lint fails, revise and rerun it before saving.

7. After the first successful lint pass, perform `final_readability_review`.
   This is a required full-note reread for language and expression only.
   It may smooth awkward prose, remove stiff translations, and rewrite ordinary English phrase leftovers into natural Chinese.
   It must not invent facts, change core numbers, or flatten the note into a safer but shallower summary.
   If the review edits the note, rerun lint.

8. Save only after lint passes and `final_readability_review` is complete.
   If an Obsidian vault is configured, it is the required target.
   The save step should create the paper-local `images/` directory even when no real image was inserted.

## Required Planning Shape

Required JSON keys:
- `paper_type`
- `dominant_domain`
- `must_cover`
- `key_numbers`
- `real_comparisons`
- `section_plan`

The plan should state which sections need depth, which comparisons and numbers matter, whether formulas are needed, and which figure/table placeholders are important.

## Completion Language

Use completion language precisely:
- say `已生成草稿` when drafting is done but lint, readability review, or save is still pending
- say `已通过校验` only when lint actually ran and passed
- say `已保存到 Obsidian` only when the formal write step actually succeeded
- say `笔记已完成` only when the required workflow is actually complete

Do not treat temporary Markdown files, partial figure work, or incomplete downstream stages as equivalent to a finished DeepPaperNote run.
