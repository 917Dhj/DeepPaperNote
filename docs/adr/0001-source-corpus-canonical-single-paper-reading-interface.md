# Source Corpus Is The Canonical Single-Paper Reading Interface

Status: accepted

DeepPaperNote already treats `source_manifest.json` and `raw_sections.jsonl` as the canonical reading material for ordinary PDFs, but some downstream stages still rederive text structure by reopening the PDF. We will make Source Corpus the single-paper reading interface: an artifact/schema-first contract made of `source_manifest.json`, `raw_sections.jsonl`, and a small loader/validator.

Source Corpus owns text-derived structure: sections, pages, coverage and truncation state, captions, appendix index, math index, language hint, text hash, and `raw_sections_path`. It does not own PDF acquisition, metadata merging, image or crop quality decisions, semantic note planning, final note prose, or Obsidian saving.

The seam sits after PDF acquisition and before evidence extraction, figure/table decisions, synthesis bundle assembly, and grounding lint. Downstream text consumers must derive full text, section maps, captions, appendix views, and diagnostic views from Source Corpus rather than reopening the PDF. `candidate_chunks` and `section_texts` may remain temporarily as diagnostic derived views, but they are not canonical reading material and must not become model-facing writing inputs.

The migration should preserve the public workflow shape: existing run artifact names, stage order, `source_manifest.json`, and `raw_sections.jsonl` remain the external contract. The first implementation pass should converge consumers onto Source Corpus without changing image extraction, final writing, note-plan semantic decisions, or Obsidian save behavior.

Success means the pipeline still emits the same core artifacts, weak or inconsistent corpus input fails closed, truncation still blocks full-read claims unless partial reading is accepted, grounding lint behavior does not weaken, every source caption still reaches figure/table decisions, legacy evidence fields stay out of the model-facing bundle, and the relevant focused tests plus the full pytest suite pass.
