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

## Paper Identity

The acquisition-layer answer to “which paper is this run about?” It is distinct from both source text and final note metadata. It owns the paper’s stable identifiers, title evidence, source provenance, identity confidence, identity verdict, and any repair history needed to decide whether acquisition may continue.

## Paper Manifestation

A concrete version or appearance of the same Paper Identity, such as an arXiv preprint, publisher version, Zotero attachment, or local PDF. Manifestations may differ in layout, pagination, publisher template, source URL, venue metadata, or minor title punctuation while still representing the same paper.

## Identity Equivalence

The acquisition-layer decision that two candidate records are manifestations of the same Paper Identity rather than competing identities. Evidence may include highly consistent titles, overlapping leading authors, highly similar abstracts or first paragraphs, cross-linked DOI/arXiv metadata, shared external work identifiers, or close PDF content structure despite layout differences.

## Source Manifestation

The Paper Manifestation actually read during a run, usually the user-supplied PDF, Zotero attachment, downloaded arXiv PDF, publisher PDF, or another confirmed full-text source. Source Manifestation is run-level evidence and may differ from the work-level canonical metadata.

## Work-Level Identity

The canonical Paper Identity shared by equivalent manifestations of the same scholarly work. It may retain both DOI and arXiv identifiers and should not be collapsed into the specific PDF used as the Source Manifestation.

## Note Identity Display

The work-level identity shown in the final note metadata and core information. It should prefer canonical work title and stable identifiers while still disclosing the Source Manifestation that was actually read.

## Evidence Location Binding

The rule that page numbers, figure/table locations, source sections, and grounding references bind to the Source Manifestation actually read during the run, not to a different manifestation that merely provides more canonical metadata.

## Strong Identity Anchor

A DOI, arXiv ID, Zotero key, DOI URL, arXiv URL, or equivalent stable identifier supplied by a trusted source such as the user input, Zotero, or an authoritative provider. Identity Repair may use a Strong Identity Anchor to repair title, venue, PDF URL, and source metadata, but must not silently replace the paper identity.

## Challengeable Identity Anchor

An identifier inferred from weaker evidence such as a local PDF first page, local filename, title-only search, or other heuristic extraction. Identity Repair may replace a Challengeable Identity Anchor when stronger contradictory evidence is found, but must record the reason.

## Identity Verdict

The acquisition-layer decision about whether a Paper Identity is safe to use. It must distinguish accepted, accepted-with-warnings, repairable, ambiguous, and failed identities; strong identifiers such as DOI or arXiv ID do not automatically make every title or metadata field safe.

## Accepted With Warnings

An Identity Verdict where Paper Identity is safe enough for downstream use after validation or repair, but non-blocking metadata uncertainty remains. It is for incomplete or imperfect metadata, not for cases where the run may be about the wrong paper.

## Warning-Scoped Note Impact

The rule that accepted-with-warnings identity uncertainty may affect final note metadata, source provenance, citation wording, or over-specific venue/year claims, but must not degrade or distract the analytical body of the note when the Paper Identity and Source Manifestation are safe.

## Identity Repair

The bounded acquisition-layer process that attempts to correct a repairable Paper Identity before downstream stages use it. It is not note rewriting, Source Corpus repair, or final note quality evaluation.

## Repair-Exhausted Fail Closed

The acquisition-layer rule that the pipeline may fail closed only after bounded Identity Repair has been attempted and still cannot produce an automatically safe Paper Identity. A repairable identity should enter repair before it is allowed to stop the pipeline.

## Identity Verification Boundary

The acquisition boundary where Paper Identity is checked before downstream use. DeepPaperNote uses an initial check after resolution and a definitive repair-and-verify step after metadata collection and before PDF fetch.

## Canonical Identity Artifact

The authoritative acquisition artifact consumed by downstream stages when a Paper Identity has been accepted after validation and any allowed repair. It is a narrow work-level identity plus selected source-manifestation contract, not a full metadata-provider dump. It does not overwrite the original resolve or metadata artifacts; those remain provenance evidence.

## Identity Repair Trace

The acquisition artifact that records attempted identity repairs, evidence used, rejected candidates, accepted corrections, and unresolved risks. It preserves why the Canonical Identity Artifact was accepted, repaired, or failed.

## Identity Failure Summary

A short user-facing acquisition failure explanation produced only after Identity Repair is exhausted. It tells the user what stronger evidence is needed without exposing raw provider payloads or asking the note writer to explain the failure.

## Identity Failure Class

The machine-readable category for an exhausted identity failure, such as ambiguous candidates, source PDF mismatch, unresolved metadata contradiction, provider unavailable, or insufficient evidence. It is consumed by runners, artifact auditors, and regression judges.

## Identity Evidence

A specific acquisition-layer observation used to validate or repair Paper Identity, such as provider title, DOI, arXiv ID, author list, abstract similarity, first-page text, PDF metadata, filename, Zotero metadata, or external work identifier. Identity Evidence supports the Canonical Identity Artifact but does not by itself become the canonical identity.

## Identity Evidence Trust Order

The domain priority for Identity Evidence: explicit user-supplied stable identifiers or source paths express run intent; Zotero metadata plus attachment is strong local evidence; DOI/arXiv authoritative metadata anchors work identity; OpenAlex, Semantic Scholar, and Crossref work linkage support equivalence and enrichment; PDF metadata, first-page text, and abstract text validate the Source Manifestation; filenames and title-only queries are weak evidence that may start repair but should not be accepted alone.

## Note Evaluation Rubric

A reusable evaluator-facing standard for judging final DeepPaperNote outputs after generation. It is used by evaluation agents to compare candidate notes against baselines and is not a writing reference for the note-generation workflow.

## Evaluation Agent

An agent that judges finished notes and related evaluation evidence. It must not generate, repair, or rewrite the note being evaluated.

## Strict Gate Verdict

An evaluation outcome where severe failures such as major factual errors, unsupported central claims, broken grounding, or misleading claim boundaries override numeric quality scores.
