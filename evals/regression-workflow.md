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
- child Codex CLI prompt template
- installed skill version for each run
- vault layout
- output artifact layout
- evaluation rubric version

## Handoff Documents

Each agent should read the previous stage's output document before starting, then
write its own result document for the next agent. Use placeholders rather than
hard-coded local paths in prompts.

Recommended handoff chain:

```text
paper-set.md
  -> baseline-run-manifest.md
  -> candidate-run-manifest.md
  -> artifact-audit-report.md
  -> note-evaluation-report.md
  -> regression-summary.md
```

The runner manifests should also point to the machine-readable artifacts under
the run root.

## Goal Mode And Child Runner Prompts

Every workflow-stage agent should be started in goal mode. Use `/goal` as the
first line of each Agent Prompt Template in this document.

The independent per-paper Codex CLI sessions launched by the Baseline Runner and
Candidate Runner are different: they must not use `/goal`.

For each paper, the runner must launch an independent Codex CLI session with
exactly this prompt after replacing placeholders:

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

Do not add constraints, explanations, source paths, agent instructions, model
notes, or extra surrounding text to that child prompt. Record the exact child
prompt in the run manifest.

## Recommended Agent Roles

Use these roles as separate sessions or clearly separated phases.

### Paper Finder Agent

Selects the test papers. It is read-only and must not run DeepPaperNote.

### Baseline Runner Agent

Records the frozen baseline identity, runs the baseline skill version, and writes
baseline notes plus artifacts. It does not evaluate quality.

### Candidate Runner Agent

Runs the candidate skill version on the exact same paper set and writes candidate
notes plus artifacts. It does not evaluate quality.

### Artifact Auditor Agent

Checks whether the candidate run respected Source Corpus, bundle, grounding,
lint, figure/table, and save contracts. It does not judge final note quality.

### Note Evaluator Agent

Uses `evals/note-quality-rubric.md` to compare baseline notes against candidate
notes. It does not generate or repair notes.

### Regression Judge Agent

Synthesizes runner status, artifact audit, and note evaluation into one
experiment verdict.

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

The Paper Finder Agent should output a Markdown report with:

- 4 primary test papers
- 2 backup papers
- the expected stress point for each paper
- a table with this shape:

```text
Title | Type | Venue/Year | Note path | PDF or source evidence | Why it is a good test | What the change should help with | Risk
```

### Paper Finder Agent Prompt Template

```text
/goal

Goal:
Choose a reusable real-paper test set for a DeepPaperNote regression run.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- optional prior paper selection notes: <PRIOR_SELECTION_DOC_OR_NONE>
- paper source root or index: <PAPER_SOURCE_ROOT>

Task:
- Find 6 candidate papers: 4 primary papers and 2 backups.
- Prefer papers with stable identity evidence, usable PDF/source material, and enough technical depth.
- Cover benchmark/evaluation, method/model/system, appendix-heavy, figure/table-heavy, and limitations-heavy stress patterns when possible.
- Do not run DeepPaperNote.
- Do not modify notes, PDFs, or the vault.

Output:
- Write a Markdown paper-set report to <PAPER_SET_DOC>.
- Include the required selection table.
- Mark the 4 primary papers and 2 backups.
- For each primary paper, state the expected stress point and what a regression should reveal.
```

## Phase 2: Run Baseline Notes

Run baseline before candidate. Without a frozen baseline, the experiment can only
say that a candidate looks acceptable, not that it improved.

The Baseline Runner owns the baseline manifest. Before generating notes, it must
record:

- baseline git ref or release tag
- installed skill source
- runner tool
- model settings
- prompt template
- run timestamp
- paper-set document path
- run root and vault layout
- artifact collection rules

For each selected paper:

1. Create an isolated run directory.
2. Create or assign an isolated test vault.
3. Install or sync the baseline skill version.
4. Start one independent Codex CLI session per paper with the exact child prompt.
5. Save the raw final note and all artifacts.
6. Update the baseline manifest with present and missing artifacts.
7. Do not edit the note after generation.

The per-paper child Codex CLI prompt must be exactly:

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

The runner may control working directory, temp vault, installed skill version,
logging, and manifest collection outside the child prompt. It must not add any
extra text to the child prompt. Baseline and candidate must use the same child
prompt template.

Do not reuse old baseline artifacts unless they were produced with the same paper
set, runner settings, child Codex CLI prompt template, and artifact collection
rules.

### Baseline Runner Agent Prompt Template

```text
/goal

Goal:
Run the frozen baseline DeepPaperNote version for the selected paper set and
write a complete baseline manifest.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- paper set report: <PAPER_SET_DOC>
- baseline ref or release note: <BASELINE_REF_DOC_OR_VALUE>

Task:
- Record the baseline identity before running any paper.
- Use the exact per-paper child Codex CLI prompt template required by this workflow.
- For each primary paper, create an isolated run directory and test vault.
- Sync or install the baseline skill version.
- For each primary paper, start a separate independent Codex CLI session.
- In each child Codex CLI session, use exactly this prompt after replacing placeholders: `给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。`
- Do not add any other text to the child Codex CLI prompt.
- Preserve raw final notes, runner logs, and all available artifacts.
- Record the exact child prompt, temp vault path, run directory, final note path, logs, exit status, available artifacts, and missing artifacts.

Constraints:
- This workflow-stage agent uses `/goal`; the per-paper child Codex CLI sessions must not use `/goal`.
- Do not batch multiple papers into one Codex CLI session.
- Do not evaluate note quality.
- Do not repair or rewrite generated notes.
- Do not run candidate code.
- Do not change the paper set.

Output:
- Write <BASELINE_MANIFEST_DOC>.
- The manifest must include baseline identity, runner settings, child Codex CLI prompt template, per-paper exact child prompt, per-paper status, final note paths, artifact paths, logs, exit status, and missing artifacts.
- Also write or update machine-readable manifest data under <BASELINE_RUN_ROOT> when practical.
```

## Phase 3: Run Candidate Notes

Run candidate after baseline on the same paper list.

For each selected paper:

1. Use the same paper identity input.
2. Use the same runner tool and model settings.
3. Use the same exact child Codex CLI prompt template.
4. Use an isolated candidate run directory and test vault.
5. Install or sync the candidate skill version.
6. Save the raw final note and all artifacts.
7. Update the candidate manifest with present and missing artifacts.
8. Do not edit the note after generation.

Baseline and candidate runners should not run concurrently when they share global
state such as an installed skill directory.

The per-paper child Codex CLI prompt must be exactly the same template used by
the baseline:

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

### Candidate Runner Agent Prompt Template

```text
/goal

Goal:
Run the candidate DeepPaperNote version on the exact same paper set and write a
candidate manifest that lines up with the baseline manifest.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- paper set report: <PAPER_SET_DOC>
- baseline manifest: <BASELINE_MANIFEST_DOC>
- candidate ref or change summary: <CANDIDATE_REF_DOC_OR_VALUE>

Task:
- Confirm the paper set and child Codex CLI prompt template match the baseline manifest.
- Sync or install the candidate skill version.
- For each primary paper, create an isolated candidate run directory and test vault.
- For each primary paper, start a separate independent Codex CLI session.
- In each child Codex CLI session, use exactly this prompt after replacing placeholders: `给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。`
- Do not add any other text to the child Codex CLI prompt.
- Preserve raw final notes, runner logs, and all available artifacts.
- Record the exact child prompt, temp vault path, run directory, final note path, logs, exit status, available artifacts, and missing artifacts.
- Map every candidate output to the matching baseline output.

Constraints:
- This workflow-stage agent uses `/goal`; the per-paper child Codex CLI sessions must not use `/goal`.
- Do not batch multiple papers into one Codex CLI session.
- Do not evaluate note quality.
- Do not repair or rewrite generated notes.
- Do not rerun baseline.
- Do not change the paper set unless the baseline manifest is invalid.

Output:
- Write <CANDIDATE_MANIFEST_DOC>.
- The manifest must include candidate identity, runner settings, child Codex CLI prompt template, per-paper exact child prompt, per-paper status, final note paths, artifact paths, logs, exit status, missing artifacts, and baseline/candidate pairing.
- Also write or update machine-readable manifest data under <CANDIDATE_RUN_ROOT> when practical.
```

## Phase 4: Artifact Audit

The Artifact Auditor determines whether the run respected workflow contracts.
It does not evaluate final prose quality.

The auditor should check:

- whether Source Corpus artifacts exist and are internally consistent
- whether `source_manifest.json` and `raw_sections.jsonl` were the canonical
  text-derived reading input
- whether old diagnostic derived views became model-facing writing inputs
- whether acquisition resolve, metadata, fetch, Canonical Identity Artifact, and
  Identity Repair Trace artifacts are present or explicitly missing
- whether the canonical identity provenance points back to the expected resolve
  and metadata artifacts
- whether fetch consumed the canonical identity/source manifestation contract
  instead of reusing loose resolve or metadata identity fields
- whether repaired identity, accepted-with-warnings identity,
  repair-exhausted failure, and equivalent manifestation cases are explained by
  explicit identity verdict, warning, failure class, equivalence, and repair
  trace evidence
- whether truncation or partial reading was explicit
- whether grounding lint used valid section IDs or page ranges
- whether figure/table decisions were fail-closed
- whether final save behavior preserved required files and paths

Artifact audit outcomes:

- `pass`
- `partial`
- `fail`
- `unknown`

Map acquisition identity behavior to these same outcomes using explicit evidence:

- `pass`: resolve, metadata, fetch, canonical identity, and repair trace artifacts
  were consistently reused or consumed; the identity verdict is accepted or
  accepted-with-warnings; any warning is scoped to metadata/provenance; and
  Source Corpus evidence binds to the selected source manifestation.
- `partial`: the run remains safe for note evaluation, but non-blocking
  provenance, warning, or repair trace evidence is incomplete enough to limit
  confidence in the acquisition audit.
- `fail`: identity evidence is contradictory or unsafe, repair-exhausted failure
  did not fail closed before downstream consumption, fetch used a stale or wrong
  identity, the selected PDF/source manifestation is inconsistent, or the trace
  is missing for a repaired identity.
- `unknown`: required acquisition artifacts are absent from the manifest or
  inaccessible, so the auditor cannot determine whether the identity contract
  was respected.

An artifact improvement alone is not the same as final note improvement. It can
support an `architectural_improvement_only` conclusion when final note quality
does not materially improve.

Acquisition identity improvements count as final note-visible improvement only
when the evidence shows they prevented or fixed wrong identity, wrong PDF,
metadata contradiction, missing source evidence, broken path, citation damage,
or a comparable downstream failure. Otherwise they remain
`architectural_improvement_only` even when the acquisition architecture is
cleaner.

### Artifact Auditor Agent Prompt Template

```text
/goal

Goal:
Audit whether the baseline and candidate runs produced complete, contract-respecting artifacts.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- paper set report: <PAPER_SET_DOC>
- baseline manifest: <BASELINE_MANIFEST_DOC>
- candidate manifest: <CANDIDATE_MANIFEST_DOC>

Task:
- Inspect the artifacts listed in both manifests.
- Check Source Corpus, synthesis bundle, grounding, lint, figure/table, and save artifacts.
- Check acquisition resolve, metadata, fetch, canonical identity, and repair trace artifacts.
- Verify whether canonical identity and repair trace evidence were consistently reused or consumed.
- Map identity behavior to pass/partial/fail/unknown with concrete evidence.
- Cover repaired identity, accepted-with-warnings identity, repair-exhausted failure, and equivalent manifestation cases when they appear in the run.
- Record whether candidate artifacts respect the expected contracts.
- Record missing or inconsistent artifacts.
- Distinguish artifact improvements from final note quality improvements.

Constraints:
- Do not judge final prose quality.
- Do not edit notes or artifacts.
- Do not rerun DeepPaperNote.
- Do not infer success from artifact presence alone.

Output:
- Write <ARTIFACT_AUDIT_REPORT>.
- Include one section per primary paper with pass/partial/fail/unknown, evidence paths, identity verdict evidence, source manifestation evidence, repair trace evidence, and risks.
- End with an overall artifact verdict and any blocker for note evaluation.
```

## Phase 5: Note Evaluation

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

### Note Evaluator Agent Prompt Template

```text
/goal

Goal:
Evaluate whether candidate final notes are materially better than baseline final notes.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- <REPO_ROOT>/evals/note-quality-rubric.md
- <REPO_ROOT>/evals/note-evaluator-prompt.md
- paper set report: <PAPER_SET_DOC>
- baseline manifest: <BASELINE_MANIFEST_DOC>
- candidate manifest: <CANDIDATE_MANIFEST_DOC>
- artifact audit report: <ARTIFACT_AUDIT_REPORT>

Task:
- For each primary paper, compare the raw baseline note and raw candidate note.
- Use the fixed rubric hard gates and scored dimensions.
- Use source evidence and artifacts when available.
- Mark evidence-grounded dimensions as lower-confidence when source evidence is missing.
- Identify content improvements, regressions, and ties.

Constraints:
- Do not rewrite or repair notes.
- Do not rerun DeepPaperNote.
- Do not evaluate artifact contract quality except where it affects note quality.
- Do not reward cleaner formatting unless content quality also improves.

Output:
- Write <NOTE_EVALUATION_REPORT>.
- Include the required rubric JSON for each primary paper.
- Add a short per-paper comparison summary and final per-paper verdict.
```

## Phase 6: Regression Judgment

The Regression Judge combines:

- paper set report
- baseline manifest
- candidate manifest
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

For acquisition identity work, keep two fields separate in the regression
summary:

- `architectural_improvement_only`: the candidate improved artifact reuse,
  provenance, canonical identity, repair trace, or reporting clarity, but the
  final notes did not visibly improve.
- `final_note_visible_improvement`: the candidate prevented or fixed wrong
  identity, wrong PDF, metadata contradiction, missing source evidence, broken
  path, citation damage, or a comparable downstream failure visible in the
  generated note or its source evidence.

Do not promote an acquisition architecture improvement into final note quality
improvement merely because resolve, metadata, fetch, canonical identity, or
repair trace artifacts are cleaner or more complete.

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
- architectural_improvement_only versus final note-visible acquisition improvement
- one-paper improvement
- broad real improvement
- failed or inconclusive experiment

### Regression Judge Agent Prompt Template

```text
/goal

Goal:
Decide whether the regression experiment supports claiming a real improvement.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- <REPO_ROOT>/evals/note-quality-rubric.md
- paper set report: <PAPER_SET_DOC>
- baseline manifest: <BASELINE_MANIFEST_DOC>
- candidate manifest: <CANDIDATE_MANIFEST_DOC>
- artifact audit report: <ARTIFACT_AUDIT_REPORT>
- note evaluation report: <NOTE_EVALUATION_REPORT>

Task:
- Check runner success, artifact audit outcomes, and note evaluation verdicts.
- Check whether acquisition identity improvements are architectural_improvement_only or final note-visible.
- Assign a per-paper verdict.
- Assign one experiment-level verdict.
- Decide whether optimization success can be claimed.
- Identify the next recommended action.

Constraints:
- Do not rerun tools.
- Do not edit generated notes.
- Do not override hard-gate failures with average scores.
- Do not claim real improvement for formatting-only gains or one cherry-picked paper.

Output:
- Write <REGRESSION_SUMMARY_DOC>.
- Include experiment id, baseline version, candidate version, paper list, runner settings summary, artifact audit summary, note evaluation summary, per-paper verdicts, experiment-level verdict, and next recommended action.
```
