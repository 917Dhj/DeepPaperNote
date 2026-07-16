# Paper Glossary Optimization Design

Date: 2026-07-14

Status: approved for implementation

## Goals

- Keep `paper-glossary` independent from the DeepPaperNote workflow.
- Use only `*_source_manifest.json` and `*_raw_sections.jsonl` as the paper-content contract.
- Let each user configure one Obsidian term-library directory on first use per device.
- Present a high-quality, length-aware candidate list before any write.
- After selection, write or enrich term notes and add safe outbound links to the explicit article Markdown.
- Reduce model latency without making term notes too thin.

## Non-goals

- Do not modify `skills/deeppapernote/` or call its workflow.
- Do not change plugin manifests.
- Do not add a vector database or third-party dependency.
- Do not guess which Markdown article to modify.
- Do not replace or rewrite user-authored term-note content.

## Inputs and Boundaries

Term evidence comes only from a source manifest and its `raw_sections_path`, or from an explicit raw-sections JSONL file. The Markdown article path is a separate, explicit write target. It is never inferred from a PDF title, `full_text_md_path`, or a same-named file search.

If the user provides only a PDF, manifest, or raw-sections path, preview may run, but article linking must wait until the user supplies the Markdown note path.

## First-use Configuration

On the first write-capable run, ask the user to choose a term-library directory inside an Obsidian vault. Find the nearest ancestor containing `.obsidian` and reject a directory without one.

Store device-local configuration in `~/.paper-glossary/config.json`:

```json
{
  "vault_root": "F:\\我的笔记\\123",
  "terms_subdir": "book\\术语"
}
```

The config is not written into the plugin repository or Obsidian vault. Later runs reuse it without asking, and the preview still displays the resolved term-library path. Writer destination authority comes only from validated device config. `--config-path` selects a config file, not a direct destination. To use a different location, reset and configure the device again.

Before any write:

- verify that `vault_root/.obsidian` exists;
- resolve paths before checking containment;
- verify that the term directory remains inside the configured vault;
- verify that the target article Markdown is inside the same vault.

If any check fails, stop before changing files and request configuration again.

## Candidate Workflow

### Deterministic prefilter

Build a grounded candidate pool from prose, headings, emphasis, acronym expansions, named methods, models, datasets, tools, and important components. Exclude:

- fenced and inline code;
- URLs and existing links;
- references-only records or reference sections;
- environment-variable fragments and code-identifier fragments;
- example-only brands or entities without reusable conceptual value;
- case-only duplicates and known aliases.

Prefer longer and more specific forms before short forms. Keep evidence anchors and surface forms for every candidate.

### Length-aware limit

Measure effective body characters after excluded material is removed. The final shortlist limit is:

| Effective body length | Maximum candidates |
| --- | ---: |
| `< 10,000` | 10 |
| `10,000-29,999` | 18 |
| `30,000-59,999` | 25 |
| `>= 60,000` | 35 |

These are upper limits, not quotas. Never add noise to fill a tier. The deterministic pool may contain up to ten more items than the final limit so the semantic review has alternatives.

### Semantic review

Use one compact host-model review to rank the grounded pool, remove residual noise, and retain core concepts that the deterministic ranking would otherwise underrank. The review may only drop or reorder exact proposal candidates: every retained candidate preserves its exact `term` and ordered `surface_forms`. It may not merge aliases, author forms, or introduce a term without paper evidence in the pool.

Present the complete final shortlist as a numbered Markdown list. Also display:

- the resolved term-library directory;
- the article Markdown path, when available;
- a clear statement that selection will write term notes and add one safe article outlink per selected term.

Then stop and wait. A broad request or paper path alone is not write approval.

## Selection and Generation

Accept numbers, names, or `全部写入` only from the immediately preceding shortlist. Resolve control input to canonical names before invoking triage.

Classify selected terms as:

- `new`: no matching name or alias in the central library;
- `existing_complete`: an existing note has a definition, confidence, and at least two substantive explanatory fields;
- `existing_thin`: an existing note is missing required fields or has fewer than two substantive explanatory fields.

Use one batch generation step for all `new` entries and all missing fields in `existing_thin` entries:

- `anchor_only`: concise definition, paper usage/occurrence, confidence, and only necessary supplementary context;
- `needs_explanation`: definition, elaboration, intuition, distinction, occurrence, and confidence.

For every existing note, append the new paper occurrence when absent. For `existing_thin`, add only missing fields. Never remove, replace, reorder, or rephrase existing user content. `existing_complete` receives the occurrence only.

Validate the entire generated batch before writing any entry. One structured-output repair attempt is allowed. If the repaired payload is still invalid, stop without writing generated content.

## Article Outlinks

Selection authorizes both glossary writes and article linking because the preview states both effects in advance.

Use the actual `link_stem` returned by the glossary writer. In the explicit article Markdown, link the first safe prose occurrence:

```md
[[ReAct]]
[[ReAct|REACT]]
```

Skip matches inside:

- YAML frontmatter;
- headings;
- fenced or inline code;
- URLs, Markdown links, HTML, and existing wiki links;
- reference sections;
- a larger identifier or word.

Match longer terms before shorter ones. Preserve the original surface text through an alias link. Add at most one outlink per term. A repeated run must not add another link.

Record the article hash at preview. Recheck it immediately before link application. If it changed, stop article writing and report the conflict. Build the edited text in memory, write a temporary sibling file, and atomically replace the article only after validation. If no safe occurrence exists, keep the valid glossary result and report the missing outlink without forcing a fallback insertion.

## Performance

- Use at most one semantic-review phase before selection.
- Use one batch generation phase after selection; never call the model once per term.
- Generate content only for new entries and missing fields in thin entries.
- Lint only files changed by the current run; keep a separate full-library audit command.
- Report elapsed time for configuration, extraction, semantic review, generation, glossary write, article linking, and lint.
- Treat under-two-second local script work on the chapter-four regression fixture as an observed, environment-dependent target. Repeated benchmark runs report a median and range, or exact overruns. Overall model time is a visible target of roughly one to two minutes, not a platform-independent guarantee.

## Result and Failure Reporting

The final result reports separate counts and paths for:

- created;
- enriched;
- reused;
- occurrences appended;
- article outlinks added;
- selected terms without a safe outlink;
- failures.

Configuration errors, cross-vault paths, invalid selections, stale article hashes, and invalid generated payloads must fail before the corresponding write. A failed enrichment preserves the original note. A failed article link does not corrupt or delete a valid term note.

## Implementation Surface

Keep changes inside `skills/paper-glossary/`:

- update `SKILL.md` for first-use setup, hybrid preview, selection effects, and adaptive generation;
- add device-local config resolution under `scripts/`;
- improve `plan_glossary.py` prefiltering, alias normalization, evidence, and dynamic limits;
- extend `write_glossary_terms.py` with preflight validation and non-destructive thin-note enrichment;
- add a focused article-linking script with hash and atomic-write protection;
- update `references/file-contract.md` and `README.md`;
- add focused unit and integration tests.

## Verification

Tests must cover:

- first-use configuration, reuse, reset, deleted paths, non-vault paths, and cross-vault rejection;
- all four candidate-size tiers without quota filling;
- code, URL, references, environment-variable, example-entity, case, and alias filtering;
- preservation of core chapter concepts such as `Reflection`;
- concise and full entry schemas;
- new, complete, and thin existing-note behavior;
- preservation of frontmatter, custom sections, comments, and user text;
- idempotent occurrence enrichment;
- direct and alias outlinks, protected Markdown regions, longer-term priority, stale hashes, and idempotency;
- the complete preview, selection, write, link, and lint flow using repository fixtures.

Run the focused paper-glossary tests and the repository's normal full test suite. No commit or push occurs until implementation and verification are complete and the user explicitly approves it.

## Current Demo Cleanup

The earlier demo wrote notes to `F:\我的笔记\123\学习\hello_agent\术语`. Do not migrate those notes blindly. After implementation passes tests, rerun preview for the chapter-four article with the improved filter, let the user select from the corrected shortlist, merge approved content into the configured central library, add article outlinks, and only then remove assistant-created demo files after confirming they contain no later user edits.
