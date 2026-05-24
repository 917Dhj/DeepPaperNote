# Workflow

This skill is a single-paper production pipeline.

The pipeline below describes the reusable core workflow plus the model-side handoff expected by any platform adapter.

When the current environment exposes local bibliography tooling, run a local-library-first preflight before the deterministic pipeline:
- search the local Zotero library by title, DOI, or arXiv id
- if there is a confident local hit, materialize a JSON input record from that trusted metadata
- inspect child attachments and prefer a local Zotero attachment path if one is available
- if the integration does not expose the local path, use the attachment key and filename to locate it in common Zotero `storage/` roots
- only fall back to title-based web resolution when the local library does not resolve the paper

For convenience, MVP also includes a runner script that executes the deterministic stages sequentially:
- `scripts/run_pipeline.py`

## Global Stage Discipline

For a normal single-paper note request, the pipeline below is a required execution contract.

- Required stages must not be silently skipped.
- Stage slowness is not a valid reason to bypass the stage.
- Partial artifacts must not be reported as final completion.
- If the workflow stops early, the report must name the current stage and the downstream required stages that remain incomplete.
- If a required stage fails, only three actions are allowed:
  - retry the same stage
  - enter a fallback explicitly allowed by this skill
  - stop and report the blocked stage honestly
- Do not invent shortcuts that replace the declared workflow.

## Pipeline

1. `resolve_paper`
   Normalize the user input into one paper identity.
   Accepted inputs: title, DOI, URL, arXiv ID, local PDF path, Zotero item key.
   If the input is already a trusted JSON record from local-library resolution, prefer that over a fresh title search.
   Completion condition:
   - one canonical paper identity is selected
   - obvious title ambiguity is resolved rather than hand-waved
   Allowed on failure:
   - retry with stronger identifiers or ask for clarification if identity is genuinely ambiguous
   - do not continue as if a title-only guess were a confirmed paper

2. `collect_metadata`
   Build a canonical metadata record.
   Preferred fields:
   - title
   - authors
   - affiliations
   - year
   - venue
   - DOI
   - abstract
   - code URL
   - project URL
   - source URL
   Completion condition:
   - a canonical metadata record exists, even if some optional fields remain empty
   Allowed on failure:
   - continue only with an explicitly partial metadata record
   - do not pretend metadata collection happened if no canonical record was produced

3. `fetch_pdf`
   Acquire the best available PDF.
   Preferred order:
   - local PDF
   - Zotero attachment
   - metadata `pdf_url`
   - direct PDF URL supplied by the user
   - arXiv or open-access PDF
   - publisher PDF if accessible
   - DOI enrichment and other currently supported acquisition paths
   Completion condition:
   - a usable PDF is available for downstream extraction
   Allowed on failure:
   - stop and report which acquisition paths were tried and what input is needed
   - do not continue as a degraded, provisional, abstract-only, or full-text-substitute note when no usable PDF exists

4. `extract_source_text`
   Produce the canonical raw reading artifacts.
   Canonical outputs:
   - `*_raw_sections.jsonl`
   - `*_source_manifest.json`
   - optional derived `*_full_text.md`, generated from JSONL
   Completion condition:
   - all available PDF pages are extracted by default
   - any explicit truncation is marked in `source_manifest.coverage`
   - source sections and page records are available for grounding
   Allowed on failure:
   - retry extraction, ask for a better PDF/OCR/source material, or stop
   - do not replace this stage with "I read some of the PDF myself so it is probably fine"

5. `extract_evidence`
   Produce deterministic structural indexes and quality signals.
   This stage can keep heuristic fields for diagnostics and legacy tooling, but top-N evidence buckets, `candidate_chunks`, and truncated `section_texts` are not the model-facing writing substrate.
   Completion condition:
   - structural indexes, reference candidates, coverage signals, and extraction-quality metadata exist

6. `extract_pdf_assets`
   Export page-level PDF image assets and page metadata.
   This stage should be deterministic:
   - prefer object-level image extraction from the PDF
   - record page number, image index, dimensions, and extraction method
   - use OCR only as page-text fallback, not as semantic figure matching
   Completion condition:
   - page/image asset metadata is produced, or the failure is explicitly recorded
   Allowed on failure:
   - continue with placeholder-first figure handling only if the failure is surfaced honestly
   - do not silently skip this stage and then talk as if figure handling were complete

7. `plan_figures`
   Build a figure inventory and plan placeholders for all major figures/tables that matter to the note.
   Placeholder-first rule:
   - preserve the important figure/table structure even if images are missing
   - only replace a placeholder when a real extracted image matches it with enough confidence
   - keep the original paper numbering such as `Fig. 2` or `Table 1`
   Completion condition:
   - major figures/tables have a placeholder-or-replacement decision
   Allowed on failure:
   - keep placeholders and explain the limitation
   - do not skip this stage just because image matching is slow or imperfect

8. `plan_figure_table_decisions`
   Build a decision row for every detected figure/table caption.
   Each item should have one explicit state: `insert`, `placeholder`, `low_priority`, `visual_defect`, or `skip` with reason.
   Planned usable figure/table crops with real image paths should be marked `insert`; this is still a final-save obligation, not a pipeline-time vault write.
   Completion condition:
   - every major detected figure/table has a recorded decision or skip reason

9. `build_synthesis_bundle`
   Assemble a model-facing manifest bundle from metadata, source manifest, coverage, references, figure/table manifest, figure plan, and PDF assets.
   This is the main handoff point from scripts to the language model.
   The model must read raw source records through `source_manifest.raw_sections_path`; the bundle itself must not expose old top-N `evidence`, `candidate_chunks`, or truncated `section_texts` as the primary writing input.
   The model must inspect `coverage` before treating source evidence as complete; truncated source text means the run is partial unless the user explicitly accepts partial reading.
   Completion condition:
   - the synthesis bundle exists and is the actual model handoff input
   Allowed on failure:
   - stop and report bundle construction as the blocking stage
   - do not replace the bundle with ad hoc memory of prior stages

10. model note planning
   Before drafting the final note, create an explicit short note-planning artifact:
   - infer the paper type
   - decide which sections deserve the most weight
   - decide which sections need `###` subheadings
   - select the most important numbers, comparisons, and figure/table placeholders
   - identify central claims, supporting source evidence, claim boundaries, limiting results, and reusable takeaways
   - add paper-specific subsections when the evidence supports them
   Canonical artifact:
   - a short JSON planning file such as `<note>.plan.json` or a run-scoped `*_note_plan.json`
   - pass that file to `scripts/lint_note.py --plan-file ...` when linting the final note
   - pass that file to `scripts/lint_grounding.py --note-plan ... --source-manifest ... --bundle-json ... --figure-decisions ...` before drafting from it
   - in interactive contexts, you may additionally show a compact `<note_plan>...</note_plan>` block as display-only context, but it does not replace the JSON file
   Do not rely only on an implicit hidden-planning step.
   Completion condition:
   - an explicit `note_plan` JSON artifact exists
   Allowed on failure:
   - revise planning until a short inspectable plan file exists
   - do not jump straight to prose and claim planning was basically done

11. `lint_grounding`
   Validate that the note plan is grounded in the canonical source manifest.
   Completion condition:
   - every substantive planned section cites either a valid `section_id` or a valid page range
   - every substantive planned section has a paper-specific `focus`/reading goal, not only a valid anchor
   - usable figure/table candidates with real image paths are not left as vague placeholders or low-priority placeholders
   - old broad bundle references such as `synthesis_bundle.evidence.method_evidence` are rejected
   - truncated source text blocks full-read drafting unless partial reading was explicitly accepted

12. model synthesis
   The language model reads the synthesis bundle and writes the actual note.
   It should do all understanding-heavy work:
   - choose emphasis
   - separate research problem from task definition
   - reconstruct method flow
   - pick the most meaningful results
   - explain what the evidence proves and does not prove
   - identify limitations and what the paper does not prove
   Completion condition:
   - a complete note draft exists, not just scattered sections or a partial summary
   Allowed on failure:
   - stop and report that drafting is incomplete
   - do not collapse a partial draft into "the note is finished"

13. `lint_note`
   Check structure, heading levels, missing sections, weak analysis, and mixed-language prose.
   If the refined note still contains half-English half-Chinese lines, fail closed before vault write.
   Completion condition:
   - lint has actually run and produced a result
   Allowed on failure:
   - revise and rerun lint
   - do not say the note is already validated if lint never ran

14. `final_quality_review`
   After the first successful script lint pass, reread the full note once more as an analytical quality pass against the source artifacts and note plan.
   This stage exists because script lint only enforces the floor and cannot judge whether the evidence chain, mechanism-to-result explanation, comparative positioning, claim boundaries, Discussion/Limitations interpretation, and reusable takeaways are deep enough.
   Required focus:
   - central claims are backed by raw sections or page ranges
   - key experimental settings, protocol details, and numbers are present when the paper depends on them
   - mechanisms, protocols, constructs, data decisions, or study design choices are mapped to the result pattern they explain
   - strong baselines, prior routes, human/clinical references, or obvious alternatives are used to interpret what the paper changes
   - proven claims are separated from unproven or unvalidated claims
   - negative, weak, missing, or limiting results are discussed when they constrain the conclusion
   - takeaways and follow-up questions are paper-specific enough to reuse in research, engineering, replication, or validity work
   Completion condition:
   - the full note has been reread after lint for analytical depth
   - any depth-driven edits are complete
   - if edits were made, the note is marked for a lint rerun before save
   Allowed on failure:
   - return to the source artifacts, revise the note, and rerun lint
   - do not treat formal lint success as permission to save a shallow note

15. `final_readability_review`
   After `final_quality_review` passes, reread the full note once more as a language-and-expression quality pass.
   This stage exists because script lint only enforces the floor and cannot judge every awkward phrase or stiff translation.
   Required focus:
   - smooth unnatural Chinese prose
   - remove stiff translations
   - rewrite ordinary English phrase leftovers into natural Chinese
   - keep stable proper nouns only when retaining English is genuinely more natural
   Completion condition:
   - the full note has been reread after lint
   - any readability-driven edits are complete
   - if edits were made, the note is marked for a lint rerun before save
   Allowed on failure:
   - continue rereading or revising until the readability review is complete
   - do not treat lint already passed as permission to skip this stage
   - do not invent new facts or change core numbers and conclusions under the name of polish

16. `write_obsidian_note`
   Save the final Markdown into the target vault.
   First decide the save mode explicitly:
    - if no Obsidian vault is configured, workspace mode is allowed
    - if an Obsidian vault is configured, vault mode is required
    - do not reinterpret "vault configured but not currently writable" as a workspace-fallback case
    Resolve a domain folder before writing:
    - prefer an existing first-level domain folder when there is a reasonable match
    - use `references/domain_rules.yaml` for application-first domain routing, with fallback method domains only when no application domain fits
    - keep existing-folder reuse conservative; method-only evidence is not enough to force reuse of an unrelated application folder
    - create a new domain only when no existing domain fits well
    - do not save directly into the bare papers root
   Complete the figure decision before this step:
    - replace usable matched placeholders with real images
    - keep lower-confidence, missing, contaminated, or blocked items as placeholders
    - pass the figure decision table to `write_obsidian_note.py --figure-decisions ...` so `insert` rows are copied into the paper-local `images/` folder and must be referenced by the final Markdown
    - do not split text writing and figure handling into two separate user turns by default
    If the configured vault or its paper-local `images/` directory cannot currently be written:
    - immediately ask the user for permission escalation
    - do not silently change the output target to the workspace
    - do not silently skip `images/` directory creation
    If the user refuses permission escalation:
    - stop the formal save flow and report that the Obsidian write did not complete
    - do not save to the workspace unless the user is asked again and explicitly approves that fallback
    Default vault layout:
    - one folder per paper
    - the note Markdown inside that folder
    - an `images/` subfolder for materialized figure assets, created even when it stays empty
    Do not claim the note is already saved to Obsidian if the vault write or `images/` directory creation never actually happened.
    Completion condition:
    - the note is actually written to the chosen target, and required paper-local layout is materialized
    Allowed on failure:
    - report the write step as incomplete
    - do not present ready-to-write or temporary-file-exists as a successful save

## Final Writing Rule

The structured artifacts are necessary, but they are not the final goal.

For the best note quality:
- scripts should gather and structure evidence
- the model should read the synthesis bundle plus canonical raw source records and write the final note in its own words
- do not delegate paper understanding to keyword scripts if the model can infer it from the bundle

Use [final-writing.md](final-writing.md) as the last-mile writing guide.
Use [evidence-first.md](evidence-first.md) and [deep-analysis.md](deep-analysis.md) for the planning and deep-reading rules that should shape the final note.

## Required Contracts

### `metadata.json`

Required keys:
- `title`
- `paper_id`
- `source_type`
- `source_url`
- `year`

Optional keys:
- `authors`
- `affiliations`
- `venue`
- `doi`
- `abstract`
- `code_url`
- `project_url`
- `zotero_key`
- `arxiv_id`
- `translated_title`
- `metadata_sources`

### `evidence_pack.json`

Legacy/diagnostic evidence extraction may still produce heuristic buckets, but the normal model-facing path should not draft from top-N evidence, `candidate_chunks`, or truncated `section_texts`.

### `source_manifest.json`

Suggested keys:
- `raw_sections_path`
- `full_text_md_path`
- `pdf`
- `coverage`
- `sections`
- `pages`
- `captions`
- `math_index`
- `appendix_index`
- `language_hint`
- `text_hash_sha256`

### `figure_plan.json`

Suggested keys per item:
- `id`
- `caption`
- `kind`
- `section`
- `reason`
- `priority`
- `anchor_text`
- `insert_mode`

See `scripts/contracts.py` for the corresponding scaffolded JSON contract definitions.

### `synthesis_bundle.json`

Suggested keys:
- `metadata`
- `coverage`
- `source_manifest`
- `source_index`
- `references`
- `figure_plan`
- `figure_table_manifest`
- `pdf_assets`
- `writing_contract`

`coverage` should include source coverage, PDF/asset coverage, extraction failures, and truncation warnings. It should not hide source truncation behind a normal-looking full-read bundle.

`references.candidates` contains model-facing candidates extracted from the paper's references section. Each candidate may include a confirmed `wikilink` when an existing vault note matched by basename or alias; otherwise use `display_text` as the plain-text fallback.

### `note_plan`

The canonical `note_plan` artifact is a short JSON file saved outside the final note body, such as `<note>.plan.json` or a run-scoped `*_note_plan.json`.
When linting, pass it with `scripts/lint_note.py --plan-file ...`; if no explicit path is given, lint looks for a sibling `<note>.plan.json`.
In interactive contexts, a compact `<note_plan>...</note_plan>` block may additionally be shown as display-only context, but it does not replace the JSON file.

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

Choose `paper_type` from `writing_contract.paper_type_selection.allowed_paper_types`; the script's suggested paper type is a hint only, not the authority. Use `paper_type_rationale` to explain the model's selection.
Each substantive `section_plan` item should include `evidence_sources` using valid `section_id` values from `source_manifest.sections` or valid page ranges within the PDF.
Each `central_claims` item should include `claim`, `supporting_evidence`, `what_it_actually_proves`, and `what_it_does_not_prove`.
`mechanism_result_map`, `comparative_positioning`, and `followup_questions` should be concise paper-specific lists that later force the final note to explain why results happened, what the comparison really means, and what the reader should test next.

## Failure Policy

Do not silently downgrade.

If the PDF or evidence is insufficient:
- report which stage failed
- explain why a full deep note is not trustworthy
- stop or ask for the better PDF, OCR, or source material needed to continue
- do not produce a degraded, provisional, or abstract-only note as the finished output

## Portability Rule

Keep the core workflow portable:
- the data contracts should remain useful outside any one agent runtime
- the scripts should not depend on platform-specific message formatting
- platform-specific behavior belongs in the adapter layer
