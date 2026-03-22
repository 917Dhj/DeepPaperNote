---
name: DeepPaperNote
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
- `/deeppapernote doctor`
- `/deeppapernote start`
- `查看 deeppapernote 的可用情况`
- `deeppapernote 有什么功能`
- `帮我检查 deeppapernote 现在能不能用`

This skill is intentionally narrow:
- it handles one paper at a time
- it does not update daily reading lists
- it does not treat a shallow abstract rewrite as a successful output

It also supports a lightweight documentation/setup-assistant mode.
When the user asks what DeepPaperNote can do, whether it is available, or how to configure it:
- do not force a paper-writing workflow
- inspect the local environment first
- explain the current setup state
- offer to help complete missing configuration

## Core Standard

The finished note must be more than a summary. It should reconstruct the paper's argument:
- what problem it solves
- how the task is defined
- what data or materials it uses
- how the method or analysis actually works
- what results matter most
- what the paper does not prove
- why the paper is worth keeping

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
8. have Codex/GPT read the bundle and write the note
9. lint the final note
10. write into Obsidian

Read [references/workflow.md](references/workflow.md) for the full pipeline and data contracts.
Read [references/architecture.md](references/architecture.md) for the separation between the reusable core workflow and the Codex-specific adapter layer.
Read [references/evidence-first.md](references/evidence-first.md) before drafting a high-quality note so that the note is planned around evidence rather than headings alone.
Read [references/deep-analysis.md](references/deep-analysis.md) before writing the final note body.
Read [references/final-writing.md](references/final-writing.md) before turning the structured artifacts into the final user-facing note.
Read [references/model-synthesis.md](references/model-synthesis.md) for the preferred model-first execution loop after the synthesis bundle is ready.

## Setup-Assistant Mode

If the user asks things like:
- `/deeppapernote doctor`
- `/deeppapernote start`
- `查看 deeppapernote 的可用情况`
- `deeppapernote 有什么功能`
- `帮我检查 deeppapernote 现在能不能用`

then switch into setup-assistant mode:
1. run `scripts/check_environment.py`
2. if the current Codex environment supports Zotero MCP, check whether it is available
3. explain:
   - what DeepPaperNote can do
   - which required items are already configured
   - which optional items are available
   - which recommended items are still missing
4. group the final status into:
   - already configured
   - recommended next configuration
   - optional but helpful enhancements
5. if Codex can directly help complete a missing configuration, offer that next

In setup-assistant mode, prefer a practical environment report over generic documentation text.

## Tool and Source Priority

Prefer the strongest available source in this order:
1. local PDF path given by the user
2. local Zotero item and local Zotero attachment if available
3. DOI and publisher metadata
4. arXiv or open-access PDF sources
5. Semantic Scholar or OpenAlex for metadata backfill

When Zotero is available, use Zotero MCP tools first for local-library context. Do not require Zotero to succeed. The skill must still work when the paper is not in the user's library.

Zotero-first rule:
- If the user input is a title, DOI, or arXiv id, first search the local Zotero library.
- If Zotero finds the paper, treat that result as the canonical identity resolution step.
- If the attachment path is not exposed by MCP, use `scripts/locate_zotero_attachment.py` with the attachment key and filename to find the local PDF under the user's Zotero storage.
- If a local attachment path is available, pass it forward as the preferred PDF source.
- If no local attachment is found, still use the Zotero-resolved metadata to avoid title ambiguity, then fall back to network PDF acquisition only for the file itself.
- Do not let a weaker title-only internet match override a confident Zotero hit.

## Output Rules

- The default output is a Markdown note written into the Obsidian vault when configured.
- If no Obsidian vault is configured, DeepPaperNote should fall back to saving into the current workspace instead of failing outright.
- By default, each paper should be written into its own same-name folder, with the note and images stored together.
- The note must use real heading levels: `#`, `##`, and `###`.
- High-quality notes should usually contain multiple meaningful `###` subheadings in the technical sections when the paper is non-trivial.
- The note must include figure/table placeholders for all major visuals rather than silently skipping them.
- Real images may replace some placeholders, but only if they clearly match the corresponding paper figure/table.
- Figure captions in the note must preserve the original paper numbering such as `Fig. 1` or `Table 2`.
- The note must pass a style gate: no mixed Chinese-English prose lines except stable proper nouns or citation metadata.
- If PDF or evidence quality is insufficient for a real deep note, fail closed or clearly label the output as degraded.

Model-first rule:
- scripts may gather and structure evidence
- scripts must not be the primary mechanism for understanding the paper
- final paper understanding and note writing belong to Codex/GPT

Use [references/note-quality.md](references/note-quality.md) for quality checks.
Use [references/paper-types.md](references/paper-types.md) for domain adaptation.
Use [references/obsidian-format.md](references/obsidian-format.md) for Markdown and vault conventions.
Use [references/figure-placement.md](references/figure-placement.md) for figure placeholder rules.
Use [references/evidence-first.md](references/evidence-first.md) when deciding how to turn bundle evidence into an actual note plan.
Use [references/deep-analysis.md](references/deep-analysis.md) when the user expects a note that feels like a real long-term research note.
Use [references/metadata-sources.md](references/metadata-sources.md) when metadata is incomplete.
Use [references/architecture.md](references/architecture.md) when deciding whether a change belongs in the reusable core or only in the Codex adapter.
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
1. if Zotero MCP is available, search the local Zotero library first
2. if Zotero resolves the paper, inspect child attachments; if needed use `scripts/locate_zotero_attachment.py` to find the local PDF
3. use `scripts/create_input_record.py` to materialize a trusted JSON input record
4. run `scripts/run_pipeline.py` on the JSON record or original exact source to produce the bundle
5. read the bundle yourself
6. write the note in your own words
7. lint the note
8. write it into Obsidian only after lint passes

Setup-assistant usage pattern:
1. run `scripts/check_environment.py`
2. summarize what is already usable
3. explain what each missing item affects
4. offer to configure missing items rather than just listing docs

Current status:
- the single-paper deterministic core pipeline is implemented as an MVP
- `scripts/run_pipeline.py` now defaults to building a model-facing synthesis bundle
- `scripts/write_obsidian_note.py` can write the final note into a target vault
- patch the scripts rather than replacing the workflow ad hoc

## Limits

- If the paper identity is ambiguous, confirm before writing.
- If the PDF is unavailable and full-text evidence is too thin, do not present a note as if it were a full deep read.
- Placeholder-first figure planning is required; image extraction is optional and must never reduce textual coverage.
