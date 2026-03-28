# Changelog

This file tracks notable **release-level** changes to DeepPaperNote.

It is not intended to record every small edit, wording tweak, or internal refactor.
Add an entry here when the project meaningfully changes for users, for example:

- a new capability is added
- a new workflow becomes officially supported
- a new integration or interface is introduced
- a release changes how users install, run, or rely on the skill

## Unreleased

- No unreleased user-facing changes yet.

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
