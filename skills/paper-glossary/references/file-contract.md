# Paper Glossary File Contract

## Boundary And Configuration

`--source-manifest` is always required as a JSON object or path. `--raw-sections` only overrides the manifest's `raw_sections_path`; it cannot replace the manifest. Together, `*_source_manifest.json` and the resolved `*_raw_sections.jsonl` are the complete shared-file collaboration boundary. `plan_glossary.py` reads records whose `record_type` is absent or `section`; `kind: references` is excluded from evidence. No DeepPaperNote import or workflow call is part of this contract.

`configure_glossary.py --terms-dir PATH` writes device-local `~/.paper-glossary/config.json`:

```json
{"vault_root":"/vault","terms_subdir":"Glossary"}
```

`vault_root` must be absolute; relative and Windows drive-relative values are invalid. Loading returns the resolved absolute vault root so write authority does not depend on the process working directory.

`--show` returns that configuration plus resolved `terms_dir`, or `{"workflow_state":"needs_configuration"}`. `--reset` returns `{"workflow_state":"reset"}`. `--validate-article PATH` requires an existing `.md` file in the configured vault and returns:

```json
{"terms_dir":"/vault/Glossary","article_path":"/vault/Papers/example.md","article_sha256":"sha256"}
```

## Proposal, Review, And Triage

`plan_glossary.py --propose` emits a deterministic candidate pool for one host semantic review. Each candidate contains ordered paper-grounded `surface_forms`. `provenance.source_sha256` binds the current `paper_id`, manifest, and source records; `provenance.proposal_sha256` also binds the exact candidate payload and summary. The host may **only drop or reorder candidates**, must preserve each retained candidate's **exact `term` string** and full object, and must display no more than `summary.shortlist_limit` terms before waiting for selection.

```json
{
  "status": "ok",
  "script": "plan_glossary.py",
  "mode": "propose",
  "workflow_state": "awaiting_semantic_review",
  "next_action": "record_reviewed_shortlist_then_present_and_wait",
  "paper_id": "paper-id",
  "candidates": [{"term": "MoE", "surface_forms": ["MoE", "ＭｏＥ"], "category": "acronym-or-model", "occurrences": 2, "section_id": "sec:method", "page_start": 3, "snippet": "..."}],
  "summary": {"effective_body_characters": 9000, "shortlist_limit": 10, "pool_candidates": 1},
  "provenance": {
    "paper_id": "paper-id",
    "source_sha256": "sha256",
    "candidates": [{"term": "MoE", "surface_forms": ["MoE", "ＭｏＥ"], "category": "acronym-or-model", "occurrences": 2, "section_id": "sec:method", "page_start": 3, "snippet": "..."}],
    "summary": {"effective_body_characters": 9000, "shortlist_limit": 10, "pool_candidates": 1},
    "proposal_sha256": "sha256"
  }
}
```

The dynamic `shortlist_limit` is 10 below 10,000 effective body characters, 18 below 30,000, 25 below 60,000, and 35 otherwise. The pool can contain up to ten review alternatives beyond that limit. With no proposal candidates, or when semantic review records an **empty reviewed shortlist**, the state is `no_candidates` and `next_action` is `"report_no_candidates"`; the host reports that terminal state without displaying an empty selector.

Record the semantic review before display:

```text
plan_glossary.py --review-proposal proposal.json --reviewed-terms '["MoE"]' --source-manifest paper_source_manifest.json --output reviewed.json
```

The reviewed artifact contains `mode: "review"`, `reviewed_shortlist` with the selected full candidate objects unchanged, `proposal_provenance`, and provenance that repeats the exact proposal paper/source/candidate/summary fields, adds the full ordered `reviewed_shortlist`, and binds them with `"review_sha256"`. Review recording rejects unknown or duplicate names, alias syntax, more than `shortlist_limit`, a changed source, and any proposal payload or identity that does not match the current source.

After the complete reviewed list is displayed, resolve shortlist numbers and `全部写入` to exact names outside the CLI. Triage requires the reviewed artifact; the old `--terms`-only path fails:

```text
plan_glossary.py --reviewed-shortlist reviewed.json --terms '["MoE"]' --source-manifest paper_source_manifest.json --output triage.json
```

Every selected name must exactly match `reviewed_shortlist`. Triage revalidates the review against the current source and proposal, copies candidate `surface_forms` unchanged, uses only those forms for occurrences and anchors, and returns proposal, review, and selection provenance. `selection_sha256` binds the review identity plus each selected exact `term` and ordered `surface_forms` list.

## Inventory And Entries

Pass triage to `inspect_glossary_library.py` with the current `--source-manifest`, optional `--raw-sections`, and saved `--reviewed-shortlist`:

```text
inspect_glossary_library.py --terms triage.json --terms-dir /vault/Glossary --source-manifest paper_source_manifest.json --raw-sections paper_raw_sections.jsonl --reviewed-shortlist reviewed.json --output inventory.json
```

The CLI recomputes the current deterministic proposal and validates the saved review before comparing the proposal, review, and selection digests from the triage artifact. This saved `--triage` is the independent authorization artifact passed unchanged to writer and linker. Both require exact ordered `term` and `surface_forms` equality with it. Inventory requires matching top-level/proposal/review paper and source fields and preserves that provenance plus each exact ordered `surface_forms` list. Its output includes the validated top-level `paper_id`. Missing, empty, non-string, whitespace-altered, duplicate, term-omitting, shortlist-mismatched, or identity-mismatched form data fails instead of being repaired. Every result contains `term`, `surface_forms`, `state`, `file`, `link_stem`, and `missing_fields`. State is `"new"`, `"existing_thin"`, or `"existing_complete"`.

The one generated glossary batch has an `entries` array. Every entry has `name`, `aliases`, `operation`, and `occurrence`; `operation` is one of `create`, `enrich`, or `reuse`.

```json
{
  "entries": [{
    "name": "MoE",
    "aliases": ["Mixture of Experts"],
    "operation": "enrich",
    "elaboration": "Only supplied when inventory marks it missing.",
    "occurrence": "Paper-specific evidence."
  }]
}
```

`create` requires a definition and valid confidence. `enrich` may add only inventory `missing_fields`. `reuse` cannot replace concept fields. Every operation requires an occurrence. The writer resolves the **configured glossary directory** from device-local configuration (or `--config-path`), requires it to remain a valid Obsidian-vault directory, and has no standalone destination override. It requires the inventory's full provenance, reruns the same chain validation against the ordered inventory result terms/forms, then rechecks current library state and preflights the complete batch before changing a note.

## Writer And Linker Results

The article-bound writer invocation is:

```text
write_glossary_terms.py --glossary entries.json --inventory inventory.json --config-path config.json --source-manifest paper_source_manifest.json --raw-sections paper_raw_sections.jsonl --reviewed-shortlist reviewed.json --triage triage.json --article /vault/Papers/example.md --output writer.json
```

For a glossary-only invocation, omit `--article`:

```text
write_glossary_terms.py --glossary entries.json --inventory inventory.json --config-path config.json --source-manifest paper_source_manifest.json --raw-sections paper_raw_sections.jsonl --reviewed-shortlist reviewed.json --triage triage.json --output writer.json
```

Both modes revalidate the current source and saved review before loading generated entries. With an article, `paper_link` is **derived from the resolved article Markdown stem** and `article_path` is its resolved absolute path. In glossary-only mode, `paper_link` is the wiki-link-safe **validated manifest `paper_id`** and `article_path` is empty. `write_glossary_terms.py` returns successful results with the actual note target and only the exact reviewed/inventory `forms`:

```json
{
  "status": "ok",
  "script": "write_glossary_terms.py",
  "paper_id": "paper-id",
  "triage_sha256": "sha256",
  "provenance": {
    "proposal": {
      "paper_id": "paper-id",
      "source_sha256": "sha256",
      "candidates": [{"term": "MoE", "surface_forms": ["MoE", "ＭｏＥ"]}],
      "summary": {"shortlist_limit": 10},
      "proposal_sha256": "sha256"
    },
    "review": {
      "paper_id": "paper-id",
      "source_sha256": "sha256",
      "candidates": [{"term": "MoE", "surface_forms": ["MoE", "ＭｏＥ"]}],
      "summary": {"shortlist_limit": 10},
      "proposal_sha256": "sha256",
      "reviewed_shortlist": [{"term": "MoE", "surface_forms": ["MoE", "ＭｏＥ"]}],
      "review_sha256": "sha256"
    },
    "selection_sha256": "sha256"
  },
  "context": {"paper_id": "paper-id", "paper_link": "example", "article_path": "/vault/Papers/example.md"},
  "mappings_sha256": "sha256",
  "results": [{
    "name": "MoE",
    "forms": ["MoE", "ＭｏＥ"],
    "file": "/vault/Glossary/MoE.md",
    "action": "enriched",
    "link_stem": "MoE",
    "fields_added": ["elaboration"],
    "occurrence_added": true
  }]
}
```

`action` is `created`, `enriched`, `updated`, or `unchanged`. Entry `aliases` may be written to note metadata and participate in logical collision checks, but they are never added to writer `forms`. Generated names and aliases are checked against the full library's NFKC/casefold alias index before any write; an existing form is allowed only for the same validated target. Grounded inventory forms need not be repeated in entry `aliases`. Existing notes are never replaced, only missing fields and an absent occurrence may be added. `triage_sha256` deterministically identifies the authorized triage's paper, provenance, and terms. `mappings_sha256` binds that triage identity, validated provenance, derived context, and exact ordered `name`, `forms`, `file`, and `link_stem` mappings.

Before filesystem-invalid-character cleanup, the writer translates Obsidian wikilink syntax characters `# ^ [ ] | : %` in generated filename stems to their fullwidth equivalents. When the allocated `link_stem` differs from the exact term, the note keeps that exact term as an alias and visible H1, so article links use forms such as `[[C＃|C#]]`. Inventory rejects a selected existing note whose filename still contains those unsafe ASCII characters and asks the user to replace its filename; it never changes user-owned note paths automatically.

Run the linker **only if an article Markdown was supplied/requested**:

```text
link_glossary_terms.py --input /vault/Papers/example.md --write-result writer.json --expected-sha256 sha256 --config-path config.json --source-manifest paper_source_manifest.json --raw-sections paper_raw_sections.jsonl --reviewed-shortlist reviewed.json --triage triage.json --output linker.json
```

The linker revalidates the successful writer provenance against the current source, saved review, and same saved triage; requires its mappings to equal the triage's exact authorized selection; verifies `triage_sha256`; recomputes `mappings_sha256`; and checks context, order, files, stems, and full-library form resolution before touching the article. It rejects a writer artifact with **no bound article path**. Supply the preview's `article_sha256` as `--expected-sha256`. **For a glossary-only request, skip `link_glossary_terms.py`**. When run, it returns the validated `article_path`, per-note `results`, and counts:

```json
{
  "status": "ok",
  "script": "link_glossary_terms.py",
  "article_path": "/vault/Papers/example.md",
  "results": [{"link_stem": "MoE", "status": "already_linked"}],
  "summary": {"linked": 0, "already_linked": 1, "not_found": 0}
}
```

Link statuses are `linked`, `already_linked`, or `not_found`. A stale article hash stops linking before article modification.

## Lint And Timing Boundaries

Lint only **writer-returned changed glossary note files** whose **`action` is `created`, `enriched`, or `updated`**, using **one `lint_glossary.py` invocation with repeated `--input PATH`** arguments. Explicit inputs are resolved and deduplicated, and may be combined with `--terms-dir` for an intentional full-library audit. **Do not pass article Markdown to `lint_glossary.py`**; it validates the term-note structure, not ordinary articles.

**Time host-only phases separately**. **Each CLI emits top-level `elapsed_ms`** as a non-negative integer for its own complete invocation:

```json
{
  "elapsed_ms": 12
}
```

The **single writer invocation includes whole-batch preflight and commit**. **Do not report separate preflight and commit timings**. Host semantic review and model generation remain separately timed host-only phases and are not fabricated by Python.
