---
name: paper-glossary
description: Use when building reusable Obsidian glossary notes from an existing paper source manifest, optionally with a raw-sections override, especially when a reader needs a reviewed shortlist before glossary notes and article links are changed.
---

# Paper Glossary

Build shared glossary notes from `*_source_manifest.json`. `--source-manifest` is always required; `--raw-sections` only overrides its `raw_sections_path` with an explicit `*_raw_sections.jsonl`. This skill never runs or modifies a paper-reading workflow; the manifest and raw-sections file are its only paper-content boundary. See `references/file-contract.md` for JSON and CLI contracts.

## Preview And Wait (Default)

1. **Show saved configuration** on first use per person/device. If absent, ask for a term directory inside an Obsidian vault and configure it; reuse valid configuration later. **Setup may create `~/.paper-glossary/config.json`**.
2. **Require an explicit article Markdown path** when article links are requested. Validate it and the configured term directory are in the **same Obsidian vault**; never infer an article path.
3. **Run deterministic proposal** from the effective body.
4. **Perform exactly one grounded host semantic review**, bounded by `shortlist_limit`. It may **only drop or reorder candidates** and must preserve each retained proposal candidate's **exact `term` string**.
5. **Record the reviewed shortlist** with `plan_glossary.py --review-proposal PROPOSAL --reviewed-terms NAMES`; this validates the saved proposal against the current paper source and preserves each full candidate, ordered `surface_forms`, and provenance.
   If review produces an **empty reviewed shortlist**, report `no_candidates` and stop without presenting a selector.
6. **Present every retained term** from that reviewed artifact as a numbered Markdown list. This is the terminal, Codex, and Claude Code interaction. Show the resolved term directory, the article Markdown path (or that none was requested), and that selection authorizes glossary writes/enrichment plus first-safe-occurrence article links when an article was supplied.
7. State: **No glossary notes or article Markdown have been written before selection.** **End the response and wait.** Do not triage, inventory, generate, link, or lint during preview.

A broad request, manifest, raw sections path, or article path is not selection approval. A host-native selector is allowed only when it displays the complete same list in one interaction.

## After Selection

**Accept only numbers**, exact term names, or `全部写入` from the immediately preceding numbered list. Resolve them to the exact displayed `term` strings before invoking a script; `全部写入` applies only to that list. Invalid selections receive the valid range and another wait. Triage requires both `--reviewed-shortlist REVIEW` and the resolved exact names in `--terms`; never use `--terms` alone or add alias syntax.

Pass the current `--source-manifest`, optional `--raw-sections`, and saved `--reviewed-shortlist` to inventory, writer, and linker. Inventory consumes the saved `--triage` artifact as its selected-term input; writer and linker must also receive that same saved `--triage`. They require exact ordered `term` and `surface_forms` equality with this independent authorization before any glossary or article write.

1. **Triage** the selection; its selection identity binds each exact selected name and ordered paper-grounded forms.
2. Run library **inventory** from that triage artifact; it recomputes the complete proposal/review/selection provenance chain and fails closed on mismatched paper, source, shortlist, or forms.
3. Then **generate one action-aware batch**.
4. **Run one writer invocation** against the **configured glossary directory**; it revalidates the same provenance chain and requires its ordered inventory results to match the authorized triage exactly, then performs **whole-batch preflight** followed by the **create/enrich/reuse commit**. The writer resolves device-local configuration (or an explicit `--config-path` for that device) and does not accept a standalone write destination. With `--article`, its backlink is **derived from the resolved article Markdown stem**. Without an article, the glossary-only backlink comes from the **validated manifest `paper_id`**. The successful artifact preserves `triage_sha256`, provenance, article context, ordered mappings, and their deterministic `mappings_sha256`; the mapping digest binds the triage identity.
5. **Link each successful writer result** at its first safe occurrence **only if an article Markdown was supplied/requested**. The linker authenticates the writer provenance, context, digest, note paths, stems, and forms against the same current source/review, and rejects an artifact with **no bound article path**. **For a glossary-only request, skip `link_glossary_terms.py`**.
6. **Lint writer-returned changed glossary note files** whose **`action` is `created`, `enriched`, or `updated`** in **one `lint_glossary.py` invocation with repeated `--input PATH`** arguments. **Do not pass article Markdown to `lint_glossary.py`**.
7. **Report observable wall-clock timing** and statuses. **Time host-only phases separately**. **Each CLI emits top-level `elapsed_ms`** for its own complete invocation. The **single writer invocation includes whole-batch preflight and commit**. **Do not report separate preflight and commit timings**.

`new` entries are created; `existing_thin` entries receive only missing structured fields and a missing occurrence; `existing_complete` entries may receive only a missing occurrence. **Do not overwrite** existing note content. See `references/file-contract.md` for `existing_thin`, entry operations, writer `forms`, and link statuses.

## Grounding

- `anchor_only`: concise paper use plus a thin general explanation.
- `needs_explanation`: labeled background explanation with confidence and paper occurrence.
- Exclude reference-only occurrences as evidence. Keep paper facts in `occurrence` and outside knowledge labeled.
