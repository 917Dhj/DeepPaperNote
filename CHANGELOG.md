# Changelog

This file tracks notable **release-level** changes to DeepPaperNote.

It is not intended to record every small edit, wording tweak, or internal refactor.
Add an entry here when the project meaningfully changes for users, for example:

- a new capability is added
- a new workflow becomes officially supported
- a new integration or interface is introduced
- a release changes how users install, run, or rely on the skill

## Unreleased

No unreleased user-facing changes yet.

## v2.0.0

- Strengthened note-depth planning with source-grounded central claims, claim boundaries, limiting-result coverage, mechanism-to-result mapping, comparative positioning, reusable takeaways, follow-up questions, and a separate final analytical quality review before readability polish.
- Expanded benchmark/dataset and clinical paper guidance to cover sample statistics, data access, privacy constraints, and reproducibility boundaries when the paper reports them.

## v1.1.1

Small patch release that fixes existing logic gaps.

### Fixed

- Tightened final-note linting so retained figure/table placeholders must use the standard `[!figure]` callout format.
- Strengthened table crop quality checks so crops contaminated by running prose or other figure/table captions fail closed.

### Notes

- This remains a stable release.
- The release asset continues to ship as a clean manually installable `DeepPaperNote.zip`.

## v1.1.0

Minor stable release with a major figure/table extraction quality upgrade.

### Added

- Added figure-level PDF asset extraction that renders caption-anchored page regions instead of relying only on raw xref image objects.
- Added richer `figure_assets` metadata for extracted figures and tables, including labels, captions, extraction kind, and visual quality signals.
- Added visual quality gates so weak crops can fail closed and remain placeholders instead of being treated as insertion-ready images.
- Added `figure_assets` to the synthesis bundle so model-side review can inspect richer figure/table candidates.
- Added regression tests for figure asset candidates, placeholder-first planning, label normalization, and visual quality rejection.

### Changed

- Improved extraction for complete figures, vector-heavy papers, fragmented LaTeX tables, and caption-on-bottom tables.
- Preserved DeepPaperNote's placeholder-first behavior: extracted figure assets are exposed as candidates, not automatic note insertions.
- Strengthened figure-placement and final-writing guidance around visual quality review and candidate handling.

### Contributors

- Incorporated the figure-level extraction work from PR #1 by KuangjuX, with follow-up changes to keep insertion semantics placeholder-first.

### Notes

- This remains a stable release.
- The release asset continues to ship as a clean manually installable `DeepPaperNote.zip`.

## v1.0.1

Patch release after `v1.0.0`.

### Changed

- Added YAML frontmatter and wikilink rules for Obsidian-native features.
- Fixed `lint_note.py` compatibility with YAML frontmatter.
- Added tests for frontmatter stripping and frontmatter-aware lint compatibility.
- Fixed wikilink target resolution with a lookup-first, fail-closed approach.
- Removed unused image assets that were no longer referenced by the README files.

### Notes

- This remains a stable release.
- The release asset continues to ship as a clean manually installable `DeepPaperNote.zip`.

## v1.0.0

First stable release of DeepPaperNote.

### Changed

- Reframed DeepPaperNote as a pure cross-agent skill for Claude Code, Codex, Cursor, Copilot, Gemini CLI, and other Agent Skills-compatible environments.
- Kept the root `SKILL.md` as the single canonical skill entrypoint.
- Updated installation guidance for `npx skills add 917Dhj/DeepPaperNote -a codex` and `npx skills add 917Dhj/DeepPaperNote -a claude-code`.
- Removed experimental onboarding/setup pseudo-surfaces and the temporary Claude plugin wrapper structure.
- Added `AGENTS.md` and `CLAUDE.md` for repo-level agent guidance.
- Added explicit Python `>=3.10` interpreter guidance for agents running bundled scripts.

### Preserved

- The evidence-first deep-reading pipeline.
- Obsidian-first output behavior.
- Figure/table placeholder-first policy.
- Lint gate and final readability review.

## v0.3.2-alpha

Fifth public alpha release of DeepPaperNote.

### Changed

- Strengthened `local_pdf -> enrich_metadata` so Zotero-style attachment filenames no longer dominate metadata resolution.
- Added local PDF metadata hints that prefer embedded PDF title, DOI, arXiv identifiers, and first-page title signals before falling back to cleaned filenames.
- Added local-PDF-only title correction so high-confidence external matches can replace noisy attachment-style titles without changing the global merge policy.
- Tightened candidate scoring so published venue/DOI records are preferred over preprint-style matches when both are available.
- Normalized common PDF ligatures such as `ﬁ` and `ﬂ` during text extraction so titles and other extracted strings are cleaner and more stable.

### Packaging

- Rebuilt the release zip from the latest `main` branch state for `v0.3.2-alpha`.

### Notes

- This is still an alpha release.
- Chinese remains the only fully supported output language.
- Figure replacement is still conservative and placeholder-first when image confidence is insufficient.

## v0.3.1-alpha

Fourth public alpha release of DeepPaperNote.

### Changed

- Changed the default Obsidian paper root from `20_Research/Papers` to `Research/Papers`.
- Aligned runtime path resolution, save behavior, and tests with the new default paper root so new notes land in the updated location consistently.

### Packaging

- Rebuilt the release zip from the latest `main` branch state for `v0.3.1-alpha`.

### Notes

- This is still an alpha release.
- Chinese remains the only fully supported output language.
- Figure replacement is still conservative and placeholder-first when image confidence is insufficient.

## v0.3.0-alpha

Third public alpha release of DeepPaperNote.

### Changed

- Added a dedicated `创新点` section near the front of the note and strengthened the front-matter contract.
- Added explicit `### 机制流程` guidance for method and system papers so the execution chain is reconstructed more clearly.
- Strengthened ablation handling so notes are more likely to capture failed settings, weaker variants, and trade-offs rather than only best-case results.
- Renamed the opening abstract block to `原文摘要翻译` and tightened the contract so it is treated as a Chinese translation of the original abstract rather than a newly written summary.
- Tightened the `核心信息` block into a fixed metadata zone and explicitly forbade analysis or judgment from leaking into it.
- Added a required `final_readability_review` stage after script lint to improve fluency, remove stiff phrasing, and reduce unnecessary English leftovers.
- Added a dedicated math syntax gate to catch common Obsidian / MathJax rendering failures before final save.
- Strengthened the overall workflow contract so the model is less likely to silently skip required stages, downgrade output behavior, or claim completion too early.
- Tightened Obsidian save rules and fixed the duplicated paper-slug directory bug during note writing.

### Packaging

- Added a release zip asset for v0.3.0-alpha and narrowed the release package to omit README files, license/changelog docs, and showcase media.

### Notes

- This is still an alpha release.
- Chinese remains the only fully supported output language.
- Figure replacement is still conservative and placeholder-first when image confidence is insufficient.

## v0.2.0-alpha

Second public alpha release of DeepPaperNote.

### Changed

- Strengthened the note-writing contract so technical papers are pushed closer to replication-oriented reading notes rather than polished summary rewrites.
- Added explicit short note planning before final note generation.
- Added equation-aware output guidance so key formulas can be preserved in LaTeX when they are central to understanding the method.
- Added stricter final self-review requirements for key numbers, method explanation depth, and technical completeness.
- Added stronger formatting checks for suspicious mid-sentence line breaks and math accidentally rendered as code.
- Updated the abstract section contract to keep both the original abstract and a Chinese translation.
- Made the Chinese README the default GitHub homepage and clarified that Chinese is currently the only fully supported note language.

### Documentation

- Split the English README into `README.en.md` while keeping the Chinese README as the default repository homepage.
- Updated homepage messaging to better emphasize replication-oriented technical note quality.

### Notes

- This is still an alpha release.
- Chinese remains the only fully supported output language at this stage.
- High-confidence figure replacement remains conservative; placeholder-first behavior is still preferred when image certainty is low.

## v0.1.0-alpha

First public alpha release of DeepPaperNote.

### Added

- Initial public Codex skill workflow for generating a deep-reading note from one paper.
- Model-facing synthesis bundle pipeline with deterministic evidence gathering.
- Placeholder-first figure planning and Obsidian folder-per-paper output structure.
- Zotero-first helper workflow for local-library-first paper resolution.
- Workspace fallback output when no Obsidian vault is configured.
- OCR fallback for low-text PDF pages.
- Domain-aware note routing that prefers existing vault domains before creating new ones.
- Minimal automated test suite and GitHub Actions CI.
- Setup-assistant entry points such as `/deeppapernote doctor` and `/deeppapernote start`.

### Documentation

- Bilingual project README (`README.md` and `README.zh-CN.md`).
- MIT license and initial project metadata via `pyproject.toml`.

### Changed

- Standardized figure placeholders to a stable callout format.
- Shifted the architecture toward model-first paper understanding.
- Moved image output into paper-local `images/` folders.

### Notes

- This is an alpha release.
- Figure replacement quality still depends on extraction quality and semantic matching confidence.
- Some environments may expose different `python3` interpreters across sessions; doctor now reports the active interpreter explicitly.
