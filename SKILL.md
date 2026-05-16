---
name: deeppapernote
description: Generate a high-quality deep-reading note for a single paper and write it into an Obsidian-style vault. Use when the user gives a paper title, DOI, URL, arXiv ID, Zotero item, or local PDF and wants a polished Markdown note with strong structure, evidence-based analysis, and figure placeholders.
---

# DeepPaperNote

Use this skill when the user wants one outcome:
- read one paper carefully
- generate a high-quality Markdown note
- save the note into an Obsidian-style vault when configured, or into the current workspace when no vault is configured

Chinese trigger examples:
- `给这篇论文生成深度笔记`
- `写一篇高质量论文精读笔记`
- `把这篇文章整理成 obsidian 笔记`
- `读这篇论文并生成 md 笔记`

This skill is intentionally narrow:
- it handles one paper at a time
- it does not update daily reading lists
- it does not treat a shallow abstract rewrite as a successful output
- it does not split the public entrypoint into separate setup, troubleshooting, or start commands

## Core Standard

The finished note must be more than a summary. It should reconstruct the paper's argument:
- what problem it solves
- how the task is defined
- what data or materials it uses
- how the method or analysis actually works
- what results matter most
- what the paper does not prove
- why the paper is worth keeping

Default writer persona:
- a top-tier researcher or algorithm engineer
- writing a replication-oriented lab note
- not writing a popular-science explanation
- assuming the reader can follow Python, PyTorch, training loops, and evaluation logic

The note must adapt to the paper type. Use the same base structure, but shift emphasis for AI methods, benchmarks, clinical studies, and humanities or social-science papers.

## Workflow

Follow this order:
1. resolve the paper identity
2. collect metadata
3. acquire the PDF or full text
4. extract evidence
5. extract PDF image assets
6. plan figure placement
7. build the synthesis bundle
8. have the model read the bundle and plan the note
9. have the model write the note
10. lint the final note — if the lint output contains `passes_style_gate: false`, apply the Style Gate Enforcement rule before advancing to step 11 or 12
11. perform `final_readability_review` after lint passes
12. write into Obsidian

This is the required workflow for a normal single-paper note request, not a loose suggestion.
Unless this skill explicitly marks a stage as optional, required stages must not be silently skipped, reordered into a shortcut, or treated as complete just because a partial artifact already exists.

Global no-short-circuit rule:
- do not stop after only the early stages and present the workflow as finished
- do not treat slowness, inconvenience, or temporary uncertainty as permission to bypass a required stage
- do not replace the declared workflow with an improvised shortcut
- if a required stage fails, only do one of three things:
  - retry that stage
  - enter a fallback that is explicitly allowed by this skill
  - stop and report which stage is blocked and which downstream required stages remain incomplete
- do not describe the whole task as complete while required downstream stages are still pending

Completion-language rule:
- say `笔记已完成` only when the required workflow is actually complete
- say `已生成草稿` when drafting is done but lint, final readability review, or save is still pending
- say `已通过校验` only when lint has actually been run and passed
- say `已保存到 Obsidian` only when the write step has actually succeeded
- do not treat `lint 已通过` as equivalent to `整篇笔记已经润色完成`
- if final readability review is still pending, explicitly say the draft passed script lint but has not finished final language review
- if the workflow stopped early, name the current stage and the still-missing required stages instead of using completion language
- lint is a floor, not the writing objective

Read [references/workflow.md](references/workflow.md) for the full pipeline and data contracts.
Read [references/architecture.md](references/architecture.md) for the separation between the reusable core workflow and the platform-adapter layer.
Read [references/evidence-first.md](references/evidence-first.md) before drafting a high-quality note so that the note is planned around evidence rather than headings alone.
Read [references/deep-analysis.md](references/deep-analysis.md) before writing the final note body.
Read [references/final-writing.md](references/final-writing.md) before turning the structured artifacts into the final user-facing note.
Read [references/model-synthesis.md](references/model-synthesis.md) for the preferred model-first execution loop after the synthesis bundle is ready.

## Tool and Source Priority

Prefer the strongest available source in this order:
1. local PDF path given by the user
2. local Zotero item and local Zotero attachment if available
3. DOI and publisher metadata
4. arXiv or open-access PDF sources
5. Semantic Scholar or OpenAlex for metadata backfill

Before resolving the paper, actively check Zotero integration: attempt to call the Zotero MCP tool (for example, search for the paper title or list libraries). If the tool responds without error, Zotero is available and the local-library-first rule below applies. If the call fails or the tool is not present, record "Zotero not available" and proceed without it. Do not skip this check — the check itself determines whether local-library-first applies.

Local-library-first rule (applies only when the Zotero check above succeeds):
- search the local Zotero library first using the paper title, DOI, or arXiv id
- If Zotero finds the paper, treat that result as the canonical identity resolution step.
- If the attachment path is not exposed by the integration, use `scripts/locate_zotero_attachment.py` with the attachment key and filename to find the local PDF under the user's Zotero storage.
- If a local attachment path is available, pass it forward as the preferred PDF source.
- If no local attachment is found, still use the library-resolved metadata to avoid title ambiguity, then fall back to network PDF acquisition only for the file itself.
- Do not let a weaker title-only internet match override a confident local-library hit.

## Output Rules

- The default output is a Markdown note written into the Obsidian vault when configured.
- Workspace fallback is allowed only when no Obsidian vault is configured at all.
- Before using workspace fallback, you must ask the user: "I don't see an Obsidian vault configured. Do you have a vault path you'd like me to save this note to? If yes, please provide the path. If no, I'll save to the current workspace instead." Do not write anywhere until the user responds.
- If an Obsidian vault is configured, DeepPaperNote must treat that vault as the required save target rather than silently switching output roots.
- If the configured vault or its paper-local subdirectories are outside the current writable scope, DeepPaperNote must ask the user for permission escalation instead of downgrading to workspace output.
- If the user refuses that permission escalation, DeepPaperNote must clearly report that the note has not been saved into Obsidian yet.
- After such a refusal, DeepPaperNote may save to the workspace only if it asks again and receives explicit user consent for that fallback.
- By default, each paper should be written into its own same-name folder, with the note and images stored together.
- The note should never default to the bare `Research/Papers` root. Choose a domain folder first.
- Domain selection should be conservative: prefer an existing domain folder in the user's vault when there is a reasonable match; only create a new domain folder when no existing domain fits well.
- A normal note-generation request should complete in one pass: note text, figure placeholder decisions, image materialization when confident, and final save.
- Do not stop after a text-only draft just to ask whether the user wants figures inserted. Finish the figure replacement decision inside the same task unless the user explicitly asked for text only.
- Always create the paper-local `images/` folder during final save, even if no high-confidence images were materialized.
- The `images/` folder is part of the required save protocol, not an optional cleanup step. If permission is missing, request it; do not skip the directory.
- Do not present a workspace write as if the Obsidian save already succeeded.
- The note must use real heading levels: `#`, `##`, and `###`.
- The note should include `原文摘要翻译` near the beginning when abstract metadata is available, before `一句话总结`.
- When abstract metadata is available, `原文摘要翻译` should directly translate the original paper abstract into Chinese rather than restating it as your own summary.
- The `原文摘要翻译` section itself should be Chinese-only; do not place English abstract sentences or English paragraph excerpts in that section.
- Do not mix later judgments, innovation summaries, or hindsight explanations into `原文摘要翻译`; keep it as the original abstract translated into Chinese.
- The note should include a dedicated `创新点` section immediately after `原文摘要翻译` and before `一句话总结`.
- The `创新点` section should not be empty praise. It should enumerate the paper's actual innovations and briefly explain why each one matters.
- High-quality notes should usually contain multiple meaningful `###` subheadings in the technical sections when the paper is non-trivial.
- The note must include figure/table placeholders for all major visuals rather than silently skipping them.
- Every kept figure/table placeholder must appear directly under the most relevant analytical section named by its `建议位置`; do not collect unresolved placeholders in catch-all sections such as `剩余图表占位` or `Remaining figures`.
- Every kept figure/table placeholder must use the standard `> [!figure]` callout format with `建议位置`, `放置原因`, and `当前状态`; do not use ordinary paragraph markers such as `[图表占位 | Fig. 1]`, `图表占位：Table 2`, or `Figure Placeholder | Fig. 3`.
- Real images may replace some placeholders, but only if they clearly match the corresponding paper figure/table.
- When inserting a real image, prefer the `obsidian_embed` returned by `scripts/materialize_figure_asset.py`.
- Figure captions in the note must preserve the original paper numbering such as `Fig. 1` or `Table 2`.
- The note must pass a style gate: no mixed Chinese-English prose lines except stable proper nouns or citation metadata.
- Style gate enforcement: when `lint_note.py` output contains `passes_style_gate: false`, fix the reported issues and re-run lint. Keep fixing and re-running until lint passes — multiple rounds are normal and expected. Do not decide that any failure is an acceptable exception — proper nouns, math formulas, and citation metadata are not automatic exemptions. Only escalate to the user if the same failures appear unchanged across multiple rounds with no reduction, indicating the model is unable to make further progress independently.
- If PDF or evidence quality is insufficient for a real deep note, fail closed or clearly label the output as degraded.

Model-first rule:
- scripts may gather and structure evidence
- scripts must not be the primary mechanism for understanding the paper
- final paper understanding and note writing belong to the model
- before writing the final note, create an explicit short `note_plan` artifact rather than relying on hidden planning only
- prefer a compact structured plan such as `<note_plan>...</note_plan>` or an equivalent temporary planning file
- do not require or expose a long free-form `<thinking>` block
- for technical papers, prefer replication-grade explanation over high-level summary
- if formulas, objectives, or complexity expressions are central, include the key ones in the final note
- render math as `$...$` or `$$...$$`, not as inline code or fenced code blocks
- before final save, explicitly self-review whether the note contains enough technical detail, key numbers, and any necessary formulas
- after script lint passes, reread the full note once more for readability; do not stop at formal compliance only
- in that final readability review, ordinary English phrase leftovers should usually be rewritten into natural Chinese, while stable proper nouns may remain in English
- do not use the final readability review to invent new facts, empty filler text, or shallower but safer wording just to satisfy lint

Use [references/note-quality.md](references/note-quality.md) for quality checks.
Use [references/paper-types.md](references/paper-types.md) for domain adaptation.
Use [references/obsidian-format.md](references/obsidian-format.md) for Markdown and vault conventions.
Use [references/figure-placement.md](references/figure-placement.md) for figure placeholder rules.
Use [references/evidence-first.md](references/evidence-first.md) when deciding how to turn bundle evidence into an actual note plan.
Use [references/deep-analysis.md](references/deep-analysis.md) when the user expects a note that feels like a real long-term research note.
Use [references/metadata-sources.md](references/metadata-sources.md) when metadata is incomplete.
Use [references/architecture.md](references/architecture.md) when deciding whether a change belongs in the reusable core or only in the platform-adapter layer.
Use [references/final-writing.md](references/final-writing.md) when drafting the final note in natural language.

## Scripts

Use these bundled scripts rather than rebuilding the workflow from scratch:
- `scripts/check_environment.py`
- `scripts/create_input_record.py`
- `scripts/locate_zotero_attachment.py`
- `scripts/resolve_paper.py`
- `scripts/run_pipeline.py`
- `scripts/collect_metadata.py`
- `scripts/fetch_pdf.py`
- `scripts/extract_evidence.py`
- `scripts/extract_pdf_assets.py`
- `scripts/plan_figures.py`
- `scripts/build_synthesis_bundle.py`
- `scripts/lint_note.py`
- `scripts/materialize_figure_asset.py`
- `scripts/write_obsidian_note.py`

Preferred usage pattern:
1. if local bibliography integration is available, search the local Zotero library first
2. if the library resolves the paper, inspect child attachments; if needed use `scripts/locate_zotero_attachment.py` to find the local PDF
3. use `scripts/create_input_record.py` to materialize a trusted JSON input record
4. run `scripts/run_pipeline.py` on the JSON record or original exact source to produce the bundle
5. read the bundle yourself
6. write the note in your own words
7. lint the note
8. write it into Obsidian only after lint passes and the final readability review is complete

Python interpreter rule:
- DeepPaperNote requires Python `>=3.10`.
- Before running repository scripts, check the interpreter version instead of assuming the current shell default is compatible.
- If the default `python3` is below `3.10`, automatically look for another available interpreter that satisfies the requirement, such as `python3.12`, `python3.11`, `python3.10`, `/opt/anaconda3/bin/python3`, `/opt/homebrew/bin/python3`, or `/usr/local/bin/python3`.
- Use the first compatible interpreter you find and continue with that interpreter for the repository scripts in the current task.
- If no compatible interpreter is available, stop and clearly tell the user which interpreter was found, which version it reported, and that DeepPaperNote requires Python `>=3.10`.

Troubleshooting rule:
- use `scripts/check_environment.py` only when a concrete dependency or integration question is blocking execution
- explain required dependencies, optional enhancements, and downgrade behavior directly rather than redirecting the skill into a separate troubleshooting workflow
- do not feature environment inspection as a public pseudo-command surface

Current status:
- the single-paper deterministic core pipeline is implemented as an MVP
- `scripts/run_pipeline.py` now defaults to building a model-facing synthesis bundle
- `scripts/write_obsidian_note.py` can write the final note into a target vault
- patch the scripts rather than replacing the workflow ad hoc

## Limits

- If the paper identity is ambiguous, confirm before writing.
- If the PDF is unavailable and full-text evidence is too thin, do not present a note as if it were a full deep read.
- Placeholder-first figure planning is required; image extraction is optional and must never reduce textual coverage.
