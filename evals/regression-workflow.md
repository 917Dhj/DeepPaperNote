# DeepPaperNote Regression Workflow

Status: v2
Audience: agents that run or review DeepPaperNote evaluation experiments
Scope: checking a change against real papers, from a smoke run to a full note-quality regression

This file is canonical. `evals/regression-workflow-zh.md` is its Chinese translation; when they disagree, this file wins and the translation is fixed.

The scoring rubric lives in `evals/note-quality-rubric.md` (v2). The note evaluator's prompt template lives in `evals/note-evaluator-prompt.md`.

## Choose A Tier

| Tier | Use it when | What it shows |
| --- | --- | --- |
| Deterministic | every pull request | `python3 -m pytest -q`; add `python3 -m pytest -q -m corpus` when extraction or figure selection changes (`evals/paper-corpus.md`) |
| Smoke | `SKILL.md`, a reference, or the stage order changes | the workflow still completes on real papers |
| Full | you want to claim that final notes got better | whether the candidate's notes beat the baseline's beyond run-to-run noise |

A smoke pass never supports a quality claim. Only a full run can end in `real_improvement`.

## Core Principles

- An experiment compares raw generated output under controlled conditions. Nobody edits, completes, or polishes a note before it is evaluated.
- The agent that generates a note never evaluates it.
- The evaluator is blind: it sees two notes as A and B and never learns which is the baseline.
- One run per arm is not evidence. Generation is stochastic, so a full run measures the noise between two baseline runs and counts only differences larger than that.

## Controlled Variables

Hold these fixed across every run of one experiment, and record them in the manifests:

- **Baseline and candidate commits.** The baseline is the parent of the change under test: the commit before the change, or, for a pull request, its merge base with `develop`. Never use `main` as the baseline unless `main` is that commit; it can lag `develop` by many merges and would mix their effects into the result.
- **Host and model.** One host per experiment, Codex CLI by default, with the same model and reasoning settings. A change to `SKILL.md` runs the smoke tier on every host it targets.
- **Paper set and PDF bytes.** Use the fixed set below and check each PDF's SHA-256 against `evals/expectations/<paper>.json` before running.
- **Input mode and child prompt.** See Child Prompt.
- **Run configuration.** Give every run its own configuration file, so no user configuration, shell profile, or earlier preference leaks in. Write `<RUN_DIR>/config.json`:

  ```json
  {
    "output_language": "<OUTPUT_LANGUAGE>",
    "save_mode": "obsidian",
    "obsidian_vault": "<TEMP_VAULT_PATH>",
    "papers_dir": "Papers"
  }
  ```

  `<OUTPUT_LANGUAGE>` is `zh-CN` unless the experiment says otherwise, and `<TEMP_VAULT_PATH>` is an absolute path to an existing empty directory. Start the child session with `DEEPPAPERNOTE_CONFIG_PATH=<RUN_DIR>/config.json` and `DEEPPAPERNOTE_DISABLE_SHELL_CONFIG=1`, and with no other `DEEPPAPERNOTE_` variable set.

- **Isolation.** Each run gets its own run directory and temporary vault. Runs that share an installed skill directory never run concurrently.
- **Rubric version.** Every evaluation in one experiment uses the same rubric version.

## Paper Set

Use this fixed set from `evals/papers/`. The PDFs are local and ignored by Git; their hashes are committed in `evals/expectations/`.

| Role | Paper | Stress points |
| --- | --- | --- |
| primary | `arxiv-sam` | method plus dataset, figure- and table-heavy, appendix, heavy Visual Review |
| primary | `tacl-lost-middle` | evaluation paper, many figures, conclusions bounded by limitations |
| primary | `osdi-distserve` | systems paper, algorithms, comparison tables |
| primary | `ncomms-medsam` | journal layout, medical domain, full-width captions |
| spare | `arxiv-transformer` | short mechanism paper |
| spare | `zh-aptamer-review` | Chinese review article |

The smoke tier uses `arxiv-transformer` and `arxiv-sam`. Replace a primary paper with a spare only when its run cannot start for a reason unrelated to the change, and record why.

To extend the set, a Paper Finder agent picks papers with stable identity, a readable PDF, enough technical depth for a deep note, and a stress point the set lacks: benchmark or evaluation, method or system, appendix-heavy, figure- or table-heavy, or limitations-heavy. Each new paper gets an `evals/expectations/` entry as `evals/paper-corpus.md` describes before an experiment uses it.

## Child Prompt

Each run starts one independent child session with exactly one prompt and nothing else: no extra constraint, explanation, source path, agent instruction, model note, prefix, or suffix. Child sessions do not use `/goal`; the workflow agents below do. Never run two papers in one child session.

| Input mode | Use it for | Prompt |
| --- | --- | --- |
| PDF (default) | every note-quality comparison | `给这篇论文生成一个深度笔记：<PDF_PATH>。笔记保存到<TEMP_VAULT_PATH>中。` |
| Title | changes to resolve, metadata, fetch, or identity | `给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。` |

PDF mode feeds both arms the same bytes and skips the Zotero lookup. Title mode exercises acquisition end to end, so its result also depends on the network and on whether Zotero is running; record both. Both arms of one experiment use the same mode. Record the exact prompt of every run.

## Run Record

After each child session ends, the runner saves, under that run directory:

- the raw final note and every artifact the run wrote
- the child prompt, logs, and exit status
- `status-bindings.json`, which names the run's admission, note plan, draft, lint, review, and save files and its run context, in the format of `<SKILL_ROOT>/references/run-state.md`. These files have no fixed names, so a status query without bindings reports those stages as `missing` and `summary.saved_verified` as false even for a finished run. Reuse the bindings file the child wrote when its paths match the files in `<RUN_WORKDIR>`; otherwise write one from those files and the run configuration.
- `run_state.json`, the output of `python3 <SKILL_ROOT>/scripts/run_state.py status --workdir <RUN_WORKDIR> --prefix <RUN_PREFIX> --bindings <RUN_DIR>/status-bindings.json`. It records which stages passed, stale artifacts, provenance gaps, and the `summary` the final report uses. When the child chose its own work directory, take `<RUN_WORKDIR>` from the `workdir=` line in its log.

A run counts as **complete** when `run_state.json` shows every required stage passed, `summary.saved_verified` is true, and `summary.saved_sha256_match` is true.

## Smoke Tier

1. Run the candidate on the two smoke papers in PDF mode, once each, on every host the change targets.
2. Keep each Run Record.
3. One reviewer, human or agent, reads each note against hard gates H1 to H8 of the rubric. It scores nothing and compares nothing.
4. Write `smoke-report.md`: per run, the host, completion per `run_state.json`, any `next_action` or provenance gap, and each hard gate with one line of evidence.

The smoke tier passes when every run is complete and every hard gate passes. Report it as "the workflow still completes", never as a quality result.

## Full Tier

### Roles

Each role can be its own session or a clearly isolated phase:

- **Baseline Runner:** records the baseline identity, then runs the baseline. It does not judge quality.
- **Candidate Runner:** runs the candidate on the same set, then builds the blinded pairs. It does not judge quality.
- **Artifact Auditor:** checks each run against the workflow contract. It does not judge prose.
- **Note Evaluator:** scores blinded pairs with the rubric. It never sees manifests, arms, or commits.
- **Regression Judge:** unblinds the pairs and gives the verdict.

Every agent reads the previous phase's document and writes its own for the next one. Prompts use placeholders, not local paths:

```text
baseline-run-manifest.md
  -> candidate-run-manifest.md + evaluation-pairs.md + blinding-map.json (sealed)
  -> artifact-audit-report.md
  -> note-evaluation-report.md
  -> regression-summary.md
```

### Runs

Run each primary paper twice per arm, in fresh child sessions: four papers times two arms times two runs makes 16 runs. Name run directories with neutral ids such as `run-07`, so a path never reveals its arm; the manifests map ids to arms.

Reuse earlier baseline runs only when the commit, host, model, paper set, input mode, child prompt, and run configuration all match.

### Blinded Pairs

After every run is recorded, the Candidate Runner builds three pairs per paper:

| Pair | Compares | Purpose |
| --- | --- | --- |
| noise | baseline run 1 and baseline run 2 | how much two runs of the same version differ |
| comparison 1 | baseline run 1 and candidate run 1 | |
| comparison 2 | baseline run 2 and candidate run 2 | |

For each pair it randomly assigns which run is A, gives the pair a neutral id, shuffles all pairs together, and writes:

- `evaluation-pairs.md`: per pair, its id, the paper, and the note, source evidence, and artifact root of A and of B
- `blinding-map.json`: per pair, its kind and which run and arm is A and B. Only the Regression Judge reads it.

### Artifact Audit

The auditor starts from each run's `run_state.json` and records its stage results, stale artifacts, and provenance gaps. It then checks what the script cannot judge:

- the accepted identity matches the paper in the PDF: title, authors, and identifier
- Visual Review decisions are plausible: main method and main result figures are not left out or dropped, and each drop gives an editorial reason
- the note's embeds match the frozen decisions, and inserted images exist in the paper-local `images/` directory
- truncation or partial reading is stated in the note when the source manifest records it
- Grounding Lint cites valid section IDs or page ranges for the central claims

Each run gets `pass`, `partial`, `fail`, or `unknown`:

- `pass`: every required stage passed and the checks above hold.
- `partial`: the run completed, but a provenance, warning, or repair trace gap lowers confidence in the audit.
- `fail`: a required stage failed, a check above fails, or identity evidence is contradictory or unsafe.
- `unknown`: required artifacts are missing or unreadable, so the auditor cannot decide.

For title-mode experiments, the auditor also maps acquisition identity behavior to these results with explicit evidence:

- `pass`: the resolve, metadata, fetch, canonical identity, and repair trace artifacts are reused and consumed consistently; the identity verdict is accepted or accepted-with-warnings; warnings are limited to metadata or provenance; and Source Corpus evidence is bound to the selected source manifestation.
- `partial`: the run can still be evaluated, but non-blocking provenance, warning, or repair trace evidence is incomplete.
- `fail`: identity evidence is contradictory or unsafe; a repair-exhausted failure did not fail closed before downstream consumption; fetch used a stale or wrong identity; the selected PDF or source manifestation is inconsistent; or a repaired identity lacks its trace.
- `unknown`: required acquisition artifacts are missing or unreadable.

Cover the repaired identity, accepted-with-warnings identity, repair-exhausted failure, and equivalent manifestation scenarios whenever a run produces them.

An artifact improvement is not a final-note improvement. An acquisition identity improvement counts as note-visible only when the evidence shows it prevents or fixes a wrong identity, wrong PDF, metadata contradiction, missing source evidence, broken path, citation damage, or a comparable downstream failure. Otherwise it supports only `architectural_improvement_only`.

### Note Evaluation

The Note Evaluator evaluates every pair in `evaluation-pairs.md` with `evals/note-evaluator-prompt.md` and `evals/note-quality-rubric.md`, one pair at a time and preferably in a fresh session per pair. It reads only those three files and the paths each pair names, never the manifests, `blinding-map.json`, Git history, or file timestamps. It writes one rubric JSON report per pair into `note-evaluation-report.md`.

### Regression Judgment

The Regression Judge reads every document above, including `blinding-map.json`, and unblinds each pair.

Per paper and per rubric dimension:

- The **noise margin** is the absolute score difference in the noise pair.
- The candidate **improves** a dimension when it scores higher in both comparison pairs and each gain exceeds the noise margin.
- The candidate **regresses** on a dimension when it scores lower in both comparison pairs and each loss exceeds the noise margin.
- Anything else is noise.

Per paper, assign one verdict:

- `hard_fail`: a candidate note fails a hard gate that its baseline counterpart in the same pair passes.
- `regression`: the candidate regresses on a core content dimension (D1 to D4) and improves on none.
- `no_material_change`: every difference is noise.
- `partial_improvement`: the candidate improves some dimensions, but not D1 or D2, or it also regresses on one.
- `real_improvement`: the candidate improves D1 or D2, does not regress on D4, introduces no hard-gate failure, and the evaluator's reasons tie the gain to paper evidence rather than formatting.

The experiment's verdict is one of `hard_fail`, `regression`, `no_material_change`, `partial_improvement`, `real_improvement`, or `architectural_improvement_only`:

- `hard_fail` when any paper is `hard_fail`.
- `real_improvement` only when at least three of the four papers are `real_improvement` and none is `regression`.
- `architectural_improvement_only` when artifacts or contracts improved but no paper shows more than `no_material_change`.
- Otherwise, the verdict that best describes the per-paper results, with the reason.

None of these is a real improvement: prettier formatting, a longer note with the same evidence coverage, more sections without better mechanism or result explanation, cleaner artifacts with unchanged notes, or a gain on one paper alongside a serious regression on another.

For acquisition identity work, record two fields separately:

- `architectural_improvement_only`: the candidate improved artifact reuse, provenance, canonical identity, repair trace, or reporting clarity, but final notes show no visible quality gain.
- `final_note_visible_improvement`: the candidate prevented or fixed a wrong identity, wrong PDF, metadata contradiction, missing source evidence, broken path, citation damage, or a comparable downstream failure that shows in the generated notes or source evidence.

### Experiment Summary

`regression-summary.md` records the experiment id, baseline and candidate commits, host and model, input mode, paper set, run configuration, the completion and audit result of each run, the noise margins, each per-paper verdict with its deciding dimensions, the experiment verdict, whether an optimization success can be claimed, and the next recommended action. It keeps apart a mechanism gain without a note gain, a note gain with an artifact regression, architectural versus note-visible acquisition gains, and an inconclusive experiment.

## Agent Prompt Templates

Every workflow agent starts in goal mode, so each template begins with `/goal`.

### Baseline Runner

```text
/goal

Goal:
Run the frozen baseline of DeepPaperNote on the fixed paper set and write a complete baseline manifest.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- baseline commit: <BASELINE_COMMIT>
- experiment settings: <TIER>, <HOST_AND_MODEL>, <INPUT_MODE>, <OUTPUT_LANGUAGE>

Tasks:
- Record the baseline identity, host, model, input mode, and run configuration before any run.
- Check each PDF's SHA-256 against evals/expectations.
- Install or sync the baseline skill.
- Run each primary paper twice, each run in its own child session with its own neutral run id, run directory, temporary vault, and the process environment from Controlled Variables.
- Give each child session only the child prompt for the input mode, with placeholders replaced.
- Save the Run Record of every run, including run_state.json.

Constraints:
- Do not evaluate, edit, or rewrite any note.
- Do not run candidate code or change the paper set.

Output:
- Write <BASELINE_MANIFEST_DOC>: baseline identity, settings, and per run its id, paper, exact prompt, run directory, vault, note path, exit status, completion per run_state.json, and missing artifacts.
```

### Candidate Runner

```text
/goal

Goal:
Run the candidate on the same set and settings as the baseline, then build the blinded evaluation pairs.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- <BASELINE_MANIFEST_DOC>
- candidate commit: <CANDIDATE_COMMIT>

Tasks:
- Confirm that the paper set, host, model, input mode, child prompt, and run configuration match the baseline manifest.
- Install or sync the candidate skill.
- Run each primary paper twice, exactly as the baseline did, with new neutral run ids.
- Save the Run Record of every run, including run_state.json.
- Build the three pairs per paper, randomize A and B, shuffle the pairs, and write evaluation-pairs.md and blinding-map.json.

Constraints:
- Do not evaluate, edit, or rewrite any note.
- Do not rerun the baseline. Change the paper set only if the baseline manifest is invalid.

Output:
- Write <CANDIDATE_MANIFEST_DOC> in the baseline manifest's format, plus <EVALUATION_PAIRS_DOC> and <BLINDING_MAP_PATH>.
```

### Artifact Auditor

```text
/goal

Goal:
Check every baseline and candidate run against the workflow contract.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- <BASELINE_MANIFEST_DOC>
- <CANDIDATE_MANIFEST_DOC>

Tasks:
- Start from each run's run_state.json: stage results, stale artifacts, provenance gaps.
- Run the checks in the Artifact Audit section that the script cannot judge.
- For title mode, map acquisition identity behavior to pass, partial, fail, or unknown with explicit evidence, covering every identity scenario the runs produced.
- Separate artifact improvements from final-note improvements.

Constraints:
- Do not judge prose quality.
- Do not edit notes or artifacts, and do not rerun DeepPaperNote.
- Do not infer success from the mere presence of an artifact.

Output:
- Write <ARTIFACT_AUDIT_REPORT>: per run its result, evidence paths, and risks; then an overall verdict and whether any problem blocks note evaluation.
```

### Note Evaluator

Use the template in `evals/note-evaluator-prompt.md`, once per pair.

### Regression Judge

```text
/goal

Goal:
Decide whether this experiment supports claiming a real improvement.

Read first:
- <REPO_ROOT>/evals/regression-workflow.md
- <REPO_ROOT>/evals/note-quality-rubric.md
- <BASELINE_MANIFEST_DOC>, <CANDIDATE_MANIFEST_DOC>
- <ARTIFACT_AUDIT_REPORT>
- <NOTE_EVALUATION_REPORT>
- <BLINDING_MAP_PATH>

Tasks:
- Unblind every pair.
- Compute each paper's noise margins, then apply the Regression Judgment rules per dimension and per paper.
- Decide whether acquisition identity gains are architectural only or note-visible.
- Give the experiment verdict and the next recommended action.

Constraints:
- Do not rerun tools or edit notes.
- Do not let an average score override a hard-gate failure.
- Do not claim a real improvement from formatting-only gains or a single paper.

Output:
- Write <REGRESSION_SUMMARY_DOC> as the Experiment Summary section describes.
```
