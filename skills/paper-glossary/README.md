# Paper Glossary

`paper-glossary` builds reusable Obsidian glossary notes from `*_source_manifest.json` and `*_raw_sections.jsonl`. It remains self-contained and does not call a paper-reading workflow.

## One-Time Device Setup

Each person configures one term directory once per device. The directory must be inside an Obsidian vault: its nearest vault ancestor must contain `.obsidian`. The local configuration is `~/.paper-glossary/config.json`; it stores an absolute resolved vault root and the terms subdirectory, not a repository setting. Relative and Windows drive-relative vault roots are rejected. Later runs reuse it.

Setup may create `~/.paper-glossary/config.json`; before selection, no glossary notes or article Markdown are written. Run commands from the repository root and replace each quoted `<vault>` placeholder with the real vault path.

## Windows PowerShell

```powershell
py -3.12 skills\paper-glossary\scripts\configure_glossary.py --terms-dir '<vault>\Glossary'
py -3.12 skills\paper-glossary\scripts\configure_glossary.py --show
py -3.12 skills\paper-glossary\scripts\configure_glossary.py --reset
py -3.12 skills\paper-glossary\scripts\configure_glossary.py --validate-article '<vault>\Papers\example.md'
py -3.12 -m pytest -q skills\paper-glossary\tests --basetemp .pytest-tmp-paper-glossary
```

## macOS / Linux Bash

```bash
python3 skills/paper-glossary/scripts/configure_glossary.py --terms-dir '<vault>/Glossary'
python3 skills/paper-glossary/scripts/configure_glossary.py --show
python3 skills/paper-glossary/scripts/configure_glossary.py --reset
python3 skills/paper-glossary/scripts/configure_glossary.py --validate-article '<vault>/Papers/example.md'
python3 -m pytest -q skills/paper-glossary/tests --basetemp .pytest-tmp-paper-glossary
```

When article links are requested, provide the article Markdown path explicitly. It must be a `.md` file in the same Obsidian vault as the configured term directory; the skill never guesses an article from the paper source artifacts.

`--source-manifest` is required for proposal, review recording, and triage. `--raw-sections` is an optional override for the manifest's `raw_sections_path`, not a standalone replacement. The artifact workflow is:

1. Run `plan_glossary.py --propose ... --output proposal.json`.
2. Perform one semantic review, then record its exact ordered subset with `--review-proposal proposal.json --reviewed-terms ... --output reviewed.json`.
   If this produces an **empty reviewed shortlist**, report `no_candidates` and stop without displaying an empty selector.
3. Display the complete reviewed shortlist as numbers and wait. Resolve number responses or `全部写入` to exact names outside the CLI.
4. Run triage with `--reviewed-shortlist reviewed.json --terms ...`; `--terms` alone is rejected.
5. Pass triage to inventory, inventory to the writer at the **configured glossary directory** (use `--config-path` only to select that device-local configuration), and successful writer results to the linker when an article was requested.

For inventory, writer, and linker, always pass the current `--source-manifest`, optional `--raw-sections`, and saved `--reviewed-shortlist`. Inventory reads the saved `--triage` as its input; writer and linker also require that same saved `--triage` and enforce exact ordered `term` and `surface_forms` equality with it. These post-triage CLIs recompute the current proposal/review chain before writing. When the writer receives `--article`, `paper_link` is **derived from the resolved article Markdown stem**. A glossary-only writer invocation omits `--article` and derives `paper_link` from the **validated manifest `paper_id`**; do not run the linker for that branch because it rejects a writer artifact with **no bound article path**.

Proposal candidates carry ordered paper-grounded `surface_forms` plus SHA-256 provenance and the bounded candidate/summary material needed to recompute it. Inventory and writer both fail closed unless proposal, review, and selection digests recompute from one matching paper/source chain and the exact ordered forms. Review, triage, inventory, and writer results preserve those forms; model-authored note aliases are metadata and are not article-match forms. Writer output also preserves `triage_sha256`, validated provenance, and context and binds the triage identity plus exact ordered mappings with `mappings_sha256`; the linker recomputes that digest and validates every note path, stem, and grounded form. See `SKILL.md` and `references/file-contract.md` for exact article and glossary-only invocations and JSON contracts.
