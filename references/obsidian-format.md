# Obsidian Format

## Heading Rules

- Use `#` for the note title only.
- Use `##` for major sections.
- Use `###` only when a section genuinely needs internal structure.
- Do not flatten everything into bullet points.
- For method, system, benchmark, or clinical empirical papers, prefer meaningful `###` subheadings in technical sections instead of one long undifferentiated block.
- For method, framework, or system papers, default to `### 机制流程` inside `方法主线` and write it as a numbered 3 to 4 step flow.

## File Naming

Default file name:
- sanitized English title with underscores
- default note layout is folder-per-paper:
  - `<领域>/<paper_slug>/<paper_slug>.md`
  - `<领域>/<paper_slug>/images/...`
- when deciding `<领域>`, prefer matching an existing first-level domain folder under the user's papers directory
- domain routing uses the editable taxonomy in `references/domain_rules.yaml`: application domains are checked before fallback method domains
- reuse existing first-level folders conservatively; method-only evidence should not force reuse of an unrelated application folder
- only create a new domain folder when no existing domain is a reasonable fit
- do not save new papers directly into the bare papers root
- always create the paper-local `images/` directory during final save, even if no real image is inserted
- the paper-local `images/` directory is part of the required note layout, not an optional optimization
- if the target is an Obsidian vault but the current environment cannot create that directory yet, request permission escalation rather than omitting it

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

## Core Info Block

`## 核心信息` is a fixed metadata zone.

Formatting and scope rules:
- Core info field schema: use only the following fields, in this order, and no free prose:
  `标题`, `标题翻译`, `作者`, `机构`, `发表时间`, `发表渠道`, `DOI`, `arXiv`, `论文链接`, `代码 / 项目`, `数据 / 资源`, `论文类型`
- keep each entry in `- 字段名: 值` form
- omit fields that are unavailable or not applicable; do not add placeholder rows just to fill the schema
- do not add interpretation, commentary, judgment, or takeaway lines inside `核心信息`
- do not use the last metadata bullet as a place to append extra analysis
- move explanatory content to `一句话总结`、`深度分析`、`我的笔记` or another true analysis section

## YAML Frontmatter

Every note must start with an Obsidian properties block **above** the `#` title heading.

Required fields:
- `tags`: use `papers/<domain>` hierarchy, e.g. `papers/NLP`, `papers/CV`, `papers/multimodal`
- `aliases`: English short name or common abbreviation for wikilink resolution
- `date`: ISO publication date; use `YYYY` if only the year is known
- `doi`: DOI string without the `https://doi.org/` prefix; omit the field entirely if unavailable

Example:

```yaml
---
tags:
  - papers/NLP
aliases:
  - "Paper Short Name"
date: 2024-05-01
doi: 10.18653/v1/2024.acl-long.1
---
```

Rules:
- Do not invent placeholder values for missing fields; omit them instead.
- The `tags` field must always be present with at least one `papers/<domain>` tag.
- `aliases` should be the paper's short name or acronym (e.g. "GPT-4", "LoRA"), not a paraphrase.

## Figure Placeholder Style

Use this callout format only for placeholders that remain unresolved in the final note:

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

The structured `[FIGURE_PLACEHOLDER] ... [/FIGURE_PLACEHOLDER]` block is legacy/internal only.
Do not use it in the final user-facing note unless you are debugging the pipeline.

If a real image has been selected and materialized into the vault, do not keep the `[!figure]` callout for that same figure.
Prefer an Obsidian embed, or use a Markdown image embed when that is the available path.
The embed must be followed immediately by exactly one italic caption line:

```md
![[Research/Papers/DeepPaperNote/paper_slug/images/page_003_img_01.png]]
*论文原图编号：Fig. 2。数据生成流程图。这里插入是因为它最能帮助理解方法主线。*
```

## Default Section Order

1. `核心信息`
2. `原文摘要翻译`
3. `创新点`
4. `一句话总结`
5. `研究问题`
6. `数据与任务定义`
7. `方法主线`
8. `关键结果`
9. `深度分析`
10. `局限`
11. `我的笔记`
12. `引用`

When abstract metadata exists, `原文摘要翻译` should be a single Chinese translation block for the original abstract rather than a bilingual subsection pair.

This order is the stable backbone, not a full outline.
When the paper is complex, add `###` subsections such as:
- `### 数据来源`
- `### 任务定义`
- `### 机制流程`
- `### 为什么结果成立`
- `### 哪些地方容易被误读`

## 引用 Section Format

Entries in `## 引用` should link to existing notes in the vault where possible.
If the synthesis bundle includes `references.candidates`, use confirmed candidate `wikilink` values when present. When `wikilink` is empty, treat `display_text` as the plain-text fallback.
Follow this priority order for each reference:

1. **Vault lookup first**: check whether the cited paper already has a note in the vault.
   - Match by note basename (the `<paper_slug>` part of the folder name).
   - Match by the `aliases` field in the note's YAML frontmatter.
2. **If a match is found**: write a wikilink that separates the target from the display text:
   ```
   - [[paper_slug_or_alias|Human Readable Title]]
   ```
3. **If no match is found**: do not invent a wikilink target. Write the reference as plain text instead:
   ```
   - Vaswani et al. (2017). Attention Is All You Need.
   ```
   Use the candidate `display_text` as the plain fallback when available.

Rules:
- Never use a raw English paper title as the wikilink target; it will not match vault filenames.
- To derive a likely slug from a title: lowercase the title and replace spaces and special characters with underscores — but only use the result as the target if you have confirmed the file exists.
- List only papers cited or directly relevant to this note.
- Do not add extra DOIs or author metadata when using wikilink format; the display text is enough.
