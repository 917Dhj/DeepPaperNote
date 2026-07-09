# Paper Glossary

Companion skill for building reusable Obsidian glossary notes from paper source artifacts.

This directory is self-contained: scripts, tests, and file-contract reference material live under `skills/paper-glossary/`. It collaborates with paper-reading workflows only through `*_source_manifest.json` and `*_raw_sections.jsonl`.

Run the focused tests with:

```bash
py -3.12 -m pytest -q skills/paper-glossary/tests --basetemp .pytest-tmp-paper-glossary
```
