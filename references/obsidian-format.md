# Obsidian Format

## Heading Rules

- Use `#` for the note title only.
- Use `##` for major sections.
- Use `###` only when a section genuinely needs internal structure.
- Do not flatten everything into bullet points.
- For method, system, benchmark, or clinical empirical papers, prefer meaningful `###` subheadings in technical sections instead of one long undifferentiated block.

## File Naming

Default file name:
- sanitized English title with underscores
- default note layout is folder-per-paper:
  - `<领域>/<paper_slug>/<paper_slug>.md`
  - `<领域>/<paper_slug>/images/...`
- when deciding `<领域>`, prefer matching an existing first-level domain folder under the user's papers directory
- only create a new domain folder when no existing domain is a reasonable fit
- do not save new papers directly into the bare papers root
- always create the paper-local `images/` directory during final save, even if no real image is inserted

If the user already has a vault convention, preserve it.

## Markdown Style

- Prefer short paragraphs over long bullet lists.
- Use bullets for metadata and sharply list-shaped content.
- Keep code or metric identifiers in backticks.
- Preserve stable internal links where useful.
- Use normal LaTeX delimiters for math:
  - inline math: `$...$`
  - display math:
    `$$`
    `...`
    `$$`
- Do not wrap formulas in backticks or fenced code blocks unless you are literally showing source code.

## Figure Placeholder Style

Use this callout format as the default and preferred placeholder style:

```md
> [!figure] Fig. 3 数据分布与质量评估
> 建议位置：数据与任务定义
> 放置原因：这张图同时展示样本构成、对话长度统计和专家质检结果，是理解 `PsyInterview` 数据边界最重要的图之一。
> 当前状态：保留占位；当前提取结果只拿到局部子图，无法稳定恢复成可独立解释的完整原图。
```

Formatting rules:
- keep the original paper numbering, for example `Fig. 3` or `Table 2`
- keep a short human-readable label on the first line
- always include `建议位置`
- always include `放置原因`
- always include `当前状态`

`当前状态` should be explicit, for example:
- `保留占位；未找到高置信度整图。`
- `保留占位；当前只匹配到疑似局部子图，不足以稳定替换。`
- `已替换为真实图片；当前插入的是论文原图的局部面板，不是完整复合图。`

The structured `[FIGURE_PLACEHOLDER] ... [/FIGURE_PLACEHOLDER]` block is legacy/internal only.
Do not use it in the final user-facing note unless you are debugging the pipeline.

If a real image has been selected and materialized into the vault, prefer an Obsidian embed:

```md
![[20_Research/Papers/DeepPaperNote/paper_slug/images/page_003_img_01.png]]
*论文原图编号：Fig. 2。数据生成流程图。这里插入是因为它最能帮助理解方法主线。*
```

## Default Section Order

1. `核心信息`
2. `原始摘要`
3. `一句话总结`
4. `研究问题`
5. `数据与任务定义`
6. `方法主线`
7. `关键结果`
8. `深度分析`
9. `局限`
10. `我的笔记`
11. `引用`

Inside `原始摘要`, prefer this stable internal structure when abstract metadata exists:
- `### 英文原文`
- `### 中文翻译`

This order is the stable backbone, not a full outline.
When the paper is complex, add `###` subsections such as:
- `### 数据来源`
- `### 任务定义`
- `### 方法流程`
- `### 关键创新`
- `### 为什么结果成立`
- `### 哪些地方容易被误读`
