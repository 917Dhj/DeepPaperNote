# Workflow

This skill is a single-paper production pipeline.

The pipeline below describes the reusable core workflow, not only the Codex wrapper.

When local Zotero is available, the Codex adapter should run a Zotero-first preflight before the deterministic pipeline:
- search the local Zotero library by title, DOI, or arXiv id
- if there is a confident local hit, materialize a JSON input record from that trusted metadata
- inspect child attachments and prefer a local Zotero attachment path if one is available
- if MCP does not expose the local path, use the attachment key and filename to locate it in common Zotero `storage/` roots
- only fall back to title-based web resolution when Zotero does not resolve the paper

For convenience, MVP also includes a runner script that executes the deterministic stages sequentially:
- `scripts/run_pipeline.py`

## Pipeline

1. `resolve_paper`
   Normalize the user input into one paper identity.
   Accepted inputs: title, DOI, URL, arXiv ID, local PDF path, Zotero item key.
   If the input is already a trusted JSON record from Zotero resolution, prefer that over a fresh title search.

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

3. `fetch_pdf`
   Acquire the best available PDF or equivalent full text.
   Preferred order:
   - local PDF
   - Zotero attachment
   - arXiv or open-access PDF
   - publisher PDF if accessible

4. `extract_evidence`
   Produce an evidence pack rather than a finished note.
   Evidence targets:
   - research problem
   - task definition
   - data or materials
   - method
   - training or analysis details
   - metrics
   - strongest results
   - limitations
   - figure and table captions

5. `extract_pdf_assets`
   Export page-level PDF image assets and page metadata.
   This stage should be deterministic:
   - prefer object-level image extraction from the PDF
   - record page number, image index, dimensions, and extraction method
   - use OCR only as page-text fallback, not as semantic figure matching

6. `plan_figures`
   Build a figure inventory and plan placeholders for all major figures/tables that matter to the note.
   Placeholder-first rule:
   - preserve the important figure/table structure even if images are missing
   - only replace a placeholder when a real extracted image matches it with enough confidence
   - keep the original paper numbering such as `Fig. 2` or `Table 1`

7. `build_synthesis_bundle`
   Assemble a model-facing bundle from metadata, evidence, section previews, figure plan, and PDF assets.
   This is the main handoff point from scripts to the language model.

8. Codex/GPT note planning
   Before drafting the final note, make a dynamic internal note plan:
   - infer the paper type
   - decide which sections deserve the most weight
   - decide which sections need `###` subheadings
   - select the most important numbers, comparisons, and figure/table placeholders
   - add paper-specific subsections when the evidence supports them

9. Codex/GPT synthesis
   The language model reads the synthesis bundle and writes the actual note.
   It should do all understanding-heavy work:
   - choose emphasis
   - separate research problem from task definition
   - reconstruct method flow
   - pick the most meaningful results
   - identify limitations and what the paper does not prove

10. `lint_note`
   Check structure, heading levels, missing sections, weak analysis, and mixed-language prose.
   If the refined note still contains half-English half-Chinese lines, fail closed before vault write.

11. `write_obsidian_note`
    Save the final Markdown into the target vault.
    Resolve a domain folder before writing:
    - prefer an existing first-level domain folder when there is a reasonable match
    - create a new domain only when no existing domain fits well
    - do not save directly into the bare papers root
    Complete the figure decision before this step:
    - replace high-confidence placeholders with real images
    - keep lower-confidence items as placeholders
    - do not split text writing and figure handling into two separate user turns by default
    Default vault layout:
    - one folder per paper
    - the note Markdown inside that folder
    - an `images/` subfolder for materialized figure assets, created even when it stays empty

## Final Writing Rule

The structured artifacts are necessary, but they are not the final goal.

For the best note quality:
- scripts should gather and structure evidence
- Codex should read the synthesis bundle and write the final note in its own words
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

## Failure Policy

Do not silently downgrade.

If the PDF or evidence is insufficient:
- report which stage failed
- explain why a full deep note is not trustworthy
- optionally produce a clearly labeled degraded note

## Portability Rule

Keep the core workflow portable:
- the data contracts should remain useful outside Codex
- the scripts should not depend on Codex-only message formatting
- platform-specific behavior belongs in the adapter layer
