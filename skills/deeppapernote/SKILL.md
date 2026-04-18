---
description: Generate a high-quality deep-reading note for a single paper and write it into an Obsidian-style vault. Use when the user gives a paper title, DOI, URL, arXiv ID, Zotero item, or local PDF and wants a polished Markdown note with strong structure, evidence-based analysis, and figure placeholders.
---

# DeepPaperNote

This Claude plugin wrapper exposes the canonical DeepPaperNote skill that lives at the repository root.

Before doing the task:
- read [../../SKILL.md](../../SKILL.md) and follow it as the canonical workflow and policy source
- use the same bundled `scripts/`, `references/`, and `assets/` directories from the repository root
- do not invent a separate Claude-only workflow here

The repository-root `SKILL.md` remains the source of truth for:
- scope
- workflow stages
- output rules
- fail-closed behavior
- figure and table placeholder policy
- Obsidian save semantics
