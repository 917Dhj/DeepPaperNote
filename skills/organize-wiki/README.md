# Organize Wiki

`organize-wiki` keeps your paper library in domain folders you agree with. It writes the convention `<vault>/DeepPaperNote/domains.md`, which DeepPaperNote follows when it files a new paper, and it moves and retags papers to match.

The agent reads your library and your research memory, proposes merges, splits, renames, and moves with evidence, and asks you in short rounds. Nothing changes until you have seen the preview and confirmed it. Every reorganization is logged under `<vault>/DeepPaperNote/organize-log/`, and "撤销上一次整理" / "undo the last reorganization" restores it while the touched files stay unedited.

Start it with `/organize-wiki`, or ask "整理我的知识库" / "organize my paper library".

It moves whole paper folders between domains and never renames a paper folder or a note, so links by file name keep working; links that spell out a moved path are rewritten. Notes without frontmatter are moved but never edited.

See [`references/file-contract.md`](references/file-contract.md) for the file format and script interfaces.

```bash
python3 -m pytest -q skills/organize-wiki/tests
```
