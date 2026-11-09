# organize-wiki file contract

organize-wiki writes the domains file and moves paper folders; DeepPaperNote reads the domains file when it chooses a new paper's domain. Neither imports the other's code.

## Library layout

- The vault and paper folder come from DeepPaperNote's configuration, `~/.deeppapernote/config.json` (or `DEEPPAPERNOTE_CONFIG_PATH`): `obsidian_vault`, `papers_dir`, `output_language`. `--vault` and `--papers-dir` win. A vault holds `.obsidian/`.
- A **domain** is a folder directly under the papers root. A **paper folder** is a folder directly under a domain. Its notes are the `.md` files directly inside it.
- A paper's **id** is `<domain>/<paper folder>`, relative to the papers root.
- A folder directly under the papers root that holds `<name>.md`, `<name>.zh-CN.md`, `<name>.en.md`, or `.deeppapernote.json` is a paper folder without a domain, reported as an anomaly.
- A paper's **domain tag** is `papers/<domain>`, whitespace written as `_`. A conforming note has frontmatter whose `tags` hold exactly one `papers/` tag, its domain tag.

## Domains file

`<vault>/DeepPaperNote/domains.md`:

```md
---
aliases: [领域分类]
tags: [paper-domains]
updated: 2026-11-07
---

# 领域分类

> 这份约定由整理知识库 skill 与你一起维护。DeepPaperNote 保存新论文时按它选择领域文件夹。

## 长视频理解

- 定义：理解长视频的模型、方法与基准。
- 收录：长视频问答、长视频基准、视频记忆机制。
- 不收录：短视频动作识别（去 计算机视觉）。
- 代表论文：[[LVBench.zh-CN|LVBench]]、[[VideoAgent|VideoAgent]]
```

- Each `##` heading is a domain folder name. Under it, `- <label>：<text>` lines carry the fields. Labels: `定义` / `Definition`, `收录` / `Includes`, `不收录` / `Excludes`, `代表论文` / `Representative papers`. Readers accept either language and `:` or `：`, and ignore other lines.
- English files use the H1 `Paper Domains`, the alias `Paper Domains`, and the note line `This convention is kept with you by the organize-wiki skill. DeepPaperNote follows it to choose the domain folder for a new paper.`
- Representative papers are `[[<note file stem>|<title>]]` links joined by `、` or `, `. They link by file name, so they survive folder moves.

## `scan_library.py`

Read-only. Output:

| Field | Meaning |
|---|---|
| `status` | `ok`, `needs_vault`, or `not_a_vault` |
| `vault`, `papers_dir`, `language`, `today` | where and how it read |
| `domains_file` | `path`, `exists`, `sha256`, `domains` (name → fields, in file order) |
| `research_memory` | `exists`, `directions`, `not_focus` (top-level item texts) |
| `domains` | `[{name, paper_count, in_convention}]` for every domain folder |
| `papers` | one entry per paper folder, below |
| `anomalies` | `[{kind, path, detail}]`, below |

A paper entry: `id`, `domain`, `folder`, `title`, `notes` (paths relative to the paper folder, including notes in a `nested_folder`), `has_sidecar`, `pdf_only` (no note), `tag_status`, `papers_tags` (every `papers/` tag across its notes), `excerpt` (its Abstract section, or the start of the body, at most 400 characters).

`tag_status` is `ok`, `mismatch` (one `papers/` tag, another domain), `multiple`, `missing` (frontmatter with no `papers/` tag), `no_frontmatter`, or `no_note`. With several notes, the worst status counts, in that order reversed.

Anomaly kinds:
- `paper_at_root`: a paper folder directly under the papers root.
- `loose_file`: a file directly in a domain folder or the papers root.
- `nested_folder`: a paper folder holding a subfolder, other than `images`, that holds `.md` files.
- `images_index`: an `.md` file inside a paper's `images/`; reported only.

## Plan

The model writes the plan the user confirmed:

```json
{
  "language": "zh-CN",
  "domains": [
    {"name": "长视频理解", "definition": "…", "includes": "…", "excludes": "…",
     "representative_papers": ["长视频理解/LVBench"]}
  ],
  "renames": [{"from": "多智能体", "to": "LLM智能体"}],
  "moves": [{"paper": "大模型/Social_Code", "to": "社会智能"}],
  "flatten": [{"paper": "Benchmark/SWE_bench"}],
  "wrap": [{"file": "长视频理解/Face_Human_Bench_ICLR.pdf", "folder": "Face_Human_Bench_ICLR"}],
  "retag": [{"paper": "长视频理解/TimeSpot"}]
}
```

- `domains` is the complete convention after the plan: every domain folder that remains must appear, in the order the file lists them. A domain listed with no papers is allowed.
- `renames` moves every paper of `from` into `to`; when `to` already exists, the two merge.
- `moves` names papers by their id before the plan; `to` is a final domain.
- `flatten` moves the files of a `nested_folder` up into its paper folder.
- `wrap` puts a `loose_file` into a new paper folder `folder` in the same domain; a later `moves` entry may name `<domain>/<folder>`.
- `retag` normalizes the tags of a paper that does not move. Moved papers are normalized anyway.
- A paper id in `representative_papers` is its id before the plan, and must have a note.
- Every list but `domains` may be omitted.

**Normalizing tags.** In each note with frontmatter, the `tags` field ends with the domain tag first. The tag of the folder the paper leaves is dropped; each other `papers/X` tag becomes the topic tag `X`, unless present already. Other tags keep their order. A note without frontmatter is left unchanged.

**Links.** After the moves, every `[[…]]` or `](…)` link target in the vault's `.md` files that starts with a moved path's old vault-relative path is rewritten to the new path. `%20` stays encoded. Links by file name alone are untouched.

**Removed folders.** A domain folder left with no entries but hidden files is removed.

## `organize.py`

`preview --plan plan.json` writes nothing. Output: `status` (`ok` or `refused`), `plan_digest`, `summary` (`domains_created`, `domains_removed`, `moves`, `flattens`, `wraps`, `tag_edits`, `link_edits`), `moves` (`[{paper, from, to}]`), `edits` (`[{path, kinds}]`), `domains_file` (`path`, `exists`, `text`, `diff`), `warnings`, and `errors`.

`apply --plan plan.json --expected-digest <plan_digest>` recomputes the preview and refuses when the digest differs, because the library or the plan changed after preview. It holds `<vault>/.deeppapernote.lock`, the lock DeepPaperNote takes when it saves. On success it writes the log and reports `log` and `verify`.

`undo --latest` reverses the newest log that is not undone yet. It first checks every step: an edited file must still have its post-apply hash, a moved folder must still be at its destination with its origin free. With any conflict it changes nothing and lists them.

`verify` checks the library against the newest log: moved folders in place, no link left on an old path, conforming tags in every touched note, and a domains file that lists every domain folder.

A refusal is `{"status": "refused", "errors": […]}` with exit code 1. The refusals are:
- an unknown paper, folder, or file;
- a target domain missing from `domains`;
- a remaining domain folder missing from `domains`;
- a new domain name with characters other than letters, digits, `_`, `-`, or only digits;
- a destination that exists;
- a representative paper without a note;
- a plan digest that differs at apply.

## Log

`<vault>/DeepPaperNote/organize-log/<YYYYMMDD-HHMMSS>.json`:

```json
{
  "schema_version": 1, "created": "2026-11-07T21:30:00", "papers_dir": "Research/Papers",
  "plan_digest": "…", "undone": false,
  "steps": [
    {"kind": "mkdir", "path": "Research/Papers/社会智能"},
    {"kind": "move", "from": "Research/Papers/大模型/Social_Code", "to": "Research/Papers/社会智能/Social_Code"},
    {"kind": "edit", "path": "Research/Papers/社会智能/Social_Code/Social_Code.md", "before_text": "…", "after_sha256": "…"},
    {"kind": "rmdir", "path": "Research/Papers/大模型"}
  ]
}
```

Paths are vault-relative. `edit` covers notes, linking files, and the domains file; `before_text` is `null` for a file the plan created.
