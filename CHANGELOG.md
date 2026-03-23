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
