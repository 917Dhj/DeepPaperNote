# Final quality review

Use this protocol after Grounding Lint and every Final Note Lint gate pass. The model judges analytical coverage; the scripts validate artifact structure, freshness, and revision state.

## Prepare the draft

The author writes one final Markdown file as UTF-8 without BOM, using LF line endings. Normalize it before lint or review, never after recording a passing review. For a Windows-authored draft, normalize in the run workspace and rerun lint before requesting review.

Freeze the plan during this loop. A source-justified plan correction returns to grounding and affected drafting stages; it does not reset the run's revision budget. Keep the same quality-review path and workspace throughout the run, including corrections and readability edits. Use a separate review path for a different run.

## Reviewer prompt

Give the reviewer this prompt with the explicit paths and resolved language filled in. Prefer a fresh subagent with no inherited drafting context. If the host has no subagents, use a dedicated main-session review pass under this same prompt.

> You are the Final Quality Reviewer. Read the complete current Markdown draft and frozen plan from the supplied paths. Use only those files by default. You may consult explicitly supplied source or bundle paths to resolve an ambiguity. Evaluate the draft in the supplied `output_language`, exactly `en` or `zh-CN`.
>
> Review from scratch on every attempt. Do not rely on an earlier verdict, author assurances, a passing lint, or an earlier drafting rationale. Write only the quality-review JSON artifact. Do not edit the note, plan, readability receipt, or revision journal.
>
> Check every planned item in these three groups:
>
> - `central_claims`: the note explains each claim and the evidence-to-claim relationship, including what the evidence actually proves. A keyword mention is insufficient.
> - `mechanism_result_map`: the note explains each planned mechanism-to-result relationship. Listing a mechanism and a result separately is insufficient.
> - `claim_boundaries`: the note faithfully carries every boundary and each central claim's `what_it_does_not_prove`. Unsupported generalization fails this check.
>
> Mark a group true only when all its relevant plan items are faithfully reflected. For each missing or incorrect relationship, identify the exact plan item and a concrete required revision. Do not invent facts, weaken the plan to fit the draft, or turn broad stylistic preferences into V1 blocking findings. The wider writing requirements still apply to the author.
>
> Write the exact closed artifact below. Compute hashes from the actual raw file bytes with a tool. Never guess a digest. Use the configured language for `reason` and `required_revision`; retain the schema keys and JSON pointers as written. Do not include commentary or extra fields.

Quality artifact shape:

```json
{
  "schema_version": 1,
  "output_language": "en",
  "verdict": "pass",
  "reviewed_note_sha256": "<actual raw draft SHA-256>",
  "reviewed_plan_sha256": "<actual raw plan SHA-256>",
  "checks": {
    "central_claims": true,
    "mechanism_result_map": true,
    "claim_boundaries": true
  },
  "blocking_findings": []
}
```

Use lowercase 64-character SHA-256 values. A passing artifact has all three literal booleans true and no findings. A failing artifact uses `verdict: "fail"`, at least one false check, and a finding for every false check. Every finding names a false check and contains exactly:

```json
{
  "check": "central_claims",
  "plan_ref": "/central_claims/0",
  "reason": "The note states the improvement but omits the planned evidence-to-claim explanation.",
  "required_revision": "Explain how the planned evidence supports this claim and limit the conclusion to that evidence."
}
```

Allowed references name an existing item at `/central_claims/N`, `/mechanism_result_map/N`, or `/claim_boundaries/N`, matching the failed check. Boundary findings may also use `/central_claims/N/what_it_does_not_prove`. Indices are zero-based canonical decimals. Empty strings, arbitrary pointers, unknown fields, duplicate keys, and inconsistent verdicts are invalid executions.

## Record every result

After the reviewer writes the artifact, the author runs the existing writer's record phase:

```sh
python scripts/write_obsidian_note.py --record-final-quality-review \
  --language en --content-file RUN/note.md --plan-file RUN/note_plan.json \
  --final-quality-review RUN/note.final_quality_review.json
```

Pass the run's actual language and paths. This phase needs no title, save destination, or Vault configuration. It writes only its workspace state and phase output. Read the structured verdict and `revision_allowed`; a valid failing review is recorded even though the command returns failure. Invalid or stale executions leave state unchanged and must be retried without treating them as content failures.

The journal is derived from the explicit review path with its suffix replaced by `.state.json`. Retain it; do not reset it to obtain more revisions. Invoke commands serially. Final Save requires the current passing review to have been recorded; saving does not implicitly record a pass.

An initial valid fail authorizes a revision. The next valid review of changed note bytes consumes one of two revision slots. Repeat that sequence at most twice. Reprocessing the current review is idempotent; replaying an older observation cannot restore an old pass. Same-byte rereviews and plan corrections preserve pending failure and exhaustion. After the second revision fails, stop automatic rewriting and report the remaining findings. A later passing artifact for different bytes cannot bypass that exhaustion.

## Readability and final save

After a recorded quality pass, read the whole note for fluency, terminology, line breaks, and renderable math. Preserve evidence, numerical results, stable proper nouns, and analytical depth. If this pass changes the draft, rerun Final Note Lint and a fresh full quality review, record the result, and reread the resulting version for readability.

For the final unchanged version, write a separate receipt with exactly:

```json
{
  "schema_version": 1,
  "output_language": "en",
  "verdict": "pass",
  "reviewed_note_sha256": "<actual raw final draft SHA-256>"
}
```

Formal Save receives explicit `--content-file`, `--plan-file`, `--final-quality-review`, and `--final-readability-review` paths alongside its existing lint, grounding, source, and figure-decision inputs. All checks must describe the same final version. Any draft or plan byte change invalidates its prior quality review; any draft change invalidates the readability receipt. Review JSON and journals remain in the workspace, outside the saved paper folder.

If using `--output` for status JSON, keep it outside the destination paper directory and separate from every input artifact. The writer refuses paths that could overwrite a note, archive record, image, review, or journal, including when reporting a save conflict.
