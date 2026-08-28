# User Configuration

DeepPaperNote can resolve a run entirely from Run Overrides. It also supports one optional device-local User Configuration at `~/.deeppapernote/config.json` for fallback values and explicit future preferences:

For isolated validation only, `DEEPPAPERNOTE_CONFIG_PATH` may relocate this one file for the current process. It is not a preference, does not create a second configuration layer, and must not be persisted into the configuration itself.

- `output_language`: `zh-CN` or `en`
- `save_mode`: `workspace` or `obsidian`
- `obsidian_vault`: existing absolute directory, required only in Obsidian mode
- `papers_dir`: safe relative path inside the Vault, required only in Obsidian mode

There is no implicit language or save-mode default. Workspace mode ignores stored Obsidian fields for the current run but preserves them for a later Obsidian run. Destination writability is a Formal Save concern; configuration inspection never creates a probe file in the workspace or Vault.

## Configuration admission

Complete Configuration Readiness before paper identity resolution:

1. Resolve the explicit request, CLI arguments, and current process environment in precedence order.
2. When those Run Overrides contain every active field and pass validation, complete Configuration Readiness without reading User Configuration.
3. Otherwise run `scripts/user_configuration.py` without setters. The inspector returns exactly one structured User Configuration state: `ready`, `needs_input`, `invalid`, or `blocked`.
4. For `needs_input` on first use, ask one Configuration Prompt Batch for the unresolved active fields. Require `obsidian_vault` and `papers_dir` when the resolved Save Mode is Obsidian. For later repair, ask only for `prompt_fields`.
5. For migration candidates, show the candidates and obtain confirmation before persisting future preferences. Candidates may still act as current-process Run Overrides when they are actually present in the process environment.
6. Persist confirmed preferences with the relevant `--set-output-language`, `--set-save-mode`, `--set-vault`, and `--set-papers-dir` options. Use `--replace-invalid` only after the user explicitly confirms replacement of malformed or non-object JSON.
7. Run the inspector again after a Preference Change. Persistence completes only when it returns `ready` after atomic write and readback validation; then resolve the run again.

Treat `invalid` as repairable input. Treat `blocked` as an I/O boundary: report its issue, preserve the current file, and stop before paper work. Never claim a preference was saved unless readback returned `ready`.

## Resolution and persistence

Resolve each preference using this exact precedence; an explicit request is an explicit current-run parameter, including a natural-language request:

`explicit request > CLI > current process environment > User Configuration`

An explicit request about the current paper is a Run Override. Translate it to the matching runtime override and leave `config.json` byte-for-byte unchanged. Persist only explicit future-default wording as a Preference Change.

Current process environment values are first-class Run Overrides and may satisfy the entire run without a configuration-file read. Shell startup files are not read when the inherited process environment is complete. If fallback is required while `config.json` is absent, supported shell values may be shown as migration candidates; they become persistent preferences only after confirmation.

Preference Changes preserve unknown JSON fields and report a warning. Malformed or non-object JSON receives a unique invalid backup before a confirmed replacement. Writes use a same-directory temporary file, atomic replacement, and exact reread comparison.

## Completion criteria

Configuration is ready only when every active field is present and valid, the resolved values contain no missing or invalid field, and the workflow has not begun identity resolution. A User Configuration file is not required when Run Overrides already meet that condition. Obsidian mode requires an existing absolute Vault and a traversal-safe relative paper directory. Workspace mode requires neither Obsidian field and cannot be redirected by stale values.
