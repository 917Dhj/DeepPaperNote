# Acquisition Paper Identity Is A First-Class Contract

Status: accepted

DeepPaperNote's acquisition artifact reuse work exposed that paper identity can drift while still flowing into later artifacts, for example a source PDF/title being accepted with incomplete or contradictory metadata. We will treat Paper Identity as a first-class acquisition contract, separate from both general metadata enrichment and the Source Corpus reading interface.

The acquisition layer owns Work-Level Identity, Source Manifestation, identity evidence, identity equivalence, bounded repair, and an explicit Identity Verdict. Downstream stages must consume an accepted Canonical Identity Artifact rather than independently trusting title, DOI, arXiv, PDF metadata, filename, or provider records from earlier acquisition artifacts.

The pipeline must run an initial identity check after resolution, then a definitive repair-and-verify step after metadata collection and before PDF fetch. Repairable identities enter bounded Identity Repair before fail-closed behavior is allowed; fail closed is only valid after repair is exhausted or automatic selection remains unsafe.

## Considered Options

Gate-only validation would stop low-confidence runs quickly, but it would also block cases that acquisition can repair automatically. This was rejected because fail closed before repair makes the pipeline brittle and loses recoverable papers.

Leaving identity fields embedded across resolve, metadata, and fetch artifacts keeps the current shape simple, but it obscures which identity was accepted, which evidence was trusted, and whether a later artifact reused or contradicted an earlier one. This was rejected because it makes both regression audits and downstream safety decisions unreliable.

Letting downstream note-writing stages repair visible identity problems was rejected because it is too late: the wrong PDF, wrong work, broken source path, or citation damage may already have shaped the evidence bundle before the writer sees the note.

The chosen design is a first-class Canonical Identity Artifact plus an Identity Repair Trace. Original resolve, metadata, and fetch artifacts remain provenance; they are not overwritten to hide repair.

## Consequences

The Canonical Identity Artifact should carry a narrow contract: run status, paper ID, identity verdict, work-level identity, source manifestation, selected identity evidence, equivalence decision, warnings, and a path to the repair trace. Full provider payloads, rejected candidates, repair attempts, and detailed evidence belong in trace/provenance artifacts.

Work-Level Identity and Source Manifestation are distinct. A published PDF, arXiv version, Zotero attachment, or local PDF may be accepted as manifestations of the same Paper Identity when title, leading authors, abstract or first paragraph, external work linkage, and PDF structure support equivalence. Such manifestation differences are not automatically ambiguity.

Final note metadata and core information should display the Work-Level Identity, while source/provenance sections disclose the Source Manifestation actually read. Page numbers, figure/table locations, section references, and grounding evidence bind to the Source Manifestation, not to another equivalent manifestation.

`accepted_with_warnings` is allowed only when identity is safe enough for downstream use but non-blocking metadata uncertainty remains. Those warnings may affect metadata, provenance, citation wording, or over-specific venue/year claims, but must not degrade or distract the analytical body of the final note.

Regression and artifact audits should evaluate identity reuse through the explicit verdict and repair trace. Acquisition architecture improvements count as final note quality improvements only when they prevent or fix downstream wrong identity, wrong PDF, metadata contradiction, missing source evidence, broken path, citation damage, or comparable note-visible failures.
