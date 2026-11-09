# DeepPaperNote Note Evaluation Rubric v3

Status: v3
Audience: evaluation agents
Scope: final DeepPaperNote Markdown notes after generation

This rubric is for evaluating finished notes. It is not a writing reference for the
DeepPaperNote note-generation workflow, and it must not be used to rewrite,
repair, or complete the note under evaluation.

v3 changes from v2: the paper type sets what the note must cover. H5 checks the analytical surface of the paper's type; D2 judges how clearly the note explains the paper's mechanism or flow; D8 adds plain language and term explanation; D9 (core question coverage) and D10 (narrative and logic) are new; the weights are rebalanced to make room for them.

## Evaluator Role

The evaluation agent judges finished outputs. It must:

- compare raw generated notes as they are
- keep both notes unmodified
- cite concrete evidence for every material judgment
- separate hard failures from score differences
- judge content wherever it appears: section names, layout, and length earn nothing by themselves

The evaluation agent must not:

- generate a replacement note
- patch missing sections
- add citations or images
- guess which note comes from which version, or let such a guess affect a judgment
- collapse the result into one scalar score without recording the failure mode

## Required Inputs

For one pair, the evaluator receives:

- the pair id
- the paper title and stable identity evidence, such as DOI, arXiv ID, venue, or PDF path
- the output language of both notes
- the paper type and its core questions: the expected `paper_type` and the id and wording of each core question for that type, identical for both notes
- note A and note B
- available source evidence for each note, preferably `source_manifest.json` and `raw_sections.jsonl`
- available run artifacts for each note, such as `synthesis_bundle.json`, note plan JSON, grounding lint output, figure/table decisions, and note lint output

The experimenter takes the core questions from `core_questions` of that type in `skills/deeppapernote/scripts/type_profiles.py` at the candidate commit, in the notes' output language. The evaluator never receives which note is the baseline, commit ids, run manifests, or timestamps.

If source evidence is unavailable, the evaluator may still compare note readability
and structure, but it must mark evidence-grounded dimensions as low-confidence.

## Evaluation Order

1. Run the hard gates on each note.
2. Check each core question against each note.
3. Score note A and note B independently.
4. Perform the pairwise comparison.
5. Emit the required JSON report.

Hard gates override numeric scores. A note that fails a severe hard gate cannot
win the comparison on its scores alone.

## Paper Type

The paper type decides what a complete note covers. Read every dimension through it:

| `paper_type` | The paper's core (D2) | Its results (D3) |
| --- | --- | --- |
| `method` | the mechanism and its pipeline | experiments against baselines, ablations |
| `system` | the design, its trade-offs, and the request or data path | measured performance under the workloads |
| `theory` | the assumptions and the proof idea | the theorems and the conditions they hold under |
| `position` | the stance and the argument for it | the conclusions argued and the evidence offered |
| `benchmark_or_dataset` | the construction pipeline and the evaluation protocol | model results and what they reveal |
| `discovery_empirical` | the hypotheses and the experiment design | the findings and what they rule out |
| `human_subjects_empirical` | the study design, participants, and measures | effects with their uncertainty |
| `survey_or_review` | the scope, the search, and the taxonomy | the consensus, disagreements, and gaps found |
| `qualitative_empirical` | the sampling and the analysis process | the themes and the material behind them |
| `humanities_argument` | the claim and the argument's structure | the conclusions and their qualifications |

Numbers matter where the paper reports them. A note on a paper without experiments is not penalized for having few numbers.

## Core Questions

Each core question is one check per note, recorded in the JSON as one of:

- `answered`: the note answers it specifically for this paper, and the answer is traceable to the paper. The answer may sit in any section, under any heading.
- `not_reported_stated`: the paper does not report it, and the note says so ("论文没有报告 X" / "The paper does not report X").
- `missing`: the note does not address it, or answers it only with generic text that would fit any paper.
- `misframed`: the note answers it, but the answer contradicts the paper, invents what the paper does not report, turns an unreported item into a fault ("the authors did not do X"), or adds a score or a low/high rating.

A `misframed` answer that misstates a central point also fails H2 or H4.

## Hard Gates

Each hard gate is `pass`, `fail`, or `unknown`.

Use `unknown` only when required evidence is unavailable. Do not use `unknown`
to soften a visible failure.

### H1. Paper Identity Is Valid

Fail if the note appears to summarize the wrong paper, mixes two papers, invents
metadata, or uses a title/DOI/arXiv identity that conflicts with the supplied
source evidence.

### H2. No Major Factual Error

Fail if the note states a central method, dataset, result, limitation, or claim
in a way that contradicts the paper or source artifacts.

### H3. Central Claims Are Grounded

Fail if central claims are not traceable to source sections, pages, tables,
figures, or supplied artifacts.

### H4. Claim Boundaries Are Honest

Fail if the note presents unproven, unvalidated, or speculative claims as proven
paper conclusions.

### H5. Core Analytical Surface Exists

Fail if the note is missing the analytical surface its paper type needs: the
problem the paper addresses, the paper's core as the Paper Type table describes it,
its results, limitations, and reusable takeaways. Judge by content, not by section
names.

### H6. No Degraded-Source Pretending

Fail if the note claims full-paper analysis while the available artifacts show
truncation, insufficient evidence, missing PDF text, or partial reading that was
not explicitly acknowledged.

### H7. Figure, Table, Citation, And Path Behavior Is Not Broken

Fail if broken image embeds, invalid local paths, incorrect figure/table identity,
or misleading citation links materially damage the note.

### H8. Final Note Is Readable In Its Output Language

Fail if the note contains raw extraction fragments, broken paragraph flow, or
substantial prose in a language other than its output language:

- `zh-CN`: English clauses where natural Chinese analysis is expected.
- `en`: Chinese prose anywhere outside citation metadata, such as a Chinese title
  or author list.

Stable proper nouns, model names, datasets, metrics, code tokens, URLs, DOI
strings, and paper figure IDs may stay in their original form in either language.

## Scored Dimensions

Score each dimension from 0 to 5, then apply the listed weight. Use half-points
only when the evidence genuinely falls between anchors.

### D1. Evidence Chain Coverage

Weight: 15

- 0: The note mostly repeats the abstract or introduction.
- 1: It mentions the paper's topic but misses the main evidence chain.
- 2: It covers some problem/core/result pieces but leaves major links unclear.
- 3: It reconstructs the basic claim-to-evidence chain with some omissions.
- 4: It covers the central claims, supporting evidence, and main interpretation.
- 5: It clearly explains the full evidence chain, including what each result does
  and does not prove.

### D2. Mechanism Or Flow Clarity

Weight: 15

Judge the paper's core as the Paper Type table describes it.

- 0: No explanation of the paper's core.
- 1: Names stages, components, or arguments without explaining how they work.
- 2: Gives a rough flow, but the order, the inputs and outputs, or the logic
  between steps stays unclear, or the explanation is buried in jargon.
- 3: The main flow is clear, but a key step, or which step is new in this paper,
  stays unclear.
- 4: Each key step's input, operation, and output is clear, what is new is marked,
  and design choices are tied to the results.
- 5: A researcher from an adjacent field could re-explain the flow and why each key
  step is there, and a specialist finds the details needed to compare or partially
  reproduce it.

### D3. Results, Settings, And Numbers

Weight: 10

Judge the paper's results as the Paper Type table describes them.

- 0: Omits the key results.
- 1: Mentions results only qualitatively, where the paper gives specifics.
- 2: Includes some results but not the settings, baselines, conditions, or
  metrics needed to interpret them.
- 3: Covers the main results and their settings with minor omissions.
- 4: Explains the most important comparisons, settings, conditions, and result
  patterns.
- 5: Selects the meaningful results, interprets them correctly, and avoids
  over-weighting decorative or weak numbers.

### D4. Claim Boundaries And Limitations

Weight: 10

- 0: No real limitations or claim boundaries.
- 1: Uses generic limitations that could apply to any paper.
- 2: Mentions limitations but does not connect them to the paper's evidence.
- 3: Identifies real constraints, missing evidence, or weak settings.
- 4: Separates proven from unproven claims and explains limiting evidence.
- 5: Mechanistically explains what the paper does not prove and how that should
  change interpretation or reuse.

### D5. Comparative Positioning And Novelty

Weight: 5

- 0: No positioning or novelty judgment.
- 1: Says the work is novel or important without locating why.
- 2: Mentions prior work or baselines shallowly.
- 3: Explains how the paper differs from a baseline, prior route, or obvious
  alternative.
- 4: Connects novelty to concrete capability, evidence, or evaluation change.
- 5: Gives a precise, evidence-backed judgment of the paper's actual
  contribution and where it is or is not differentiated.

### D6. Reusable Research Or Engineering Takeaways

Weight: 10

- 0: No reusable takeaway.
- 1: Takeaways are generic praise or vague future work.
- 2: Gives broad lessons but not enough detail to reuse.
- 3: Provides paper-specific research, engineering, replication, or validity
  takeaways.
- 4: Takeaways are tied to mechanisms, results, limitations, or follow-up checks.
- 5: A future reader could use the takeaways to guide implementation,
  reproduction, comparison, or research planning.

Score mainly from the Takeaways section (`阅读收获` / `Takeaways`): a transferable
idea that names the paper's mechanism, its transfer target, and the precondition,
plus a follow-up question or experiment specific to the paper, supports a 4 or 5.
Do not score the user-owned My Notes section (`我的笔记` / `My Notes`); in a
generated note it holds only the standard guidance.

### D7. Obsidian Note Usability

Weight: 5

- 0: Broken Markdown, metadata, paths, or structure make the note hard to use.
- 1: Major navigation or formatting problems.
- 2: Usable but rough; important sections or embeds are hard to navigate.
- 3: Stable structure and metadata with minor issues.
- 4: Clear Obsidian-friendly layout, links, figures, and sections.
- 5: Excellent long-term vault usability without sacrificing technical depth.

### D8. Language, Plainness, And Readability

Weight: 10

The reader is a smart researcher from an adjacent field. Plain prose leads each
paragraph with its conclusion, explains a term in one plain sentence where it first
appears, keeps one point per paragraph, and keeps only the numbers that carry a
conclusion in the prose. Formulas and implementation detail belong to `method`,
`system`, and `theory` notes.

- 0: Hard to read, raw extraction-like, or heavily mixed-language.
- 1: Frequent awkward phrasing, stiff literal translation, or prose left in
  another language.
- 2: Understandable, but dense: terms go unexplained, or conclusions are buried
  under detail.
- 3: Mostly fluent in the output language; a few terms go unexplained or a few
  paragraphs run several points together.
- 4: Clear, natural prose; terms are explained where they first appear, and
  paragraphs lead with their point.
- 5: An adjacent-field reader follows every paragraph on one read, with no loss of
  technical precision or faithfulness to the paper.

### D9. Core Question Coverage

Weight: 10

Score from the core question checks.

- 0: Most core questions are `missing`.
- 1: A few are `answered`; most are `missing` or `misframed`.
- 2: About half are `answered` or `not_reported_stated`.
- 3: Most are `answered` or `not_reported_stated`; one or two are `missing`, or
  answers are thin.
- 4: Every question is `answered` or `not_reported_stated`, with no `misframed`
  item; a few answers are thin.
- 5: Every question is answered precisely with evidence, and every unreported item
  that limits a conclusion is carried into the limitations.

Any `misframed` item caps the score at 3.

### D10. Narrative And Logic

Weight: 10

The narrative is the paper's own story: what problem it takes on, what it does
about it, what the evidence shows, and where the conclusion stops.

- 0: A list of disconnected facts.
- 1: Sections stand alone; the reader cannot tell what the paper's story is.
- 2: The story is stated at the top, but the sections drift from it, or paragraphs
  sit outside it.
- 3: A throughline is visible and most sections connect to it, with some detours.
- 4: Each section advances one story, and the reader can tell why each section
  follows the one before.
- 5: An adjacent-field reader could retell the paper's argument after one read; the
  summary at the top, the body, the limitations, and the takeaways agree.

## Weighted Score

For each dimension:

`weighted_points = score / 5 * weight`

The weights sum to 100, so the maximum total is 100.

Scores are secondary. A high numeric score does not override a hard-gate failure.

## Pairwise Comparison

Evaluate both notes before comparing them. Then assign one of:

- `a_wins`
- `b_wins`
- `tie`
- `mixed`

Prefer `mixed` when one note is better on some content dimensions but worse on
hard gates, factuality, grounding, or important usability.

Set `material_difference` to true only when the difference would change what a
reader learns about the paper, not when it is cosmetic, a matter of length, or
formatting alone. For each material difference, record the dimension, which note
is better, and the evidence.

The evaluator does not decide whether a change improved DeepPaperNote. The
Regression Judge in `evals/regression-workflow.md` unblinds the pairs, compares
them against the noise between two baseline runs, and assigns the improvement
verdict.

## Required JSON Output

The evaluator must emit a JSON object with this shape. `core_questions` holds one
entry per supplied question id, in the supplied order.

```json
{
  "rubric_version": "v3",
  "pair_id": "",
  "paper_id": "",
  "paper_title": "",
  "paper_type": "",
  "output_language": "zh-CN|en",
  "evidence_confidence": "high|medium|low",
  "note_a": {
    "hard_gates": {
      "paper_identity_valid": {"status": "pass|fail|unknown", "evidence": ""},
      "no_major_factual_error": {"status": "pass|fail|unknown", "evidence": ""},
      "central_claims_grounded": {"status": "pass|fail|unknown", "evidence": ""},
      "claim_boundaries_honest": {"status": "pass|fail|unknown", "evidence": ""},
      "core_analytical_surface_exists": {"status": "pass|fail|unknown", "evidence": ""},
      "no_degraded_source_pretending": {"status": "pass|fail|unknown", "evidence": ""},
      "figure_table_citation_paths_not_broken": {"status": "pass|fail|unknown", "evidence": ""},
      "readable_in_output_language": {"status": "pass|fail|unknown", "evidence": ""}
    },
    "core_questions": [
      {"id": "", "status": "answered|not_reported_stated|missing|misframed", "evidence": ""}
    ],
    "scores": {
      "evidence_chain_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "mechanism_flow_clarity": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "results_settings_numbers": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "claim_boundaries_limitations": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "comparative_positioning_novelty": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "reusable_takeaways": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "obsidian_usability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "plain_language_readability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "core_question_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "narrative_logic": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""}
    },
    "total_score": 0
  },
  "note_b": {
    "hard_gates": {
      "paper_identity_valid": {"status": "pass|fail|unknown", "evidence": ""},
      "no_major_factual_error": {"status": "pass|fail|unknown", "evidence": ""},
      "central_claims_grounded": {"status": "pass|fail|unknown", "evidence": ""},
      "claim_boundaries_honest": {"status": "pass|fail|unknown", "evidence": ""},
      "core_analytical_surface_exists": {"status": "pass|fail|unknown", "evidence": ""},
      "no_degraded_source_pretending": {"status": "pass|fail|unknown", "evidence": ""},
      "figure_table_citation_paths_not_broken": {"status": "pass|fail|unknown", "evidence": ""},
      "readable_in_output_language": {"status": "pass|fail|unknown", "evidence": ""}
    },
    "core_questions": [
      {"id": "", "status": "answered|not_reported_stated|missing|misframed", "evidence": ""}
    ],
    "scores": {
      "evidence_chain_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "mechanism_flow_clarity": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "results_settings_numbers": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "claim_boundaries_limitations": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "comparative_positioning_novelty": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "reusable_takeaways": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "obsidian_usability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "plain_language_readability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "core_question_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "narrative_logic": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""}
    },
    "total_score": 0
  },
  "pairwise_result": {
    "winner": "a_wins|b_wins|tie|mixed",
    "material_difference": true,
    "difference_summary": "",
    "differences": [
      {"dimension": "", "better": "a|b", "evidence": ""}
    ]
  }
}
```

The JSON may be followed by a short human-readable summary, but the JSON is the
source of truth for automated comparison.
