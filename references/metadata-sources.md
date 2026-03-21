# Metadata Sources

Use the strongest available source first, but backfill aggressively.

## Preferred Order

1. user-provided exact source
2. local Zotero metadata and attachments
3. DOI resolution and publisher metadata
4. Semantic Scholar
5. OpenAlex
6. arXiv metadata

## Required Fields to Attempt

- title
- authors
- affiliations
- year
- venue
- DOI
- source URL

## Optional Fields

- abstract
- code URL
- project URL
- citation counts
- arXiv ID
- Zotero key

## Rules

- If the paper is already in the local Zotero library, treat Zotero as the identity anchor before doing title-based web resolution.
- If Zotero resolves the paper but does not expose a local attachment path, still use the Zotero metadata to avoid title ambiguity.
- Do not let a weaker internet title match override a confident Zotero hit.
- Do not invent missing metadata.
- If a Chinese title is assistant-generated, mark it as a translation.
- Distinguish:
  - `not found`
  - `not provided by source`
  - `ambiguous`
