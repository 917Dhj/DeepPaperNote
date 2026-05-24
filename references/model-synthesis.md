# Model Synthesis

This file is a lightweight final-mile guide.
It is not a second router that requires reading the rest of `references/`.
For normal runs, `SKILL.md` plus the generated `synthesis_bundle.json` is the required context; use topic references only when a specific stage needs more detail.

## Execution Loop

1. Run `scripts/run_pipeline.py` from the resolved paper input.
   This should produce deterministic artifacts such as metadata, `source_manifest.json`, `raw_sections.jsonl`, PDF assets, figure/table decisions, and `synthesis_bundle.json`.

2. Read `synthesis_bundle.json` directly.
   Inspect:
   - `coverage`
   - `source_manifest`
   - `source_index`
   - `references.candidates`
   - `figure_plan`
   - `figure_table_manifest`
   - `pdf_assets`
   - `writing_contract`
   Then read the canonical raw source records named by `source_manifest.raw_sections_path`.

3. Create the canonical planning artifact before drafting.
   The canonical artifact is a short JSON file such as `<note>.plan.json` or a run-scoped `*_note_plan.json`.
   Pass it to `scripts/lint_note.py --plan-file ...` when linting.
   In interactive contexts, a compact `<note_plan>...</note_plan>` block may additionally be shown as display-only context, but it does not replace the JSON file.
   Keep the plan short, structured, and inspectable; do not expose a verbose chain-of-thought transcript.
   Choose `note_plan.paper_type` from `writing_contract.paper_type_selection.allowed_paper_types` before drafting.
   For substantive sections, include `evidence_sources` as valid `section_id` values or valid page ranges from the source manifest.
   Also include the analysis coverage fields required by the writing contract:
   - `central_claims`: each item states `claim`, `supporting_evidence`, `what_it_actually_proves`, and `what_it_does_not_prove`
   - `claim_boundaries`: boundaries that the final note must not overstate
   - `negative_or_limiting_results`: ablations, null results, weaker tasks, author limitations, or explicit "not reported" gaps that constrain the conclusion
   - `mechanism_result_map`: paper-specific links from mechanisms, protocols, constructs, or data decisions to the result pattern or diagnostic evidence they explain
   - `comparative_positioning`: how the paper differs from strong baselines, prior routes, human/clinical references, or obvious alternatives, and why that difference matters
   - `reuse_takeaways`: research or engineering takeaways that are specific enough to use later
   - `followup_questions`: concrete replication, engineering, research, or validity checks to carry forward

4. Run `scripts/lint_grounding.py --note-plan ... --source-manifest ... --bundle-json ... --figure-decisions ...`.
   Do this before drafting from the plan.
   Old broad references such as `synthesis_bundle.evidence.method_evidence` are invalid.

5. Draft the note in Chinese from the bundle, raw source records, and the explicit plan.
   The model must decide emphasis, contribution, mechanism, limitations, formula needs, figure semantics, and natural Chinese phrasing.
   Do not copy the bundle mechanically or treat script heuristics as conclusions.

6. Finish the figure decision inside the same task.
   Start from semantic placeholders.
   Insert a real image only when identity match and visual usability are both strong; otherwise keep the placeholder.
   If a real image is selected, the final note must reference the selected `images/<filename>` path and the save step must receive `--figure-decisions`.
   In the final note, inserted real images must be an embed followed by one italic caption line, without a redundant `[!figure]` callout for the same figure.

7. Run `scripts/lint_note.py`.
   If lint fails, revise and rerun it before saving.

8. After the first successful lint pass, perform `final_quality_review`.
   This is a required analytical reread against the plan and source evidence.
   Check that the note covers the central evidence chain, key settings and numbers, mechanism-to-result explanations, comparative positioning, Discussion/Limitations conclusions, proven-versus-unproven boundaries, and paper-specific reusable takeaways or follow-up questions.
   This review may return to the source records and revise missing analytical content, but it must not invent facts.

9. After `final_quality_review` passes, perform `final_readability_review`.
   This is a required full-note reread for language and expression only.
   It may smooth awkward prose, remove stiff translations, and rewrite ordinary English phrase leftovers into natural Chinese.
   It must not invent facts, change core numbers, or flatten the note into a safer but shallower summary.
   If either final review edits the note, rerun lint.

10. Save only after lint passes and both final reviews are complete.
   If an Obsidian vault is configured, it is the required target.
   The save step should create the paper-local `images/` directory even when no real image was inserted.
   When `figure_table_decisions.json` contains `insert` rows, pass it to `write_obsidian_note.py --figure-decisions ...`; the writer copies those selected images and refuses the save if the note does not reference them.

## Required Planning Shape

Required JSON keys:
- `paper_type`
- `paper_type_rationale`
- `dominant_domain`
- `must_cover`
- `key_numbers`
- `real_comparisons`
- `central_claims`
- `claim_boundaries`
- `negative_or_limiting_results`
- `mechanism_result_map`
- `comparative_positioning`
- `reuse_takeaways`
- `followup_questions`
- `section_plan`

The plan should state which sections need depth, which claims are supported by which source evidence, what those claims do and do not prove, which comparisons and numbers matter, how mechanisms or protocols explain the result pattern, how the paper is positioned against alternatives, whether formulas are needed, which limiting results or missing evidence constrain the conclusion, which figure/table placeholders are important, which takeaways are reusable beyond the current paper, and which follow-up checks a reader should keep.

## Completion Language

Use completion language precisely:
- say `已生成草稿` when drafting is done but lint, readability review, or save is still pending
- say `已通过校验` only when lint actually ran and passed
- say `已保存到 Obsidian` only when the formal write step actually succeeded
- say `笔记已完成` only when the required workflow is actually complete

Do not treat temporary Markdown files, partial figure work, or incomplete downstream stages as equivalent to a finished DeepPaperNote run.
