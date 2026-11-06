# Output Language

DeepPaperNote supports two output schemas:

| Setting | Language |
|---|---|
| `zh-CN` | Simplified Chinese |
| `en` | English |

Resolve the profile through `user-configuration.md`. For a single command, use `--language en` with `run_pipeline.py`, `build_synthesis_bundle.py`, `lint_note.py`, or `write_obsidian_note.py` where applicable. A Run Override never changes User Configuration.

## Simplified Chinese note schema

Use these top-level sections in this order:

1. `核心信息`
2. `原文摘要翻译`
3. `创新点`
4. `一句话总结`
5. the middle sections of the paper type, in order (`contracts_by_paper_type[paper_type].middle_sections`, see `paper-types.md`)
6. `局限`
7. `阅读收获`
8. `关联`
9. `我的笔记`

The workflow subsection heading and table header come from `contracts_by_paper_type[paper_type].workflow`; the weak-evidence callout is `> [!warning] 论文报告不足`. `阅读收获` holds exactly two subsections, `### 可迁移` and `### 下一步`; an item tied to the user's stated research direction starts with `判断：`. `关联` holds `### 库内笔记` and `### 关键前置文献`; an empty `库内笔记` reads `库里暂无相关笔记`, or `当前为 workspace 模式，未连接知识库` in workspace mode. `我的笔记` is the last section and, in a generated draft, holds only this guidance line:

```md
> [!note] 这一节留给你自己：写下你的判断、它和你研究的联系、想验证的点。重新生成这篇笔记时，这一节会原样保留。
```

Chinese figure placeholders use the labels `建议位置：`, `放置原因：`, and `当前状态：`; a materialized image caption begins with `论文原图编号：`.

`原文摘要翻译` is a faithful Chinese translation of the source abstract. Preserve its meaning and scope; contribution claims, result interpretation, and hindsight judgment belong later unless the source abstract itself contains them.

## English note schema

Use these top-level sections in this order:

1. `Core Information`
2. `Abstract`
3. `Contributions`
4. `One-Sentence Summary`
5. the middle sections of the paper type, in order (`contracts_by_paper_type[paper_type].middle_sections`, see `paper-types.md`)
6. `Limitations`
7. `Takeaways`
8. `Connections`
9. `My Notes`

`Takeaways` holds exactly two subsections, `### Transferable Ideas` and `### Next Steps`; an item tied to the user's stated research direction starts with `Judgment:`. `Connections` holds `### In Your Vault` and `### Key Prior Work`; an in-vault entry reads `- [[target|Title]] (relation): reason`, and an empty `In Your Vault` reads `No related notes in your vault yet.`, or `Workspace mode: not connected to a vault.` in workspace mode. `My Notes` is the last section and, in a generated draft, holds only this guidance line:

```md
> [!note] This section is yours: write down your own judgments, how the paper connects to your research, and what you want to verify. When this note is regenerated, this section is kept exactly as it is.
```

The allowed Core Information fields, in order, are:

`Title`, `Translated title`, `Authors`, `Institutions`, `Publication date`, `Venue`, `DOI`, `arXiv`, `Paper link`, `Code / Project`, `Data / Resources`, `Paper type`.

The workflow subsection heading and table header come from `contracts_by_paper_type[paper_type].workflow`; the weak-evidence callout is `> [!warning] Limited reporting`. Each figure placeholder uses:

```md
> [!figure] Figure 2 Human-readable label
> Suggested location: Method
> Why it matters: This figure clarifies the execution path.
> Current status: Placeholder retained; the recovered crop is incomplete.
```

For a materialized image, use the normal image embed followed immediately by one italic caption beginning with `Original paper item:`.

`Abstract` is a faithful rendering of the source abstract in English. Preserve its meaning and scope; contribution claims, result interpretation, and hindsight judgment belong later unless the source abstract itself contains them.

The English style gate checks headings, Core Information labels, figure callouts, inserted-image captions, and prose. Mark original non-English metadata with inline code inside `Core Information`, or with inline code or a Markdown link inside `Connections`, where wikilinks are also exempt; closed fenced code blocks and URLs keep their normal source text. In prose, a CJK identifier or stable proper noun must be an HTTP Markdown link. A source formula may retain only these CJK `\operatorname{...}` labels: `输入`, `输出`, `损失`, `状态`, `动作`, `奖励`, `标签`, `样本`, `预测`, and `目标`. The surrounding text remains subject to the English gate; inline code and free-form math text do not exempt Chinese prose.

## Contract ownership

`SKILL.md` owns the cross-stage Language Integrity Contract. This reference owns only the profile-specific schema and labels above; apply them under the resolved language carried by that contract.
