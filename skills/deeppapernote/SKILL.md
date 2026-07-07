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
3. acquire the best available PDF
4. extract canonical raw source text: `*_raw_sections.jsonl`, `*_source_manifest.json`, and optional derived `*_full_text.md`
5. extract structural indexes and PDF assets
6. plan figure placement
7. build the full figure/table decision table
8. build the manifest synthesis bundle
9. have the model read the bundle plus raw sections and plan the note
10. run grounding lint on the note plan before drafting from it
11. have the model write the note
12. lint the final note — if the lint output contains `passes_style_gate: false`, apply the Style Gate Enforcement rule before advancing to step 13, 14, or 15
13. perform `final_quality_review` after lint passes
14. perform `final_readability_review` after the quality review passes
15. write into Obsidian

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

## Core Execution Contract

`SKILL.md` plus the generated `synthesis_bundle.json` must be enough to complete a normal note-generation run.
Files under `references/` are optional stage-specific deep dives, not a default reading checklist.

Non-negotiable rules:
- evidence-first: draft from the synthesis bundle, `source_manifest`, raw sections, coverage metadata, explicit `note_plan`, and inspected paper evidence; never finish from title/abstract/headings alone
- raw-source authority: for ordinary PDFs, `*_raw_sections.jsonl` and `*_source_manifest.json` are the canonical reading material; old top-N evidence buckets, truncated `section_texts`, and `candidate_chunks` are not model-facing writing inputs
- fail-closed: if a usable PDF or sufficient evidence cannot be obtained after supported acquisition paths, stop and ask for better source material rather than producing a finished degraded note
- model-first: scripts structure evidence, but the model must decide emphasis, contribution, mechanism, limitations, and final Chinese prose
- explicit planning: before drafting, save a compact JSON `note_plan` such as `<note>.plan.json` or `*_note_plan.json`; pass it to `scripts/lint_note.py --plan-file ...`
- grounding gate: after the JSON `note_plan` exists, run `scripts/lint_grounding.py --note-plan ... --source-manifest ... --bundle-json ... --figure-decisions ...`; each substantive section must cite valid `section_id` values or valid page ranges
- required structure: include the canonical required sections, with `原文摘要翻译` before `一句话总结` and a dedicated `创新点` section immediately after `原文摘要翻译`
- abstract translation: when abstract metadata exists, `原文摘要翻译` is a faithful Chinese translation of the original abstract, not a bilingual block and not the model's own summary
- mechanism depth: method, framework, and system papers should include `### 机制流程` under `方法主线`, normally as a 3 to 4 step numbered flow with input, operation, and output destination
- placeholder-first figures: plan major figure/table placeholders first; replace one only when identity match and visual usability are both strong; otherwise keep the placeholder
- final quality gates: lint is a floor; after lint passes, first run `final_quality_review` for analytical depth, then run `final_readability_review` for language polish, and rerun lint if either review edits the note
- Obsidian-first save: if a vault is configured, treat it as the required target, create the paper-local `images/` directory, and never present a fallback/workspace write as a successful vault save

Reference usage policy:
- do not load every reference file by default
- consult `references/workflow.md` only for detailed data contracts or pipeline debugging
- consult `references/evidence-first.md`, `references/deep-analysis.md`, or `references/final-writing.md` only when the paper is complex or the draft is too shallow
- consult `references/figure-placement.md` only for ambiguous figure/table placement or image replacement decisions
- consult `references/obsidian-format.md` only for Markdown, vault, frontmatter, or reference-link formatting details
- consult `references/note-quality.md` or `references/paper-types.md` only for final review or domain adaptation
- consult `references/metadata-sources.md` only when metadata is incomplete, and `references/architecture.md` only for repository maintenance decisions

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
- Every final note must start with an Obsidian YAML properties block above the `#` title heading. Include at least a `tags` field with a `papers/<domain>` value and useful `aliases`; include `date`, `doi`, or `arxiv_id` when known, and omit unavailable fields rather than inventing placeholders.
- `## 核心信息` must be a fixed metadata block only. Use only these fields, in this order, as `- 字段名: 值` bullets: `标题`, `标题翻译`, `作者`, `机构`, `发表时间`, `发表渠道`, `DOI`, `arXiv`, `论文链接`, `代码 / 项目`, `数据 / 资源`, `论文类型`. Omit unavailable fields; put any guide sentence, takeaway, or analysis in `一句话总结` or a later section instead.
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
- Real images replace placeholders when they clearly match the corresponding paper figure/table and pass the visual-usability gate.
- When inserting a real image, use the `relative_markdown_embed` from `figure_table_decisions.json`; final save with `scripts/write_obsidian_note.py --figure-decisions ...` copies the image into the paper-local `images/` directory.
- When a real image is inserted, render it as the Obsidian embed or Markdown image embed followed immediately by one italic caption line.
- Do not keep a redundant `> [!figure]` placeholder callout for the same inserted real figure.
- Figure captions in the note must preserve the original paper numbering such as `Fig. 1` or `Table 2`.
- If a figure/table candidate is marked usable and has a real image path, insert the real image. Do not keep a placeholder merely because the figure/table is lower priority, supplemental, already summarized in text, or less central than another inserted figure.
- A kept placeholder is valid only when the image cannot be safely inserted because of a concrete visual defect, missing candidate, unresolved visual review, identity mismatch, contamination, or materialization/copy/write failure.
- For `usable_candidate` or `needs_visual_quality_check` / `review` candidates, make the visual decision only after inspecting the actual candidate image file exposed by the pipeline. Record the concrete visual observation behind the decision. Do not claim manual visual review, visual inspection, or "no reliable insertable candidate" unless the candidate image was actually opened and inspected.
- `reject_visual_quality` and `asset_candidate_missing` are fail-closed script states. They do not require manual visual review before keeping a placeholder or skipping insertion; treat them as automatic extraction outcomes unless you explicitly inspect or re-extract the source asset.
- Do not misreport missing candidates as materialization failures: `asset_candidate_missing`, empty `source_image_path`, or no independent crop means the placeholder status should say no high-confidence image candidate was extracted. Use materialization/copy/write failure language only after a real chosen image asset failed to copy or write.
- If a candidate crop contains another Figure/Table caption or a second figure body, treat that as contamination or lack of an independent crop; do not insert it and do not call it a clean usable candidate just because the target label is present.
- When `figure_table_decisions.json` contains `insert` rows, pass it to `scripts/write_obsidian_note.py --figure-decisions ...`; the writer must copy those images into the paper-local `images/` directory and refuse a note that does not reference the selected image path.
- Do not use soft reasons such as keeping the note light, values already transcribed, future lookup, or convenient back-reference as the standalone `当前状态` for a usable candidate.
- The note must pass a style gate: no mixed Chinese-English prose lines except stable proper nouns or citation metadata.
- The style gate also rejects mechanical term-replacement artifacts such as `KV缓存 of`, `批量ing`, `In相关 Researcher`, or `Single 序列 generation`; rewrite the sentence naturally instead of preserving a partially translated phrase.
- Style gate enforcement: when `lint_note.py` output contains `passes_style_gate: false`, fix the reported issues and re-run lint. Keep fixing and re-running until lint passes — multiple rounds are normal and expected. Do not decide that any failure is an acceptable exception — proper nouns, math formulas, and citation metadata are not automatic exemptions. Only escalate to the user if the same failures appear unchanged across multiple rounds with no reduction, indicating the model is unable to make further progress independently.
- If PDF or evidence quality is insufficient for a real deep note, fail closed: stop, report the blocked stage, and ask for the better PDF, OCR/source material, or other input needed to continue.

Model-first rule:
- scripts may gather and structure evidence
- scripts must not be the primary mechanism for understanding the paper
- final paper understanding and note writing belong to the model
- before writing the final note, create an explicit short `note_plan` artifact rather than relying on hidden planning only
- save `note_plan` as the canonical short JSON file outside the final note body, such as `<note>.plan.json` or a run-scoped `*_note_plan.json`
- choose `note_plan.paper_type` from the synthesis bundle's allowed paper types before drafting; the bundle must not bind writing behavior to a script-selected summary paper type
- keep the same 12 top-level note sections for every paper type, then use `contracts_by_paper_type[note_plan.paper_type].section_semantics` to interpret the typed meaning of those fixed sections and `contracts_by_paper_type[note_plan.paper_type].recommended_subsections` to draft `note_plan.section_plan`
- the note plan must include the analysis coverage fields from the writing contract: `central_claims`, `claim_boundaries`, `negative_or_limiting_results`, `mechanism_result_map`, `comparative_positioning`, `reuse_takeaways`, and `followup_questions`
- each `central_claims` item must state the claim, source-grounded supporting evidence, what the evidence actually proves, and what it does not prove
- `mechanism_result_map` must connect paper-specific mechanisms, design choices, protocols, constructs, or data decisions to the exact result pattern or diagnostic evidence they explain
- `comparative_positioning` must explain how the paper differs from strong baselines, prior routes, human/clinical references, or obvious alternatives, and why that difference changes interpretation
- `followup_questions` must be concrete replication, engineering, research, or validity checks that a reader could reuse later
- pass that JSON file to `scripts/lint_note.py --plan-file ...` when linting the final note; if omitted, lint looks for sibling `<note>.plan.json`
- pass the same JSON plan to `scripts/lint_grounding.py` before using it for final drafting; broad references such as `synthesis_bundle.evidence.method_evidence` are invalid
- interactive sessions may additionally show a compact `<note_plan>...</note_plan>` block as display-only context, but it does not replace the JSON file
- do not require or expose a long free-form `<thinking>` block
- for technical papers, prefer replication-grade explanation over high-level summary
- if formulas, objectives, or complexity expressions are central, include the key ones in the final note
- render math as `$...$` or `$$...$$`, not as inline code or fenced code blocks
- before final save, explicitly self-review whether the note contains enough technical detail, key numbers, and any necessary formulas
- during `final_quality_review`, check the full note against seven questions: whether the central evidence chain is complete, whether key settings and numbers are present, whether mechanisms or protocols are mapped to the result pattern they explain, whether the paper is positioned against strong baselines or alternative routes, whether Discussion/Limitations conclusions are explained mechanistically, whether proven claims are separated from unproven claims, and whether the research, engineering, replication, or validity takeaways are specific enough to reuse
- central quantitative comparisons with three or more systems, settings, tasks, datasets, metrics, or ablation rows should normally be written as compact Markdown tables, followed by interpretation; do not leave the main result table as a loose bullet list when a table would be clearer
- short papers still need a complete deep note: use the saved space to explain protocol details, ablations, limitations, and deployment or replication implications rather than compressing the note into a terse summary
- after `final_quality_review` passes, reread the full note once more for readability; do not stop at formal compliance only
- in `final_readability_review`, ordinary English phrase leftovers should usually be rewritten into natural Chinese, while stable proper nouns may remain in English
- do not use `final_readability_review` to invent new facts, empty filler text, or shallower but safer wording just to satisfy lint

The topic references above can improve difficult runs, but the normal execution path should not depend on reading all of them.

## Scripts

Use these bundled scripts rather than rebuilding the workflow from scratch:
- `scripts/check_environment.py`
- `scripts/create_input_record.py`
- `scripts/locate_zotero_attachment.py`
- `scripts/resolve_paper.py`
- `scripts/run_pipeline.py`
- `scripts/collect_metadata.py`
- `scripts/fetch_pdf.py`
- `scripts/extract_source_text.py`
- `scripts/extract_evidence.py`
- `scripts/extract_pdf_assets.py`
- `scripts/plan_figures.py`
- `scripts/plan_figure_table_decisions.py`
- `scripts/build_synthesis_bundle.py`
- `scripts/lint_grounding.py`
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
- If the PDF is unavailable after all supported acquisition paths have been tried, stop and report what input is needed; do not produce a degraded, provisional, or abstract-only note as the finished output. Supported acquisition paths include local PDF, Zotero attachment, metadata `pdf_url`, direct PDF URL, arXiv/open-access sources, publisher PDF if accessible, DOI enrichment, and any other current fetch path implemented by the workflow.
- Placeholder-first figure planning is required; image extraction is optional and must never reduce textual coverage.
