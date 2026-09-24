# Shared paper archive

Use this reference for Obsidian directory reuse, Connector handoff, and multiple PDF sources of one paper. `scripts/paper_archive.py` owns the deterministic archive rules; Connector vendors that module unchanged. The canonical Skill workflow still owns all reading, review, and Formal Save gates.

## Acquisition and selection

Pass the original user reference to `fetch_pdf.py --reference <reference>` alongside the accepted identity artifact. Before remote download, it searches the resolved Obsidian Vault for a verified local PDF. An explicit local input remains authoritative. An explicit arXiv revision wins; if absent locally, acquisition requests that revision of the accepted work and verifies the returned PDF. Without an explicit revision, select the highest local arXiv revision only when all available sources belong to the same comparable revision sequence. Never order sources by download time. Same-revision different-byte PDFs and incomparable sources require a choice.

For standalone read-only discovery, use `find_archived_source.py --input <metadata.json-or-reference> --vault <vault> --reference <original-reference>`. A `not_found` result permits normal acquisition. A `blocked` result is an ambiguity or verification failure, not permission to create a duplicate archive.

When multiple directories match, show their paths and content counts and ask the user to select the current destination. Carry `--target-directory <absolute-path>` through discovery, acquisition, preflight, and Formal Save. For ambiguous PDF sources, use `--source-sha256 <chosen-hash>` in discovery/acquisition. The returned `archive_source` also carries the selected directory through the Source Manifest. Selection does not waive identity or path checks.

## Admission and writing

Run the save script's preflight before drafting. Prefer verified matches over title-only candidates. Reuse a unique verified work directory, including a legacy PDF-only directory, without asking for registration. Work identity or exact PDF bytes must verify the match; a folder title alone is only a candidate. Mixed-work PDFs, malformed records, and paths outside the Vault fail closed. Existing directories anywhere inside the Vault are eligible; new directories remain under the configured papers root.

Read `asset_subdir` from preflight and pass it to `plan_figure_table_decisions.py --asset-subdir <value>`; rerun planning if earlier decisions used the default path. Bounded repairs retain this path. Use that paper-relative path for real figure embeds in the draft and figure/table decisions. The first source retains `images/`; additional sources use `images/<full-source-sha256>/`. Every figure still requires the normal source/identity/readability checks. Save does not reinterpret an old figure as belonging to another version.

The note path is bound to exact source bytes plus `output_language`. New source variants get separate version-labelled, hash-disambiguated note paths; existing filenames and links remain unchanged. An existing note for the same source and language still requires `--overwrite-existing-note --expected-existing-note-sha256 <reported-hash>` after user approval. Unbound notes are not adopted as completed notes.

## Directory record and migration

`.deeppapernote.json` schema 2 groups sources under one `work` identity. `work.provenance` retains evidence per identifier, including actual PDF-first-page evidence bound to its SHA-256; legacy records without evidence are marked `legacy_record`, not relabelled as verified provenance. `sources` is keyed by the actual PDF SHA-256. Each entry keeps its relative `pdf_path` when archived, known `arxiv_id`, source URLs, frozen `note_stem`, `asset_subdir`, and `notes` keyed by language. Each saved note binds its filename and final note SHA-256 to that source. A note-only source may omit `pdf_path`; Connector can attach its PDF later without rewriting the note.

Schema 1 records are read without mutation and upgraded on a successful write. Preserve original note/source bindings, filenames, and unrelated fields. Unknown versions remain unknown. A PDF collection adds no completed-note record. Both writers lock the Vault, reread the record, recheck source/destination, and replace the record atomically. A Connector registration failure reports the retained PDF as incomplete rather than claiming success.

## Shared location

Connector reads only `obsidian_vault` and `papers_dir` from the Skill's persistent User Configuration at `~/.deeppapernote/config.json`. Its extension ID and native-host installation settings remain separate. A missing or invalid shared location requires configuration repair; never use a conflicting legacy Connector destination. Reading or saving does not change language, save mode, unknown preferences, or persistent settings through a temporary Skill Run Override.
