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
   Acquire the best available PDF or equivalent full text.
   Preferred order:
   - local PDF
   - Zotero attachment
   - arXiv or open-access PDF
   - publisher PDF if accessible
   Completion condition:
   - a usable PDF or trustworthy full-text substitute is available for downstream extraction
   Allowed on failure:
   - stop or produce a clearly labeled degraded path
   - do not continue as if this were a full deep read when only thin metadata exists

4. `extract_evidence`
   Produce an evidence pack rather than a finished note.
   This stage should favor broad collection over early judgment.
   Evidence targets:
   - section texts
   - candidate chunks per section
   - data/material mentions
   - metrics and numeric claims
   - figure and table captions
   - enough context for the model to decide what is truly central
   Completion condition:
   - an evidence pack exists with section-level or candidate-level evidence for the paper
   Allowed on failure:
   - retry extraction or clearly mark evidence quality as degraded
   - do not replace this stage with "I read some of the PDF myself so it is probably fine"

5. `extract_pdf_assets`
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

6. `plan_figures`
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

7. `build_synthesis_bundle`
   Assemble a model-facing bundle from metadata, evidence, section previews, figure plan, and PDF assets.
   This is the main handoff point from scripts to the language model.
   Completion condition:
   - the synthesis bundle exists and is the actual model handoff input
   Allowed on failure:
   - stop and report bundle construction as the blocking stage
   - do not replace the bundle with ad hoc memory of prior stages

8. model note planning
   Before drafting the final note, create an explicit short note-planning artifact:
   - infer the paper type
   - decide which sections deserve the most weight
   - decide which sections need `###` subheadings
   - select the most important numbers, comparisons, and figure/table placeholders
   - add paper-specific subsections when the evidence supports them
   Recommended form:
   - a compact `<note_plan>...</note_plan>` block
   - or a temporary planning file saved before the final note
   Do not rely only on an implicit hidden-planning step.
   Completion condition:
   - an explicit `note_plan` artifact exists
   Allowed on failure:
   - revise planning until a short inspectable plan exists
   - do not jump straight to prose and claim planning was basically done

9. model synthesis
   The language model reads the synthesis bundle and writes the actual note.
   It should do all understanding-heavy work:
   - choose emphasis
   - separate research problem from task definition
   - reconstruct method flow
   - pick the most meaningful results
   - identify limitations and what the paper does not prove
   Completion condition:
   - a complete note draft exists, not just scattered sections or a partial summary
   Allowed on failure:
   - stop and report that drafting is incomplete
   - do not collapse a partial draft into "the note is finished"

10. `lint_note`
   Check structure, heading levels, missing sections, weak analysis, and mixed-language prose.
   If the refined note still contains half-English half-Chinese lines, fail closed before vault write.
   Completion condition:
   - lint has actually run and produced a result
   Allowed on failure:
   - revise and rerun lint
   - do not say the note is already validated if lint never ran

11. `final_readability_review`
   After the first successful script lint pass, reread the full note once more as a language-and-expression quality pass.
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

12. `write_obsidian_note`
   Save the final Markdown into the target vault.
   First decide the save mode explicitly:
    - if no Obsidian vault is configured, workspace mode is allowed
    - if an Obsidian vault is configured, vault mode is required
    - do not reinterpret "vault configured but not currently writable" as a workspace-fallback case
    Resolve a domain folder before writing:
    - prefer an existing first-level domain folder when there is a reasonable match
    - create a new domain only when no existing domain fits well
    - do not save directly into the bare papers root
    Complete the figure decision before this step:
    - replace high-confidence placeholders with real images
    - keep lower-confidence items as placeholders
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
- the model should read the synthesis bundle and write the final note in its own words
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

Suggested keys:
- `problem_evidence`
- `task_evidence`
- `data_evidence`
- `method_evidence`
- `results_evidence`
- `limitations_evidence`
- `section_texts`
- `candidate_chunks`
- `figure_captions`
- `table_captions`
- `sections`
- `evidence_quality`
- `extraction_failures`
- `quotes`

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
- `evidence`
- `section_previews`
- `figure_plan`
- `pdf_assets`
- `summary`
- `writing_contract`

### `note_plan`

Suggested keys:
- `paper_type`
- `dominant_domain`
- `must_cover`
- `key_numbers`
- `real_comparisons`
- `section_plan`

## Failure Policy

Do not silently downgrade.

If the PDF or evidence is insufficient:
- report which stage failed
- explain why a full deep note is not trustworthy
- optionally produce a clearly labeled degraded note

## Portability Rule

Keep the core workflow portable:
- the data contracts should remain useful outside any one agent runtime
- the scripts should not depend on platform-specific message formatting
- platform-specific behavior belongs in the adapter layer
