---
status: accepted
---

# Make final quality review a freshness-bound save gate

DeepPaperNote will turn `final_quality_review` into a generation-side save gate for plan-to-note analytical coverage. This gate complements deterministic lint and remains separate from the external Note Evaluation Rubric: V1 blocks only when the final Markdown fails to carry through commitments already frozen in `note_plan`.

## Decision

V1 checks every planned `central_claims`, `mechanism_result_map`, and `claim_boundaries` item. Claim-boundary review also covers each central claim's `what_it_does_not_prove`. A check passes only when every relevant plan item is faithfully reflected in the note; mentions without an evidence-to-claim, mechanism-to-result, or claim-to-boundary relationship do not pass.

A dedicated Final Quality Reviewer performs a full review from scratch on every attempt. Prefer a subagent with no inherited drafting context; hosts without subagents may use a dedicated main-session pass under the same fixed prompt contract. The reviewer reads the note and plan by default, may read explicitly supplied source or bundle paths only to resolve ambiguity, writes only the review artifact, and never edits the note or plan. The canonical prompt will live in `skills/deeppapernote/references/final-quality-review.md`.

The reviewer writes a strict, closed JSON artifact in the run workspace, conventionally `<note>.final_quality_review.json`, with this top-level shape:

```json
{
  "schema_version": 1,
  "output_language": "en",
  "verdict": "pass",
  "reviewed_note_sha256": "...",
  "reviewed_plan_sha256": "...",
  "checks": {
    "central_claims": true,
    "mechanism_result_map": true,
    "claim_boundaries": true
  },
  "blocking_findings": []
}
```

Each blocking finding contains exactly `check`, `plan_ref`, `reason`, and `required_revision`. Findings use existing-item JSON pointers: `/central_claims/N`, `/mechanism_result_map/N`, or `/claim_boundaries/N`; a boundary finding may also use `/central_claims/N/what_it_does_not_prove`. Each finding names a false check, and every false check has a corresponding finding. A passing artifact requires all checks to be true and no findings. Unknown fields, duplicate keys, nonliteral booleans, malformed or inconsistent JSON, missing artifacts, and unsupported schema versions are invalid gate executions rather than content failures. `output_language` binds the artifact to the run's exact `en` or `zh-CN` profile.

The SHA-256 values bind to the exact bytes of the reviewed Markdown and plan files. Before lint or review, the author writes the final draft as UTF-8 without BOM and with LF line endings. The save gate rejects noncanonical drafts rather than changing reviewed bytes during save. Formal gated saves explicitly pass `--content-file`, `--plan-file`, and `--final-quality-review`; paths are not discovered by convention or trusted from review JSON. Any byte change makes the artifact stale. The saved note must match the reviewed draft's raw SHA-256; the existing normalized lint hash remains a separate check.

`write_obsidian_note.py` validates the artifact and refuses save unless it is current, passing, and recorded. Its `--record-final-quality-review` phase validates and records a pass or fail without resolving a save target. It requires explicit language, draft, plan, and review paths. No separate public validator script is added. Review artifacts and their state remain in the run workspace and are not copied into the Obsidian paper folder.

The plan is frozen during the gate loop. A source-justified plan correction exits the gate, reruns grounding and affected drafting stages, and invalidates prior reviews; the plan must not be weakened merely to match the note. A valid failing review may drive at most two note revisions globally. Invalid gate executions do not consume that quota. Every revision reruns lint and a context-free full review.

The record phase atomically maintains a small journal beside the explicit review path, replacing its `.json` suffix with `.state.json`. Keep that path and workspace for the entire run, including plan corrections; use a separate review path for another run. Commands run serially. A valid failure leaves a pending revision. A later valid review of changed note bytes consumes one revision; replaying the same current review is idempotent, and replaying an older review cannot restore an old pass. Fresh same-byte reviews do not clear pending failure or exhaustion. After two consumed revisions and another valid failure, the exhausted note hash remains fixed: changed bytes cannot be accepted by a later passing review or plan correction. Invalid or stale inputs leave state unchanged. Corrupt state is refused, not reset. This tracks observed workflow attempts, not hostile deletion or forgery of local files.

After a passing quality review, `final_readability_review` still runs. It writes a closed receipt with exactly `schema_version: 1`, `output_language`, `verdict: "pass"`, and `reviewed_note_sha256`. Formal Save requires this receipt through `--final-readability-review`. If readability edits the note, lint and a fresh full quality review must run again, followed by a readability reread of the final version. Formal save requires the same final note bytes to have completed lint and readability review and to match the current recorded passing quality review.

## Rejected alternatives

- Free-form prose or drafting-pass self-certification: not independently checkable.
- A full source-to-note evaluator or reuse of the external rubric: broader than the V1 failure mode.
- Mandatory subagent support: excludes hosts without that capability.
- Artifact discovery by filename or plan paths embedded in the artifact: ambiguous or self-referential enforcement.
- Canonicalized-content hashes: weaker than the agreed exact-version binding.
- A new validation CLI: duplicates the existing save-refusal boundary.

## Consequences

Existing save calls and tests must supply the new explicit inputs. Whitespace, encoding, or formatting-only changes invalidate a prior review, intentionally favoring fail-closed freshness over convenience. Gate correctness and note-quality effect will be evaluated separately; held-out real-paper baseline/candidate experiments are deferred until implementation and deterministic tests are complete.

Status JSON stays outside the destination paper directory and cannot alias input artifacts or the journal. Both successful saves and conflict reports enforce this before writing status, so status output cannot replace reviewed notes, archive records, or images.
