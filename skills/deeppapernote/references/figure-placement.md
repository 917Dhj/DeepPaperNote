# Figure Placement

Language note: target sections and figure-callout labels must follow the generated writing contract. For English output, use the labels in `output-language.md`.

In MVP, the skill must plan figure placement even when it cannot extract image files.

## Goal

Plan placeholders for every high-value figure or table that materially helps the note.
Do not collapse the paper down to only 1 to 3 items if the paper clearly has more important visuals.

## What to Prefer

Priority order:
1. study overview or method overview figure
2. data or task-definition figure
3. key result figure or table
4. other supporting figures that clarify a major argument

## Placement Logic

- Put method overview figures in `### 机制流程` when they directly explain the core execution chain
- If the match is weaker or the note does not need that micro-structure, keep them in `方法主线`
- Put data or task figures in `数据与任务定义`
- Put main result figures or tables in `关键结果`
- Put conceptual diagrams in `研究问题` or `深度分析` if they clarify the argument

## What to Read

Use:
- figure captions
- nearby正文对 figure 的引用
- section context
- candidate pages and candidate images from deterministic PDF asset extraction

Do not place figures by paper order alone.
Do not let scripts make the final semantic choice; scripts should only prepare candidates.

## Placeholder-First Rule

- The final note should first have the right placeholder structure.
- If a usable image is extracted and semantically matched with high confidence, replace that placeholder with the real image.
- If a reliable image is not available, keep the placeholder.
- Never silently remove a figure just because extraction failed.
- Text correctness is more important than image completeness.

## Machine Contract Boundary

The generated `writing_contract.figure_table_contract` owns figure/table fields, decision values, candidate statuses, and inspection requirements. Use that contract instead of treating this visual-judgment guide as a second schema.

When the contract requires manual inspection, open the actual candidate image before claiming that a visual review found a defect. Keep missing candidates separate from real materialization failures: `asset_candidate_missing`, an empty source image path, or no independent matching crop means no usable candidate was available; materialization failure means a selected real asset later failed to copy or write.

## Integrated Placement Rule

Every kept placeholder must be placed directly under the most relevant substantive section named by its `建议位置`.
Do not collect unresolved placeholders into a catch-all section such as `剩余图表占位`, `未放置图表`, `Remaining figures`, or `Leftover figures`.

Rejecting an extraction candidate does not by itself require a final-note placeholder. The final placeholder set should come from semantic importance to the note, not from the number of failed extraction candidates.

For survey papers with many representative project figures, appendix tables, or repetitive supplemental visuals:
- keep a callout only when the visual materially helps the reader understand the argument
- otherwise summarize the pattern in prose or point the reader back to the appendix/source paper
- do not stack low-value callouts just to demonstrate that the pipeline saw them

## Visual Quality Gate

Figure/table insertion has two separate gates:
- identity match: the candidate label, caption, and local context match the planned figure/table
- visual usability: the crop actually contains the visual body needed by the reader

A label or caption match is not insertion approval.
Deterministic signals may reject an obvious defect, but only an actual image inspection may approve insertion.
Fail closed when visual usability is weak: keep the placeholder instead of inserting the candidate.

Every selected candidate begins as `review_pending`. Review it after the synthesis bundle exists and before `note_plan`:

1. Open the exact candidate crop and its complete source page preview. Each page preview carries a 10% grid; it stays out of every crop and saved image.
2. Compare them with the matched Figure/Table identity and external caption.
3. Confirm that the crop is a Visual-Body Crop: the complete scientific visual is present, all internal labels remain readable, and the external caption and surrounding paper prose are absent.
4. Record your verdict with the `review` command. Do not edit the decisions file by hand.

```bash
python3 scripts/plan_figure_table_decisions.py review \
  --decisions <figure_table_decisions.json> --item "Figure 1" \
  --verdict pass --preserved "<scientific element>" --preserved "<scientific element>"

python3 scripts/plan_figure_table_decisions.py review \
  --decisions <figure_table_decisions.json> --item "Figure 2" \
  --verdict fail --failure <terminal failure reason> --notes "<what you saw>"
```

`pass` requires at least one `--preserved` element you actually saw, and turns the item into `insert`. `fail` turns it into `visual_defect`. `drop` records that the note does not need the item; see Dropping. The script writes the asset SHA-256 and refuses a crop whose bytes changed after planning. The verdict remains yours: the command only records it.

A passing review is valid only for the decision entry's current asset SHA-256. Any asset change returns the item to `review_pending`. Complete the Figure/Table Decision Freeze before planning or drafting; grounding must reject an unresolved or stale review.

## Promotion

The planner's selection is only a starting point. When a Figure/Table the note needs is `low_priority`, a `placeholder`, or an automatic `visual_defect`, send it into review:

```bash
python3 scripts/plan_figure_table_decisions.py promote \
  --decisions <figure_table_decisions.json> --assets <assets.json> --item "Figure 9"
```

With a usable crop on file, the command rerenders it at the contract's 300 dpi. Without one, it names the page preview to open; read the region off the grid and rerun with `--bbox x0,y0,x1,y1`, adding `--page <n>` when the body is not on the caption's page. The promoted item starts at `review_pending` and takes the same review as any other candidate. Items already in review cannot be promoted again.

## Dropping

Review selects for the note, not only for crop quality. After opening a candidate, drop it when the note has no use for it, for example a third example gallery that repeats a pattern already shown:

```bash
python3 scripts/plan_figure_table_decisions.py review \
  --decisions <figure_table_decisions.json> --item "Figure 12" \
  --verdict drop --reason "<why this note does not need it>"
```

`--reason` is required, is stored as the item's `skip_reason`, and states your editorial judgment about this paper. The item becomes `dropped`, stays in the decision table with its reviewed asset SHA-256, and appears with its reason in the `run_state.py` summary and the Final user report. Keep no callout for it in the note.

A drop is an editorial choice, never a visual verdict:

- A crop with a visual problem takes `repair` or `fail`. If the note needs the visual, repair it instead of dropping it. A failure reason is refused as a `--reason`, and an item with a recorded visual failure cannot become a drop.
- Do not drop a key method overview or main result figure to save work; the priorities in What to Prefer still apply.
- An item the planner left out of review needs no drop: it is already not inserted.
- Later verdicts replace a drop if your judgment changes. Grounding rejects a drop with no reason, no recorded review, or a stale asset hash.

## Visual-Body Crop Boundary

Keep axes, tick labels, legends, color bars, scale bars, panel letters, table headers, method labels, and other text that belongs inside the scientific visual. Keep a small safety margin so edge labels are not clipped. Exclude the source caption and unrelated running prose from the image pixels while retaining the caption as metadata and later Markdown explanation.

If the external caption cannot be separated without damaging the scientific visual, fail closed and keep the placeholder. The first implementation reviews complete Figure/Table bodies only; do not split panels into separate assets.

## Bounded Crop Repair

Use a Bounded Crop Repair only for a geometry-only failure allowed by the generated contract. Read the corrected region off the grid on the page preview. The bbox is relative to the whole page, not to the crop. Then run:

```bash
python3 scripts/plan_figure_table_decisions.py review \
  --decisions <figure_table_decisions.json> --item "Table 3" \
  --verdict repair --failure <repairable failure reason> --bbox x0,y0,x1,y1
```

The script validates the bbox, rerenders once from the source PDF at the contract's 300 dpi, refreshes the asset SHA-256, and returns the item to `review_pending` for a full fresh review. A terminal defect or a failed repaired crop remains a placeholder; a second repair request closes the item as `repair_limit_exhausted`.

Reject candidates that are:
- caption-only crops
- tables with no visible table body
- table crops contaminated by running prose outside the table body or another Figure/Table caption
- figure crops contaminated by another Figure/Table caption or by a second figure body
- large text, title-page, or abstract crops masquerading as figures
- crops where the visual body is tiny relative to the crop

## Rendering Boundary

Use `obsidian-format.md` for final placeholder, image embed, caption, and numbering rules. This guide owns placement and visual judgment, not Markdown rendering.

## When to Skip

If the paper has no informative figures or tables:
- do not force one
- state that no high-value figure placeholder was added
