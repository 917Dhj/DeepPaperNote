# Changelog

This file tracks notable **release-level** changes to DeepPaperNote.

It is not intended to record every small edit, wording tweak, or internal refactor.
Add an entry here when the project meaningfully changes for users, for example:

- a new capability is added
- a new workflow becomes officially supported
- a new integration or interface is introduced
- a release changes how users install, run, or rely on the skill

## Unreleased

### Added

- Initial public Codex-first skill workflow for generating a deep-reading note from one paper.
- Model-facing synthesis bundle pipeline with deterministic evidence gathering.
- Placeholder-first figure planning and Obsidian folder-per-paper output structure.
- Zotero-first helper workflow for local-library-first paper resolution.

### Documentation

- Bilingual project README (`README.md` and `README.zh-CN.md`).
- MIT license and initial project metadata via `pyproject.toml`.

### Changed

- Standardized figure placeholders to a stable callout format.
- Shifted the architecture toward model-first paper understanding.
- Moved image output into paper-local `images/` folders.

### Notes

- The project is still in early public-facing preparation.
- Tests, CI, and public examples are still being added.
