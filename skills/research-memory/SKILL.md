---
name: research-memory
description: Use when the user wants to build, update, or review their research memory (研究记忆), the Obsidian note of their research directions that DeepPaperNote reads to tailor each paper's takeaways.
---

# Research Memory

Keep `<vault>/DeepPaperNote/research-memory.md` true to the user's research by **interviewing** them. The user never writes the memory alone: you propose, with evidence from what they have read; they confirm, correct, or add. Only confirmed answers reach the file, and only through `scripts/write_research_memory.py`. This skill writes that one file and never touches paper notes.

`references/file-contract.md` defines the file format and the JSON both scripts read and write. Read it before step 4.

## 1. Read the vault

Run `python3 scripts/aggregate_reading.py --output <tmp>/aggregate.json`. It finds the vault through DeepPaperNote's configuration. On `needs_vault` or `not_a_vault`, ask the user once for their Obsidian vault folder and rerun with `--vault <path>`.

Keep `memory.sha256` from this run; step 4 passes it to the writer.

**Done when** the aggregate reports `status: ok`.

## 2. Plan the interview

`memory.exists` picks the mode. Build the list of open **candidates**, each a statement you will ask the user to confirm, with its evidence: counts and up to five notes by title from the aggregate.

**Building** (no memory file yet):
- With `enough_reading` true, propose candidate directions from clusters across `aggregates.methods`, `datasets`, `tasks`, `domains`, and the recent window. The user's own words weigh most: `papers[].my_notes` and `papers[].judgments`.
- With `enough_reading` false, propose no direction from reading; ask for directions directly.
- Always add: the user's field and role, the concrete problem they work on now, and topics outside their focus.

**Updating** (the file exists):
- Ask only about change: themes in recent reading that no direction and no not-focus item covers; directions with no reading in `recent_90_days`, asking whether to keep each; the new reading observations.
- Every item already in the file counts as confirmed. Leave topics matching a not-focus item unasked.

In both modes:
- What your own memory holds about the user's research becomes candidates, labeled as coming from your memory, never as reading evidence.
- With `legacy_count` above zero, the first round states how many notes lack structured fields and that the counts may be incomplete.

**Done when** every candidate is on the list.

## 3. Interview in rounds

Ask in **rounds** of at most four numbered questions, in the user's language. Each question asks one thing and ends with your proposed answer and its evidence, worded so "yes" accepts it. The user may answer tersely ("1 是，2 不是，3 改成……").

```
❓ **Q1** - 你读过的 23 篇里有 9 篇关于指令数据合成（Self-Instruct、Alpaca、……），其中 3 篇的"我的笔记"提到心理咨询。

➡️ 建议写成研究方向：用大模型合成心理咨询对话数据。
```

- A direction is one sentence, specific enough to judge whether a paper's method transfers to it. A broad answer such as "NLP" earns one follow-up about the concrete problem; when the user prefers their own words, keep them.
- Directions hold at most five items. Past five, offer to merge.
- A direction may carry one detail line naming the question the user cares about now.
- A candidate the user rejects as outside their interest becomes an offer to record it under not-focus.
- Each answer reshapes the next round: drop questions it already settled, add the follow-ups it raises.
- "先这样" or "enough for now" ends the interview: go to step 4 with what is confirmed. When the user abandons the interview, write nothing.

**Done when** no candidate is open and nothing is left to ask.

## 4. Preview, confirm, write

Turn the confirmed answers into the JSON from `references/file-contract.md`:
- **Building**: a content file. Run the writer with `--create <content.json> --expected-sha256 absent --language <aggregate language> --dry-run`, and show the user `text` in full.
- **Updating**: a change list. Run it with `--update <changes.json> --expected-sha256 <memory.sha256> --dry-run`, and show the user `diff`. Point out any hand-written text the new reading observations replace.

Reading observations state facts about what the user read, each with at most five `evidence` targets copied from `papers[].target`. With `enough_reading` false, pass an empty list.

After the user confirms, run the same command without `--dry-run`. A refusal names its cause:
- the file changed since step 1: rerun step 1, show the user the current file, and confirm the changes again;
- an evidence target matches no note: copy it again from the aggregate.

**Done when** the writer reports `written: true`, or the user declined the preview.

## 5. Report

Give the file path and what changed. Say that DeepPaperNote reads My Research Directions to shape each note's transferable ideas whenever a request names no direction, and that the user can edit the first two sections in Obsidian at any time.
