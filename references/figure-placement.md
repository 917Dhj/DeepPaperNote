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

- Put method overview figures in `方法主线`
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

## Placeholder Requirements

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
- if the extracted image is only a subpanel or partial crop, say so explicitly

## When to Skip

If the paper has no informative figures or tables:
- do not force one
- state that no high-value figure placeholder was added
