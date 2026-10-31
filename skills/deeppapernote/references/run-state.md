# Inspect a run

Use the read-only status query to inspect one run's selected artifacts, find missing or stale evidence, and identify the next action.

From the repository root:

```sh
python skills/deeppapernote/scripts/run_state.py status \
  --workdir /tmp/paper-run --prefix paper
```

Use the same prefix passed to `run_pipeline.py`. The default prefix is `run`. The work directory must already exist. The query prints JSON to stdout and does not create the directory, run producers, record reviews, contact services, or write into the Vault. It does not read current User Configuration as evidence of a past run.

## Select the artifacts

The query uses the pipeline's fixed filenames for deterministic artifacts. It does not search for the newest matching file. Use a separate prefix for each run sharing a directory.

Drafts, plans, admission results, lint reports, reviews, and save results have no fixed filenames. Select them with an optional bindings file:

```sh
python skills/deeppapernote/scripts/run_state.py status \
  --workdir /tmp/paper-run --prefix paper \
  --bindings /tmp/paper-run/status-bindings.json
```

Example bindings:

```json
{
  "schema_version": 1,
  "artifacts": {
    "admission": "admission.json",
    "note_plan": "paper.plan.json",
    "draft": "paper.md",
    "grounding_lint": "grounding.json",
    "note_lint": "lint.json",
    "quality_review": "paper.final_quality_review.json",
    "readability_review": "paper.final_readability_review.json",
    "save_receipt": "save.json"
  },
  "context": {
    "paper_reference": "arXiv:2304.02643",
    "output_language": "zh-CN",
    "save_mode": "obsidian",
    "vault": "/path/to/vault",
    "papers_dir": "Research/Papers"
  }
}
```

Replace the example values with the actual files and resolved run context. The bindings file path is relative to the command's current directory unless absolute. Paths inside `artifacts` are relative to `--workdir` unless absolute. Machine artifact bindings can override the pipeline filenames for an existing run.

The file requires `schema_version: 1`. Its optional `artifacts` and `context` objects have closed schemas. Unknown keys, duplicate JSON keys, and invalid types are rejected. Context accepts `paper_reference`, `output_language`, `save_mode`, `vault`, `papers_dir`, and `target_directory`. Context supplies command arguments; it does not certify that a stage passed or approve an overwrite.

An omitted late artifact is reported as an unresolved selection. An explicitly selected missing file is reported as missing. Neither causes the query to choose another file. The quality journal is derived from the selected review path by replacing its suffix with `.state.json`, following `final-quality-review.md`; it cannot be redirected separately.

To retain admission or save evidence for a later query, use the existing writer's `--output` when running that stage. Keep those JSON outputs in the run workspace, outside the paper's destination directory. The status query does not reconstruct an unrecorded save result.

## Read the report

A successful query returns exit code 0 even when the run is incomplete or an artifact failed validation. Invalid command arguments, a missing work directory, or invalid bindings return exit code 2. The report's `status: "ok"` means inspection succeeded.

Each stage reports its selected artifacts, issues, and unmet dependencies. The stage statuses mean:

| Status | Meaning |
| --- | --- |
| `missing` | Required evidence is unselected or unavailable. |
| `invalid` | An artifact is malformed or violates its contract. |
| `failed` | Valid evidence records a failed check or blocked action. |
| `stale` | A recorded binding disagrees with current input bytes. |
| `present_unverified` | Available evidence cannot prove full input freshness. |
| `passed` | The implemented checks for this stage pass on the selected files. |

Inspect all reported issues, including those after the first blocker. The query checks downstream evidence even when an earlier artifact is missing. Unmet dependencies remain visible separately from a stage's own result.

`next_action` identifies the earliest actionable gap. It includes an executable argument list only when every required argument is known. Otherwise it names missing context, a model task, or a user decision. It does not fill commands with invented paths or grant permission to overwrite a note. Figure-decision commands carry the current admission's source-bound `asset_subdir` in Obsidian mode; workspace mode uses `images`. An unrecorded quality verdict needs the existing record phase. A recorded failure can require a revision or a stop when the two-revision limit is exhausted.

The summary provides the evidence available for the Final user report, including gate results, warnings, figure decisions, saved path and mode, domain, and hash agreement. Saved-note claims require both a selected successful save receipt and the actual saved bytes. A missing receipt means the save cannot be verified from this selection; it does not prove that no save occurred.

## Freshness limits

The query reuses the existing lint, visual-review, and final-review contracts. Grounding Lint binds the plan, source manifest, and decisions. Final Note Lint binds the plan and normalized draft. Quality and readability bind the final raw draft bytes, and a quality pass must be recorded in its current journal.

Several early producers do not record their input hashes. Those files can remain `present_unverified` even when a later gate passes. Grounding Lint also has no bundle hash, so its receipt cannot prove that it checked the latest bundle. The report lists these provenance gaps and does not infer freshness from timestamps.

Use the canonical workflow in `SKILL.md` to perform the required stages. Status inspection does not replace source reading, model judgment, final readability review, or Save Target Admission. Pipeline splitting and automatic resume are separate changes.
