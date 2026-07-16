@AGENTS.md

## Claude Code Integration

`skills/deeppapernote/SKILL.md` is both the canonical workflow definition and the Claude Code skill entrypoint.
`.claude-plugin/plugin.json` identifies the plugin, but it must not restate the workflow.

- Do not fork or restate the DeepPaperNote workflow in any Claude-only file.
- All workflow logic stays in `skills/deeppapernote/SKILL.md`.

### Skill Invocation

End users running Claude Code invoke the skill with natural language or the
`/deeppapernote` slash command. Recognized trigger examples:
- `给这篇论文生成深度笔记`
- `写一篇高质量论文精读笔记`
- `把这篇文章整理成 obsidian 笔记`
- `/deeppapernote <paper title, DOI, arXiv ID, or local PDF path>`
