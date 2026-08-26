# User Configuration

Use one device-local User Configuration at `~/.deeppapernote/config.json`:

- `output_language`: `zh-CN` or `en`
- `save_mode`: `workspace` or `obsidian`
- `obsidian_vault`: existing absolute directory, required only in Obsidian mode
- `papers_dir`: safe relative path inside the Vault, required only in Obsidian mode

There is no implicit language or save-mode default. Workspace mode ignores stored Obsidian fields. Destination writability is a Formal Save concern; configuration inspection never creates a probe file in the workspace or Vault.

## Configuration admission

Complete Configuration Readiness before paper identity resolution:

1. Run `scripts/user_configuration.py` without setters and read its structured state.
2. For `needs_input` on first use, ask one Configuration Prompt Batch for `output_language` and `save_mode`; require `obsidian_vault` and `papers_dir` in that same response when the user selects Obsidian. For later repair, ask only for `prompt_fields`.
3. For migration candidates, show the candidates and obtain confirmation for a complete configuration. Candidates alone never authorize the paper run.
4. Persist confirmed preferences with the relevant `--set-output-language`, `--set-save-mode`, `--set-vault`, and `--set-papers-dir` options. Use `--replace-invalid` only after the user explicitly confirms replacement of malformed or non-object JSON.
5. Run the inspector again. Configuration admission completes only when it returns `ready` after atomic persistence and readback validation; then continue the same paper request.

Treat `invalid` as repairable input. Treat `blocked` as an I/O boundary: report its issue, preserve the current file, and stop before paper work. Never claim a preference was saved unless readback returned `ready`.

## Resolution and persistence

Resolve each preference using this exact precedence:

`explicit request > CLI > current process environment > User Configuration`

An explicit request about the current paper is a Run Override. Translate it to the matching runtime override and leave `config.json` byte-for-byte unchanged. Persist only explicit future-default wording as a Preference Change.

While `config.json` is absent, supported process and shell values are migration candidates only. Once the file exists, shell startup files leave the preference path permanently; current process environment values remain run-scoped compatibility overrides.

Preference Changes preserve unknown JSON fields and report a warning. Malformed or non-object JSON receives a unique invalid backup before a confirmed replacement. Writes use a same-directory temporary file, atomic replacement, and exact reread comparison.

## Completion criteria

Configuration is ready only when every active field is present and valid, the resolved values contain no missing or invalid field, and the workflow has not begun identity resolution. Obsidian mode requires an existing absolute Vault and a traversal-safe relative paper directory. Workspace mode requires neither Obsidian field and cannot be redirected by stale values.
