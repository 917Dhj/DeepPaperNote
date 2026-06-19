# Context Glossary

## Source Corpus

A single-paper reading interface made of `source_manifest.json`, `raw_sections.jsonl`, and a small loader/validator. It is the canonical source for text-derived paper structure: sections, pages, coverage and truncation state, captions, appendix index, math index, language hint, text hash, and the `raw_sections_path`.

It does not own PDF acquisition, metadata merging, image or crop quality decisions, semantic note planning, final note prose, or Obsidian saving.

## Source Corpus Boundary

The point in a single-paper run where an acquired PDF becomes the canonical text reading interface. Downstream stages consume this interface for text structure instead of reopening the PDF to rederive full text, sections, captions, or appendix structure.

## Text-Derived Structure

Paper structure derived from extracted text rather than image crops or model interpretation. In this project it includes section records, page records, coverage and truncation state, captions, appendix index, math index, language hint, text hash, and the raw sections path. These belong to the Source Corpus.

## Diagnostic Derived View

A non-authoritative view derived from the Source Corpus to help diagnostics or legacy compatibility. `candidate_chunks` and `section_texts` may exist in this role, but they are not canonical reading material and must not become model-facing writing inputs.

## Model-Facing Writing Input

The structured material the model is allowed to use as the authoritative basis for note planning and final drafting. For ordinary PDFs, this is the synthesis bundle plus the Source Corpus, not diagnostic derived views such as `candidate_chunks` or `section_texts`.

## Source Corpus Invariants

Constraints that every Source Corpus implementation must preserve: one corpus per single-paper run; source manifest plus raw sections are authoritative for ordinary PDF text reading; missing raw files, empty source text, inconsistent manifest/raw data, or hash mismatches fail closed; truncation is explicit and blocks full-read claims unless partial reading is accepted; section IDs, page ranges, and caption locations stay stable for grounding and figure decisions; downstream text consumers do not reopen the PDF to rederive text structure.

## Source Corpus Migration Boundary

The first migration should converge text consumers onto the Source Corpus without changing the public workflow shape. It preserves existing run artifact names and stage order, keeps `source_manifest.json` and `raw_sections.jsonl` as the external contract, avoids a new public pseudo-command, leaves image extraction, Obsidian saving, final prose, and note-plan semantic decisions outside the change, and may keep `candidate_chunks` and `section_texts` only as diagnostic derived views.
