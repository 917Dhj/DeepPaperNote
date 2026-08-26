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
5. `Research Questions`
6. `Data and Task Definition`
7. `Method`
8. `Key Results`
9. `Deep Analysis`
10. `Limitations`
11. `My Notes`
12. `References`

The allowed Core Information fields, in order, are:

`Title`, `Translated title`, `Authors`, `Institutions`, `Publication date`, `Venue`, `DOI`, `arXiv`, `Paper link`, `Code / Project`, `Data / Resources`, `Paper type`.

Use `### Analytical Flow` for the mechanism-flow subsection. Each figure placeholder uses:

```md
> [!figure] Figure 2 Human-readable label
> Suggested location: Method
> Why it matters: This figure clarifies the execution path.
> Current status: Placeholder retained; the recovered crop is incomplete.
```

For a materialized image, use the normal image embed followed immediately by one italic caption beginning with `Original paper item:`.

## Contract ownership

`SKILL.md` owns the cross-stage Language Integrity Contract. This reference owns only the profile-specific schema and labels above; apply them under the resolved language carried by that contract.
