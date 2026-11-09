# Research memory file contract

This contract is shared by the research-memory skill, which writes the file, and DeepPaperNote, which reads it. Neither imports the other's code.

## Location

`<vault>/DeepPaperNote/research-memory.md`, found by convention; no configuration records it. The folder sits outside DeepPaperNote's paper folder, so the memory never counts as a paper note.

The vault comes from DeepPaperNote's user configuration, `~/.deeppapernote/config.json` (or the path in `DEEPPAPERNOTE_CONFIG_PATH`), read as JSON: `obsidian_vault`, `papers_dir`, and `output_language`. A script's `--vault` argument wins over it. A vault is a folder holding `.obsidian/`.

## File format

```md
---
aliases: [研究记忆]
tags: [research-memory]
updated: 2026-11-06
---

# 研究记忆

## 我的研究方向

- 用大模型合成心理咨询对话数据，关注数据质量评估
  - 正在关心的问题：如何自动评估共情程度

## 不太关心的

- 目标检测

## 阅读观察

> 这一节由研究记忆 skill 生成，每次更新整节替换；你自己的看法请写在上面两节。

- 2026-09 以来读的 8 篇里有 5 篇关于指令数据合成
  - 依据：[[Self_Instruct.zh-CN|Self-Instruct]]、[[Alpaca.zh-CN|Stanford Alpaca]]
```

| Section key | zh-CN heading | en heading | Written by |
|---|---|---|---|
| `directions` | 我的研究方向 | My Research Directions | the user, or the skill with the user's confirmation |
| `not_focus` | 不太关心的 | Not My Focus | the user, or the skill with the user's confirmation |
| `observations` | 阅读观察 | Reading Observations | the skill; replaced whole on every update |

- An **item** is a top-level list line (`- `, `* `, or `+ `). Indented list lines directly below it are its **details**.
- Directions hold at most five items. A direction's optional detail names the question the user cares about now.
- The H1 is `研究记忆` or `Research Memory`, by language. Readers recognise the headings of both languages and match them case-insensitively.
- An observation's evidence detail starts with `依据：` or `Evidence: ` and joins `[[target|title]]` links with `、` or `, `. Each target is a note file name in the vault.
- With no observations, the section holds the note line and the sentence `阅读还不够多，暂时没有观察。` (`Not enough reading yet for observations.`).
- Prose, extra sections, and extra frontmatter keys the user adds are kept on update and ignored by readers.

**DeepPaperNote reads** only the top-level items of My Research Directions, each with its details. A missing or empty section means no research memory.

## `aggregate_reading.py` output

| Field | Meaning |
|---|---|
| `status` | `ok`, `needs_vault`, or `not_a_vault` |
| `vault`, `papers_dir`, `language`, `today` | where and how it read |
| `memory` | `path`, `exists`, `sha256` (empty when absent), `language`, and the parsed `directions`, `not_focus`, `observations` |
| `paper_count`, `structured_count`, `legacy_count`, `legacy_targets` | papers read; a legacy note lacks `paper_type` or every one of `methods`, `datasets`, `tasks` |
| `enough_reading` | at least five papers |
| `aggregates.methods`, `.datasets`, `.tasks`, `.domains`, `.paper_types` | `[{value, count, targets}]`, most frequent first |
| `aggregates.by_month` | `{YYYY-MM: count}` by `read_date` |
| `aggregates.recent_90_days` | `{count, targets}` |
| `aggregates.with_my_notes` | papers whose My Notes hold the user's own text |
| `papers` | one entry per paper: `target`, `title`, `domain`, `paper_type`, `methods`, `datasets`, `tasks`, `read_date`, `structured`, `my_notes` (user text, default guidance removed, at most 1500 characters), `judgments` (Takeaways items starting with `判断：` or `Judgment:`) |

A paper is a note under the paper folder with frontmatter. The zh-CN and en notes in one folder count as one paper; `target` prefers the note in the run's language.

## `write_research_memory.py`

Building, `--create content.json --expected-sha256 absent --language zh-CN|en`:

```json
{
  "directions": [{"text": "用大模型合成心理咨询对话数据", "details": ["正在关心的问题：共情评估"]}],
  "not_focus": [{"text": "目标检测"}],
  "observations": [{"text": "最近读的多是指令数据合成", "evidence": ["Self_Instruct.zh-CN"]}]
}
```

Updating, `--update changes.json --expected-sha256 <memory.sha256>`:

```json
{
  "operations": [
    {"op": "add", "section": "directions", "text": "指令数据的自动构造", "details": []},
    {"op": "remove", "section": "not_focus", "match": "目标检测"},
    {"op": "replace", "section": "directions", "match": "<the item's exact current text>", "text": "…", "details": ["…"]}
  ],
  "observations": [{"text": "…", "evidence": ["Self_Instruct.zh-CN"]}]
}
```

- `section` is `directions` or `not_focus`. `match` is an item's exact first-line text, without the list marker. `replace` swaps the whole item, its details included.
- `observations` replaces the Reading Observations section whole. Omit it, or pass `null`, to leave the section as it is.
- An update changes only what it lists, plus the `updated` date. Every other byte of the file is kept.
- Evidence targets are copied from the aggregate's `papers[].target`. The writer resolves each to the note's title, and refuses a target that matches no note.

`--dry-run` writes nothing. Output: `status`, `written`, `path`, `sha256_before`, `sha256_after`, `diff` (unified), and `text` (the whole resulting file).

The writer refuses, exits 1, and writes nothing when:
- `--create` finds an existing file;
- `--update` finds a hash other than `--expected-sha256`, because the file changed after the aggregate read it;
- an evidence target or a `match` is not found;
- the result would hold more than five directions;
- the result loses its sections.

The refusal is `{"status": "refused", "reason": …}`.
