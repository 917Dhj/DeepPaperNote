# DeepPaperNote Note Evaluation Rubric v1

Status: v1 stable
Audience: evaluation agents
Scope: final DeepPaperNote Markdown notes after generation

This rubric is for evaluating finished notes. It is not a writing reference for the
DeepPaperNote note-generation workflow, and it must not be used to rewrite,
repair, or complete the note under evaluation.

## Evaluator Role

The evaluation agent judges finished outputs. It must:

- compare raw generated notes as they are
- keep baseline and candidate notes unmodified
- cite concrete evidence for every material judgment
- separate hard failures from score differences
- avoid rewarding a note only because it is longer, cleaner, or more polished

The evaluation agent must not:

- generate a replacement note
- patch missing sections
- add citations or images
- infer that a candidate improved simply because it came from a newer run
- collapse the result into one scalar score without recording the failure mode

## Required Inputs

For a single-paper evaluation, the evaluator should receive:

- the paper title and stable identity evidence, such as DOI, arXiv ID, venue, or PDF path
- the baseline final note
- the candidate final note
- available source evidence, preferably `source_manifest.json` and `raw_sections.jsonl`
- available run artifacts, such as `synthesis_bundle.json`, note plan JSON, grounding lint output, figure/table decisions, and note lint output

If source evidence is unavailable, the evaluator may still compare note readability
and structure, but it must mark evidence-grounded dimensions as low-confidence.

## Evaluation Order

1. Run hard gates.
2. Score baseline and candidate independently.
3. Perform pairwise comparison.
4. Assign the final verdict.
5. Emit the required JSON report.

Hard gates override numeric scores. A note with a severe hard-gate failure cannot
be treated as a real improvement, even if it scores well on some dimensions.

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

### H5. Core Analytical Sections Exist

Fail if the note is missing the core analytical surface needed for a deep note:
research problem, data/task definition, method or analysis flow, key results,
limitations, and reusable takeaways.

### H6. No Degraded-Source Pretending

Fail if the note claims full-paper analysis while the available artifacts show
truncation, insufficient evidence, missing PDF text, or partial reading that was
not explicitly acknowledged.

### H7. Figure, Table, Citation, And Path Behavior Is Not Broken

Fail if broken image embeds, invalid local paths, incorrect figure/table identity,
or misleading citation links materially damage the note.

### H8. Final Note Is Readable Chinese

Fail if the note contains substantial mixed-language prose, raw extraction
fragments, broken paragraph flow, or English clauses where natural Chinese
analysis is expected. Stable proper nouns, model names, datasets, metrics, code
tokens, URLs, DOI strings, and paper figure IDs may remain in English.

## Scored Dimensions

Score each dimension from 0 to 5, then apply the listed weight. Use half-points
only when the evidence genuinely falls between anchors.

### D1. Evidence Chain Coverage

Weight: 20

- 0: The note mostly repeats the abstract or introduction.
- 1: It mentions the paper's topic but misses the main evidence chain.
- 2: It covers some problem/method/result pieces but leaves major links unclear.
- 3: It reconstructs the basic claim-to-evidence chain with some omissions.
- 4: It covers the central claims, supporting evidence, and main interpretation.
- 5: It clearly explains the full evidence chain, including what each result does
  and does not prove.

### D2. Mechanism Or Protocol Depth

Weight: 20

- 0: No mechanism or protocol explanation.
- 1: Names methods, datasets, or stages without explaining how they work.
- 2: Gives a rough flow but misses key inputs, transformations, or outputs.
- 3: Explains the main mechanism or protocol but lacks important training,
  inference, evaluation, formula, or implementation details.
- 4: Connects mechanism or protocol choices to the observed result pattern.
- 5: Provides replication-grade explanation that a technical reader could reuse
  to re-explain, compare, or partially reproduce the paper.

### D3. Results, Settings, And Numbers

Weight: 15

- 0: Omits the key results.
- 1: Mentions results only qualitatively.
- 2: Includes some numbers but not the settings, baselines, or metrics needed to
  interpret them.
- 3: Covers the main numbers and settings with minor omissions.
- 4: Explains the most important comparisons, settings, metrics, and result
  patterns.
- 5: Selects the meaningful results, interprets them correctly, and avoids
  over-weighting decorative or weak numbers.

### D4. Claim Boundaries And Limitations

Weight: 15

- 0: No real limitations or claim boundaries.
- 1: Uses generic limitations that could apply to any paper.
- 2: Mentions limitations but does not connect them to the paper's evidence.
- 3: Identifies real constraints, missing evidence, or weak settings.
- 4: Separates proven from unproven claims and explains limiting evidence.
- 5: Mechanistically explains what the paper does not prove and how that should
  change interpretation or reuse.

### D5. Comparative Positioning And Novelty

Weight: 10

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

### D7. Obsidian Note Usability

Weight: 5

- 0: Broken Markdown, metadata, paths, or structure make the note hard to use.
- 1: Major navigation or formatting problems.
- 2: Usable but rough; important sections or embeds are hard to navigate.
- 3: Stable structure and metadata with minor issues.
- 4: Clear Obsidian-friendly layout, links, figures, and sections.
- 5: Excellent long-term vault usability without sacrificing technical depth.

### D8. Language And Readability

Weight: 5

- 0: Hard to read, raw extraction-like, or heavily mixed-language.
- 1: Frequent awkward phrasing or untranslated English prose.
- 2: Understandable but noticeably rough.
- 3: Mostly fluent Chinese with minor residue.
- 4: Clear, natural, technically precise Chinese.
- 5: Polished analytical prose that stays faithful to the paper and easy to
  reread later.

## Weighted Score

For each dimension:

`weighted_points = score / 5 * weight`

The maximum total is 100.

Scores are secondary. A high numeric score does not override a hard-gate failure.

## Pairwise Comparison

When comparing a baseline note with a candidate note, evaluate both notes first
without assuming which is newer.

Then assign one of:

- `candidate_wins`
- `baseline_wins`
- `tie`
- `mixed`

Prefer `mixed` when the candidate improves some content dimensions but regresses
on hard gates, factuality, grounding, or important usability.

## Improvement Verdict

Use exactly one final verdict:

- `hard_fail`: the candidate fails any severe hard gate.
- `regression`: the candidate is materially worse than baseline.
- `no_material_change`: differences are cosmetic, noisy, or too small to matter.
- `partial_improvement`: the candidate improves some dimensions but not enough to
  claim broad quality improvement.
- `real_improvement`: the candidate is materially better on core content
  dimensions without introducing hard-gate failures.

To assign `real_improvement`, the candidate should usually:

- pass all known hard gates
- improve Evidence Chain Coverage or Mechanism/Protocol Depth
- not regress on Claim Boundaries and Limitations
- avoid major factual, grounding, citation, figure, or readability regressions
- improve for reasons tied to paper evidence, not only cleaner formatting

## Required JSON Output

The evaluator must emit a JSON object with this shape:

```json
{
  "rubric_version": "v1",
  "paper_id": "",
  "paper_title": "",
  "evidence_confidence": "high|medium|low",
  "hard_gates": {
    "paper_identity_valid": {"status": "pass|fail|unknown", "evidence": ""},
    "no_major_factual_error": {"status": "pass|fail|unknown", "evidence": ""},
    "central_claims_grounded": {"status": "pass|fail|unknown", "evidence": ""},
    "claim_boundaries_honest": {"status": "pass|fail|unknown", "evidence": ""},
    "core_analytical_sections_exist": {"status": "pass|fail|unknown", "evidence": ""},
    "no_degraded_source_pretending": {"status": "pass|fail|unknown", "evidence": ""},
    "figure_table_citation_paths_not_broken": {"status": "pass|fail|unknown", "evidence": ""},
    "readable_chinese_final_note": {"status": "pass|fail|unknown", "evidence": ""}
  },
  "baseline": {
    "scores": {
      "evidence_chain_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "mechanism_protocol_depth": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "results_settings_numbers": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "claim_boundaries_limitations": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "comparative_positioning_novelty": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "reusable_takeaways": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "obsidian_usability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "language_readability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""}
    },
    "total_score": 0
  },
  "candidate": {
    "scores": {
      "evidence_chain_coverage": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "mechanism_protocol_depth": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "results_settings_numbers": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "claim_boundaries_limitations": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "comparative_positioning_novelty": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "reusable_takeaways": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "obsidian_usability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""},
      "language_readability": {"score": 0, "weighted_points": 0, "reason": "", "evidence": ""}
    },
    "total_score": 0
  },
  "pairwise_result": {
    "winner": "candidate_wins|baseline_wins|tie|mixed",
    "material_improvement": true,
    "improvement_summary": "",
    "candidate_regressions": []
  },
  "verdict": "hard_fail|regression|no_material_change|partial_improvement|real_improvement",
  "next_recommendation": ""
}
```

The JSON may be followed by a short human-readable summary, but the JSON is the
source of truth for automated comparison.
