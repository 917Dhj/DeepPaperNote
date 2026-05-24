# Evidence-First Note Writing

Use this guide when the goal is to approach the quality of a hand-written research note rather than a template-filled summary.

## Core Rule

Do not write the finished note directly from:
- the title
- the abstract
- one or two extracted snippets
- fixed headings alone

Instead, use a three-stage model-first pipeline:

1. build raw-source artifacts and a manifest bundle
2. create the canonical short JSON `note_plan` around source sections/pages
3. run the grounding gate
4. let the model write the note from the raw source, bundle, and plan

## Source Manifest Bundle

The source manifest and bundle should answer:
- what type of paper this is
- which parts of the PDF were actually found
- where the raw source text lives
- which numbers matter
- which datasets, metrics, baselines, or cohorts matter
- which figures are method figures, data figures, and result figures
- which conclusions are about scale, transfer, cost, limitations, or practical value
- which central claims have source evidence and which boundaries the evidence cannot cross

In `DeepPaperNote`, use:
- `scripts/run_pipeline.py`
- `scripts/extract_source_text.py`
- `scripts/build_synthesis_bundle.py`

## Explicit Note Plan

Before drafting the final note, the agent should create an explicit short planning artifact rather than silently "thinking it through" and jumping straight to the final Markdown.

Do **not** require or expose a long free-form chain-of-thought block such as `<thinking>...</thinking>`.
Instead, require a compact and inspectable JSON planning file. The canonical artifact is a short JSON file such as `<note>.plan.json` or a run-scoped `*_note_plan.json`.
Pass that file to `scripts/lint_note.py --plan-file ...` when linting; if omitted, lint looks for a sibling `<note>.plan.json`.
In interactive contexts, you may additionally show a compact `<note_plan>...</note_plan>` block as display-only context, but it does not replace the JSON file.

The plan should state:
- which sections this paper actually deserves
- which sections need more technical depth
- which subsections deserve `###` headings
- which evidence feeds each section
- which 3 to 6 numbers matter most
- which comparisons are the real ones
- which central claims are supported by which source sections or pages
- what each central claim actually proves and does not prove
- which weak, negative, limiting, or explicitly unreported results constrain the conclusion
- which research or engineering takeaways are reusable beyond the current paper
- whether this is mostly a method note, system note, dataset note, benchmark note, or empirical/clinical note
- whether key formulas or complexity expressions need to appear in the final note

Good note plans often add paper-specific sections such as:
- `### 数据构建`
- `### 量表代理特征抽取`
- `### 训练细节`
- `### 关键洞察`
- `### 为什么结果不等于临床可用`

Recommended shape:

```json
{
  "paper_type": "AI_method",
  "paper_type_rationale": "The paper proposes a model mechanism and evaluates it against baselines; the script suggestion was treated only as a hint.",
  "dominant_domain": "machine learning",
  "must_cover": ["数据构建", "方法主线", "关键消融"],
  "key_numbers": ["主结果提升 3.2 points", "训练成本降低 40%"],
  "real_comparisons": ["against the strongest reported baseline"],
  "central_claims": [
    {
      "claim": "The proposed mechanism improves multi-step tool use reliability.",
      "supporting_evidence": [{"section_id": "sec:experiments"}, {"pages": [7, 8]}],
      "what_it_actually_proves": "The reported benchmark settings show fewer unrecoverable tool errors than the named baseline.",
      "what_it_does_not_prove": "It does not prove robustness to arbitrary tools or production latency failures."
    }
  ],
  "claim_boundaries": ["The result is tied to the paper's tool set and benchmark distribution."],
  "negative_or_limiting_results": ["The paper does not clearly report a failed external-tool setting."],
  "mechanism_result_map": ["The state transition design explains the lower unrecoverable-error rate by preserving failed tool-call state for later repair."],
  "comparative_positioning": ["Compared with answer-only baselines, the paper evaluates a mechanism that keeps intermediate failure states inspectable."],
  "reuse_takeaways": ["Track tool failures as first-class state rather than hiding them in the final answer."],
  "followup_questions": ["Does the same state logging still help when external tools are slow, missing, or adversarially noisy?"],
  "section_plan": [
    {
      "section": "方法主线",
      "weight": "high",
      "subsections": ["机制流程", "训练目标"],
      "evidence_sources": [{"section_id": "sec:method"}, {"pages": [4, 6]}]
    }
  ]
}
```

Before drafting from this plan, run `scripts/lint_grounding.py --note-plan ... --source-manifest ... --bundle-json ... --figure-decisions ...`.

The plan should be short, structured, and directly useful for the final draft.

## Writing Layer

Only after the evidence bundle and explicit JSON `note_plan` exist should the model draft the final note.

Good final notes should:
- prioritize numbers and comparisons over generic summary sentences
- add paper-specific subsections when the evidence supports them
- avoid abstract-only rewriting
- explain why a figure or table matters, not just attach it
- separate “作者声称了什么” from “论文真正证明了什么”
- carry the plan's claim boundaries into `深度分析` and `局限`
- explain the mechanism deeply enough that an engineer could re-explain or re-implement the main flow

## Minimum Quality Bar

If the note does not clearly contain:
- the most important numbers
- the most important comparison
- one paper-specific insight
- one honest limitation
- one technically detailed subsection
- and, when necessary, one key formula or formal expression

then the note is still too close to a template summary.
