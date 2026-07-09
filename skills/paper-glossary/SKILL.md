---
name: paper-glossary
description: Use when building reusable glossary or term-library notes for research papers from an existing paper source manifest, raw_sections_path, *_source_manifest.json, or *_raw_sections.jsonl, especially when a reader wants terms triaged, grounded in paper occurrences, and written as shared Obsidian notes.
---

# Paper Glossary

## Overview

Build a companion glossary for a paper without changing the paper-reading workflow. Use the shared source files already produced by another paper pipeline: `*_source_manifest.json` with `raw_sections_path`, or an explicit `*_raw_sections.jsonl`.

The scripts are deterministic support tools. They find candidate terms and paper anchors, but the model writes the actual concept explanations.

## Boundary

- Do not run or modify a paper-reading pipeline from this skill.
- Do not call any main paper workflow script from this skill.
- Treat `*_source_manifest.json` and `*_raw_sections.jsonl` as the only collaboration contract.
- Keep glossary outputs separate from the paper note unless the user explicitly asks to add links.
- Keep world-knowledge explanations thin, labeled, and confidence-rated; keep paper-specific facts in the occurrence zone.

## Workflow

1. Locate the source manifest for the paper. Prefer a file named like `paper_source_manifest.json`; it must contain `raw_sections_path`, or pass `--raw-sections` explicitly.
2. Propose candidate terms:

   ```bash
   python skills/paper-glossary/scripts/plan_glossary.py --propose --source-manifest paper_source_manifest.json --output glossary_candidates.json
   ```

3. Ask the reader which terms to keep, or accept a supplied list.
4. Triage selected terms against the paper:

   ```bash
   python skills/paper-glossary/scripts/plan_glossary.py --terms '["MoE", "knowledge distillation|KD"]' --source-manifest paper_source_manifest.json --output glossary_plan.json
   ```

5. Have the model write a glossary JSON with one entry per term. Follow `references/file-contract.md` for the schema.
6. Write central term notes:

   ```bash
   python skills/paper-glossary/scripts/write_glossary_terms.py --glossary glossary_entries.json --terms-dir ./术语 --paper-link PaperNoteStem --output glossary_write.json
   ```

7. Lint the glossary note folder before reporting completion:

   ```bash
   python skills/paper-glossary/scripts/lint_glossary.py --terms-dir ./术语
   ```

## Model Responsibilities

When writing `glossary_entries.json`, use the triage output this way:

- `routing: "anchor_only"`: explain how this paper uses the term and keep the general definition short.
- `routing: "needs_explanation"`: write a textbook-level explanation with a visible warning that it is background knowledge, not the paper's own claim.
- Always include `name`, `aliases`, `definition`, `confidence`, and `occurrence`.
- Use `confidence` as one of `高`, `中`, or `低`.

## Resources

- `scripts/plan_glossary.py`: propose terms and triage selected terms from raw sections.
- `scripts/write_glossary_terms.py`: create or update one shared Markdown note per term.
- `scripts/lint_glossary.py`: validate term-note structure.
- `references/file-contract.md`: input and output schemas.

## Common Mistakes

- Do not count references-section-only occurrences as evidence that the paper explains a term.
- Do not let an absent term look grounded; mark it as `needs_explanation`.
- Do not duplicate existing term notes when an alias already exists.
- Do not remove the warning, definition, confidence tier, or paper occurrence section from term notes.
