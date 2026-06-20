# DeepPaperNote Regression Workflow

Status: v1
Audience: agents running or reviewing DeepPaperNote evaluation experiments
Scope: real-paper regression testing for final note quality

This document defines the experiment workflow. It explains how to choose papers,
run baseline and candidate notes, collect artifacts, evaluate outputs, and decide
whether a change produced a real improvement.

The quality scoring standard lives in `evals/note-quality-rubric.md`. The prompt
template for the note evaluator lives in `evals/note-evaluator-prompt.md`.

## Core Principle

A regression experiment compares raw generated outputs under controlled
conditions. Do not let the same agent generate a note and judge its own quality.
Do not manually repair generated notes before evaluation.

A useful experiment keeps these variables stable:

- paper set
- runner tool and model settings
- prompt shape
- installed skill version for each run
- vault layout
- output artifact layout
- evaluation rubric version

## Recommended Agent Roles

Use these roles as separate sessions or clearly separated phases.

### Paper Finder Agent

Selects the test papers. It is read-only and must not run DeepPaperNote.

### Baseline Runner Agent

Runs the frozen baseline skill version and writes baseline notes plus artifacts.
It does not evaluate quality.

### Candidate Runner Agent

Runs the candidate skill version on the exact same paper set. It does not
evaluate quality.

### Artifact Auditor Agent

Checks whether the candidate run respected Source Corpus, bundle, grounding,
lint, figure/table, and save contracts. It does not judge final note quality.

### Note Evaluator Agent

Uses `evals/note-quality-rubric.md` to compare baseline notes against candidate
notes. It does not generate or repair notes.

### Regression Judge Agent

Synthesizes the Artifact Auditor and Note Evaluator outputs into one experiment
verdict.

## Phase 1: Select Real Papers

Choose papers before running any baseline or candidate note.

The paper set should include 4 primary papers and 2 backups. Start small enough
to inspect outputs, then grow the fixed set once the workflow is stable.

### Selection Criteria

Prefer papers with:

- stable identity evidence, such as DOI, arXiv ID, venue, year, or local PDF
- available full text or reliable PDF attachment
- enough technical content to require a deep note
- existing baseline notes when available
- varied stress patterns

Cover these paper types when possible:

- benchmark or evaluation paper
- method, model, or system paper
- appendix-heavy paper
- figure/table-heavy paper
- paper where limitations or discussion are important for interpretation

Avoid papers that are too short, only abstract-level, missing a usable source, or
too ambiguous to identify reliably.

### Paper Selection Output

The Paper Finder Agent should output a table with this shape:

```text
Title | Type | Venue/Year | Note path | PDF or source evidence | Why it is a good test | What the change should help with | Risk
```

The final paper list must identify:

- 4 primary test papers
- 2 backup papers
- the expected stress point for each paper

## Phase 2: Freeze The Baseline

Run baseline before candidate. Without a frozen baseline, the experiment can only
say that a candidate looks acceptable, not that it improved.

The baseline should be:

- a released version
- a pre-change commit
- or another explicitly named reference version

Record the baseline identity:

- git ref or release tag
- installed skill source
- runner tool
- model settings
- prompt template
- run timestamp

Do not reuse old baseline artifacts unless they were produced with the same paper
set, runner settings, prompt shape, and artifact collection rules.

## Phase 3: Run Baseline Notes

For each selected paper:

1. Create an isolated run directory.
2. Create or assign an isolated test vault.
3. Install or sync the baseline skill version.
4. Run the runner tool with the standard short prompt.
5. Save the raw final note and all artifacts.
6. Do not edit the note after generation.

The runner prompt should stay short. It should specify only:

- no subagents
- use the installed DeepPaperNote skill
- save to the specified test vault
- the paper task

Use the same prompt shape for baseline and candidate.

## Phase 4: Run Candidate Notes

Run candidate after baseline on the same paper list.

For each selected paper:

1. Use the same paper identity input.
2. Use the same runner tool and model settings.
3. Use the same prompt shape.
4. Use an isolated candidate run directory and test vault.
5. Install or sync the candidate skill version.
6. Save the raw final note and all artifacts.
7. Do not edit the note after generation.

Baseline and candidate runners should not run concurrently when they share global
state such as an installed skill directory.

## Phase 5: Collect Artifacts

Each paper run should produce a manifest that maps the paper to its note and
artifacts.

Recommended run layout:

```text
<RUN_ROOT>/
  manifest.json
  baseline/
    <paper_slug>/
      final_note.md
      artifacts/
  candidate/
    <paper_slug>/
      final_note.md
      artifacts/
  reports/
```

Collect these artifacts when available:

- final Markdown note
- runner transcript or last message
- metadata JSON
- source manifest
- raw sections JSONL
- synthesis bundle
- note plan JSON
- grounding lint output
- note lint output
- figure/table decisions
- figure/table assets or copy logs
- Obsidian save output

Missing artifacts should be recorded, not silently ignored.

## Phase 6: Artifact Audit

The Artifact Auditor determines whether the run respected workflow contracts.
It does not evaluate final prose quality.

The auditor should check:

- whether Source Corpus artifacts exist and are internally consistent
- whether `source_manifest.json` and `raw_sections.jsonl` were the canonical
  text-derived reading input
- whether old diagnostic derived views became model-facing writing inputs
- whether truncation or partial reading was explicit
- whether grounding lint used valid section IDs or page ranges
- whether figure/table decisions were fail-closed
- whether final save behavior preserved required files and paths

Artifact audit outcomes:

- `pass`
- `partial`
- `fail`
- `unknown`

An artifact improvement alone is not the same as final note improvement. It can
support an `architectural_improvement_only` conclusion when final note quality
does not materially improve.

## Phase 7: Note Evaluation

The Note Evaluator uses `evals/note-evaluator-prompt.md` and
`evals/note-quality-rubric.md`.

For each paper, the evaluator receives:

- paper identity evidence
- baseline final note
- candidate final note
- available baseline artifacts
- available candidate artifacts
- optional source evidence

The evaluator must:

- compare raw notes only
- run all hard gates
- score all eight rubric dimensions
- cite evidence for material score differences
- decide whether the candidate beats the baseline
- emit the rubric JSON report

The evaluator must not:

- rewrite notes
- patch missing sections
- rerun DeepPaperNote
- use a different rubric
- treat clean formatting as content improvement by itself

## Phase 8: Regression Judgment

The Regression Judge combines:

- run manifest
- artifact audit report
- note evaluation report
- runner failures or missing artifacts

It assigns one experiment-level verdict.

### Verdict Values

Use these values:

- `hard_fail`
- `regression`
- `no_material_change`
- `partial_improvement`
- `real_improvement`
- `architectural_improvement_only`

### What Counts As Real Improvement

`real_improvement` means the candidate is materially better than baseline on
final note quality, not merely cleaner or more structured.

To claim `real_improvement`, the candidate should:

- pass all known hard gates in `evals/note-quality-rubric.md`
- improve Evidence Chain Coverage or Mechanism/Protocol Depth
- preserve or improve Claim Boundaries and Limitations
- avoid factual, grounding, figure/table, citation, path, or readability
  regressions
- improve for reasons tied to paper evidence
- show the improvement on most primary papers, not only one cherry-picked case

### What Does Not Count As Real Improvement

Do not claim real improvement for:

- prettier formatting only
- longer notes without stronger evidence coverage
- more sections without better mechanism or result explanation
- artifact contract cleanup that does not change final note quality
- improvements on one paper paired with serious regressions on others
- candidate notes that fail a severe hard gate

Use `architectural_improvement_only` when artifacts or contracts improved but
the final note quality is not materially better yet.

## Minimum First Experiment

For the first reusable regression run:

1. Choose 4 primary papers and 2 backups.
2. Run one baseline version.
3. Run one candidate version.
4. Audit artifacts for all primary papers.
5. Evaluate notes for all primary papers.
6. Produce one experiment summary.

Do not add another runner tool until the baseline/candidate workflow is stable.

## Final Experiment Summary

The Regression Judge should produce:

- experiment id
- baseline version
- candidate version
- paper list
- runner settings summary
- artifact audit summary
- note evaluation summary
- per-paper verdicts
- experiment-level verdict
- whether optimization success can be claimed
- next recommended action

The summary should distinguish:

- mechanism improved but note quality did not
- note quality improved but artifacts regressed
- one-paper improvement
- broad real improvement
- failed or inconclusive experiment
