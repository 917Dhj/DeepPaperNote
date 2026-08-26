# Output Language

DeepPaperNote supports two output schemas:

| Setting | Language |
|---|---|
| `zh-CN` | Simplified Chinese |
| `en` | English |

Resolve the profile through `user-configuration.md`. For a single command, use `--language en` with `run_pipeline.py`, `build_synthesis_bundle.py`, `lint_note.py`, or `write_obsidian_note.py` where applicable. A Run Override never changes User Configuration.

## English note schema

Use these top-level sections in this order:

1. `Core Information`
2. `Abstract`
3. `Contributions`
4. `One-Sentence Summary`
5. `Research Question`
6. `Data and Task Definition`
7. `Method`
8. `Key Results`
9. `Deep Analysis`
10. `Limitations`
11. `Research Notes`
12. `References`

The allowed Core Information fields, in order, are:

`Title`, `Translated title`, `Authors`, `Institutions`, `Publication date`, `Venue`, `DOI`, `arXiv`, `Paper link`, `Code / Project`, `Data / Resources`, `Paper type`.

Use `### Mechanism Flow` for the mechanism-flow subsection. Each figure placeholder uses:

```md
> [!figure] Figure 2 Human-readable label
> Suggested location: Method
> Why it matters: This figure clarifies the execution path.
> Current status: Placeholder retained; the recovered crop is incomplete.
```

For a materialized image, use the normal image embed followed immediately by one italic caption beginning with `Original paper item:`.

`Abstract` is a faithful rendering of the source abstract in English. Preserve its meaning and scope; contribution claims, result interpretation, and hindsight judgment belong later unless the source abstract itself contains them.

The English style gate checks headings, Core Information labels, figure callouts, inserted-image captions, and prose. Mark original non-English metadata with inline code inside `Core Information`, or with inline code or a Markdown link inside `References`; closed fenced code blocks and URLs keep their normal source text. In prose, a CJK identifier or stable proper noun must be an HTTP Markdown link or Obsidian wikilink. A source formula may retain only these CJK `\operatorname{...}` labels: `输入`, `输出`, `损失`, `状态`, `动作`, `奖励`, `标签`, `样本`, `预测`, and `目标`. The surrounding text remains subject to the English gate; inline code and free-form math text do not exempt Chinese prose.

## Contract ownership

`SKILL.md` owns the cross-stage Language Integrity Contract. This reference owns only the profile-specific schema and labels above; apply them under the resolved language carried by that contract.
