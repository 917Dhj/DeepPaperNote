# Obsidian Format

Language note: section names, metadata labels, figure callouts, and the mechanism-flow heading must follow `synthesis_bundle.writing_contract`. For `en`, use the exact schema in `output-language.md`; Chinese-specific examples below apply only to `zh-CN`.

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
  - `<领域>/<paper_slug>/<paper_slug>.zh-CN.md`
  - `<领域>/<paper_slug>/<paper_slug>.en.md`
  - `<领域>/<paper_slug>/images/...`
  - `<领域>/<paper_slug>/.deeppapernote.json`
- when deciding `<领域>`, prefer matching an existing first-level domain folder under the user's papers directory
- domain routing uses the editable taxonomy in `references/domain_rules.yaml`: application domains are checked before fallback method domains
- reuse existing first-level folders conservatively; method-only evidence should not force reuse of an unrelated application folder
- only create a new domain folder when no existing domain is a reasonable fit
- do not save new papers directly into the bare papers root
- always create the paper-local `images/` directory during final save, even if no real image is inserted
- the paper-local `images/` directory is part of the required note layout, not an optional optimization

The hidden `.deeppapernote.json` sidecar is the program-owned directory identity record. It groups verified source PDFs for one work and binds each saved note to exact source bytes and language. Keep the dot-prefixed name on every platform; on Windows the save script also applies and verifies the native Hidden attribute.

Before drafting, run the save script's preflight and use its directory, note path, and `asset_subdir`. Verified PDF-only directories can be reused automatically. Multiple source versions share the paper directory with separate notes and assets. Follow [the shared archive contract](paper-archive.md) for migration, candidate selection, and hash-bound overwrite rules.

If the user already has a vault convention, preserve it.

## Markdown Style

- Prefer short paragraphs over long bullet lists.
- Use bullets for metadata and sharply list-shaped content.
- Keep code or metric identifiers in backticks.
- When English proper nouns (model names, dataset names, method names, metric names, venue abbreviations) or standalone key numeric values appear inline within Chinese prose, wrap them in backticks for visual separation — e.g. `GPT-4`、`SQuAD`、`BLEU`、`87.3%`.
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
- move explanatory content to `一句话总结`、`深度分析`、`阅读收获` or another true analysis section

## YAML Frontmatter

Every note must start with an Obsidian properties block **above** the `#` title heading.

Required fields:
- `tags`: use `papers/<domain>` hierarchy, e.g. `papers/NLP`, `papers/CV`, `papers/multimodal`
- `aliases`: English short name or common abbreviation for wikilink resolution
- `date`: ISO publication date; use `YYYY` if only the year is known
- `doi`: DOI string without the `https://doi.org/` prefix; omit the field entirely if unavailable
- `paper_type`: the note plan's `paper_type`, e.g. `AI_method`
- `methods`, `datasets`, `tasks`: lists of 0 to 5 core items each; an empty list is written `[]`
- `read_date`: the day the paper was first read, as `YYYY-MM-DD`; distinct from the publication `date`

These keys stay in English in both `zh-CN` and `en` notes, so one Bases view can query every note. `writing_contract.frontmatter_contract` carries the exact rules, and Final Note Lint checks them.

Example:

```yaml
---
tags:
  - papers/NLP
aliases:
  - "Paper Short Name"
date: 2024-05-01
doi: 10.18653/v1/2024.acl-long.1
paper_type: AI_method
methods: [direct preference optimization]
datasets: [Anthropic HH]
tasks: []
read_date: 2026-11-06
---
```

Rules:
- Do not invent placeholder values for missing fields; omit them instead.
- The `tags` field must always be present with at least one `papers/<domain>` tag.
- `aliases` should be the paper's short name or acronym (e.g. "GPT-4", "LoRA"), not a paraphrase.
- `methods`, `datasets`, and `tasks` name only what is central to the paper, never every term it mentions. Write the values as plain text.
- When an existing note is replaced, copy `existing_read_date` from the admission result into `read_date`; otherwise use today's date.

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
![[Research/Papers/DeepPaperNote/paper_slug/images/figure_2.png]]
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
11. `阅读收获`
12. `引用`
13. `我的笔记`

When abstract metadata exists, `原文摘要翻译` should be a single Chinese translation block for the original abstract rather than a bilingual subsection pair.

This order is the stable backbone, not a full outline.
When the paper is complex, add `###` subsections such as:
- `### 数据来源`
- `### 任务定义`
- `### 机制流程`
- `### 为什么结果成立`
- `### 哪些地方容易被误读`

## 阅读收获 Section Format

```md
## 阅读收获

### 可迁移

- 一到两条，每条一两句话：论文里的具体机制或做法、能迁移到哪里、迁移成立的前提。结合用户研究方向的条目以 `判断：` 开头。

### 下一步

- 一到两条，每条一两句话：针对这篇论文的追问或实验，至少一条检验论文自身的论断或证据；推荐的论文必须已出现在 `引用` 中。
```

## 我的笔记 Section Format

`我的笔记` is always the last section. A generated draft holds exactly this guidance line under the heading:

```md
## 我的笔记

> [!note] 这一节留给你自己：写下你的判断、它和你研究的联系、想验证的点。重新生成这篇笔记时，这一节会原样保留。
```

Everything from the `## 我的笔记` heading line to the end of the file belongs to the user, including any `##` headings the user adds. Formal Save keeps that block from the note it replaces, unless the old note is byte-identical to its last recorded save or the block is exactly the standard guidance. When the old note has no `## 我的笔记` heading, nothing can be kept and the overwrite prompt says so.

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
