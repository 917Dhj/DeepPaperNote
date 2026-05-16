# Figure Placement

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
- Figure replacement decisions should be completed inside the same note-generation task.
- Do not produce a text-only note first and then ask the user in a follow-up whether figures should be inserted.
- If no figure can be confidently replaced, finish the note with placeholders and explain that outcome in the final response.

## Integrated Placement Rule

Every kept placeholder must be placed directly under the most relevant substantive section named by its `建议位置`.
Do not collect unresolved placeholders into a catch-all section such as `剩余图表占位`, `未放置图表`, `Remaining figures`, or `Leftover figures`.

`reject_visual_quality` means the candidate image must not be inserted.
It does not by itself require a final-note placeholder.
The final placeholder set should come from semantic importance to the note, not from the number of failed extraction candidates.

For survey papers with many representative project figures, appendix tables, or repetitive supplemental visuals:
- keep a callout only when the visual materially helps the reader understand the argument
- otherwise summarize the pattern in prose or point the reader back to the appendix/source paper
- do not stack low-value callouts just to demonstrate that the pipeline saw them

## Visual Quality Gate

Figure/table insertion has two separate gates:
- identity match: the candidate label, caption, and local context match the planned figure/table
- visual usability: the crop actually contains the visual body needed by the reader

A label or caption match is not insertion approval.
Fail closed when visual usability is weak: keep the placeholder instead of inserting the candidate.

Reject candidates that are:
- caption-only crops
- tables with no visible table body
- table crops contaminated by running prose or another Figure/Table caption
- large text, title-page, or abstract crops masquerading as figures
- crops where the visual body is tiny relative to the crop

## Placeholder Requirements

Every kept placeholder in the final note must use the standard `[!figure]` callout format.
Do not use ordinary paragraph markers such as `[图表占位 | Fig. 1]`, `图表占位：Table 2`, or `Figure Placeholder | Fig. 3`.

Each placeholder should include:
- figure or table id
- a short label
- target note section
- reason for placement
- current status
- if available, the most plausible candidate image file(s)

Preferred final-note format:

```md
> [!figure] Fig. 3 数据分布与质量评估
> 建议位置：数据与任务定义
> 放置原因：这张图同时展示样本构成、对话长度统计和专家质检结果，是理解数据边界最重要的图之一。
> 当前状态：保留占位；当前提取结果只拿到局部子图，无法稳定恢复成可独立解释的完整原图。
```

The placeholder text should be stable and explicit:
- `建议位置` says where the figure belongs in the note
- `放置原因` says why the figure matters for understanding the paper
- `当前状态` says whether the note keeps a placeholder or has replaced it with a real image
- `当前状态` must preserve truth over neatness; if extraction is uncertain, say so plainly

If a real image is inserted:
- keep the original paper identifier, for example `Fig. 2` or `Table 1`
- do not renumber it according to note order
- prefer the `obsidian_embed` returned by `scripts/materialize_figure_asset.py`
- if the extracted image is only a subpanel or partial crop, say so explicitly

## When to Skip

If the paper has no informative figures or tables:
- do not force one
- state that no high-value figure placeholder was added
