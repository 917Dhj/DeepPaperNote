# Research Memory

`research-memory` keeps one Obsidian note, `<vault>/DeepPaperNote/research-memory.md`, that records your research directions, the topics outside your focus, and observations about what you have read. DeepPaperNote reads your directions to shape each note's transferable ideas whenever you do not name a direction in the request.

You do not write the memory yourself. The agent reads your paper notes, proposes directions with evidence, and asks you in short rounds; only what you confirm is written, after you see a preview.

Start it with `/research-memory`, or ask "建立我的研究记忆" / "update my research memory".

It finds your vault through DeepPaperNote's configuration (`~/.deeppapernote/config.json`) and asks once when that is missing. It writes only the memory file and never edits paper notes. You can edit the directions and not-focus sections in Obsidian at any time; the skill keeps your edits.

See [`references/file-contract.md`](references/file-contract.md) for the file format and script interfaces.

```bash
python3 -m pytest -q skills/research-memory/tests
```
