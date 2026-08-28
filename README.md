<div align="center">

# DeepPaperNote

**Turn one complex paper into an Obsidian note you will actually want to keep.**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![Homepage](https://img.shields.io/badge/homepage-online-2563eb)](https://917dhj.github.io/DeepPaperNote/)
[![Status](https://img.shields.io/badge/status-stable-16a34a)](https://github.com/917Dhj/DeepPaperNote)
[![Release](https://img.shields.io/github/v/release/917Dhj/DeepPaperNote?display_name=tag&color=0f766e)](https://github.com/917Dhj/DeepPaperNote/releases)
[![License](https://img.shields.io/badge/license-MIT-c9a227)](./LICENSE)
[![Agents](https://img.shields.io/badge/agents-Claude%20Code%20%2B%20Codex-7c3aed)](./skills/deeppapernote/SKILL.md)
[![Output](https://img.shields.io/badge/output-Obsidian-16a34a)](./skills/deeppapernote/references/obsidian-format.md)
[![Changelog](https://img.shields.io/badge/changelog-latest-0f766e)](./CHANGELOG.md)

</div>

[![DeepPaperNote Hero](./assets/hero-academic.svg)](https://917dhj.github.io/DeepPaperNote/)

<p align="center">
  <em>Read one paper deeply. Add one durable page to your academic wiki.</em>
</p>

**Do you know this situation? You sit down to study an important paper, but the exhausting part is not simply reading it. It is turning what you understood into a note you can still use later.** The time usually disappears into work like this:

- switching between the PDF, Zotero, web pages, and your note app
- manually organizing metadata, the abstract, figures, and the method backbone
- understanding part of the paper, then spending even longer turning that understanding into a coherent note
- ending up with something that looks complete but is not a note you actually want to revisit

DeepPaperNote takes over that repetitive, mechanical, and surprisingly expensive layer of paper reading. It gathers the material, builds the structure, places figures in context, and shapes the final note so you can keep your attention on the paper's real ideas.

In other words, you can think of DeepPaperNote as the **single-paper ingestion layer for an LLM-maintained academic wiki**: it reads one paper deeply and turns its research question, methods, evidence, results, and figures into a durable page that people can read and agents can reuse. Obsidian is where those pages live, connect, and grow; DeepPaperNote is how a paper reliably enters the wiki.

DeepPaperNote is an agent skill for reading **one paper at a time**. The same core skill runs in Claude Code and Codex, and it focuses on the questions that distinguish a deep-reading note from an abstract rewrite:

- What problem is the paper actually solving?
- How does the method, system, or analytical mechanism really work?
- Are the key formulas, experimental conclusions, and figure context preserved?
- Will the result become a useful long-term Obsidian note rather than a disposable summary?

> [!tip]
> If you already use Obsidian or Zotero, DeepPaperNote automates the most time-consuming and error-prone parts of evidence gathering, organization, and note production.

## 📰 News

- **[2026-07-16]** 🧩 Added [`paper-glossary`](./skills/paper-glossary/README.md), an optional companion skill for building reusable Obsidian terminology notes.
- **[2026-07-16]** 🔌 DeepPaperNote is now distributed as a plugin for multiple agents, with support for selecting multiple skills from the repository. [PR #12](https://github.com/917Dhj/DeepPaperNote/pull/12)
- **[v2.0.0]** 🚀 Released a deeper evidence-first paper-reading workflow with stronger note planning and figure handling. [Release notes](https://github.com/917Dhj/DeepPaperNote/releases/tag/v2.0.0)

News lists only the three most recent user-facing milestones. See the [changelog](./CHANGELOG.md) and [GitHub Releases](https://github.com/917Dhj/DeepPaperNote/releases) for the full history.

## 🚀 Quick Start

### 1. Install the plugin

```bash
npx skills add 917Dhj/DeepPaperNote
```

The installer lets you choose which skills to install and which agents should receive them. For most users, start with `deeppapernote`; add `paper-glossary` only if you want reusable terminology notes.

### 2. Install the core PDF dependency

```bash
python3 -m pip install PyMuPDF
```

DeepPaperNote requires Python 3.10 or newer. `PyMuPDF` powers the core PDF extraction path.

### 3. Hand a paper to your agent

A title, DOI, URL, arXiv ID, or local PDF all work. Zotero items are also supported when a compatible integration is available.

```text
Generate a deep-reading note for this paper: <title, DOI, URL, arXiv ID, or local PDF>
Turn this paper into an Obsidian note: <paper>
```

DeepPaperNote supports complete English and Simplified Chinese note schemas. A complete set of inherited `DEEPPAPERNOTE_*` environment variables starts the run without reading `~/.deeppapernote/config.json`; otherwise your Agent uses that file as a fallback and asks only for unresolved fields.
The User Configuration section below covers both save modes, both language profiles, and one-run overrides. Section names, metadata fields, figure callouts, planning guidance, linting, and Formal Save all follow the resolved language.

## 🎯 Why DeepPaperNote?

![DeepPaperNote usage example](./assets/usage-example.png)

| You may be dealing with... | DeepPaperNote helps by... |
| --- | --- |
| 📄 **You finished the paper, but your notes are still a pile of fragments** | Rebuilding the research question, method chain, central experiments, and limitations into one note you can actually read again |
| 🧠 **You do not want another polished-looking AI summary** | Preserving the formulas, numbers, figure context, and evidence boundaries that make the paper worth understanding |
| 🗂️ **You keep reading papers, but they never become your academic wiki** | Turning each paper into a searchable, linkable, reusable Obsidian knowledge page so your academic wiki grows one paper at a time |
| 📚 **The paper is already in Zotero, and you do not want to match or download it again** | Preferring local records and attachments when available, reducing repeated work and paper mismatches |

## 🧩 Skills

DeepPaperNote remains the main product. The repository also includes an optional companion skill that works from DeepPaperNote's saved paper artifacts without taking over or rerunning the paper-reading workflow.

| Skill | Role | When to use it |
| --- | --- | --- |
| [`deeppapernote`](./skills/deeppapernote/SKILL.md) | **Core product · recommended** | Read one paper deeply and produce a structured, evidence-based Obsidian note with figures, results, and limitations |
| [`paper-glossary`](./skills/paper-glossary/SKILL.md) | Optional companion | Select terms from existing paper artifacts, create reusable Obsidian glossary notes, and optionally link them back to the paper note |

You do not need to install every skill. Choose the ones that match your workflow during installation.

## ✅ Quality Promise

- The result should be a deep-reading note for one paper, not an abstract rewrite.
- Important methods, experimental results, figures, and limitations should be explained rather than merely listed.
- If the available source is not strong enough for a real deep read, the workflow should stop and ask for better material instead of pretending the note is complete.

The canonical execution contract lives in [`skills/deeppapernote/SKILL.md`](./skills/deeppapernote/SKILL.md).

## 🗂️ User Configuration

DeepPaperNote can run entirely from current-process environment variables. It also stores optional durable device-local preferences in `~/.deeppapernote/config.json` for fallback values and explicit future defaults.

| Field | Valid values | When required |
| --- | --- | --- |
| `output_language` | `zh-CN` or `en` | Always |
| `save_mode` | `workspace` or `obsidian` | Always |
| `obsidian_vault` | Existing absolute directory | Only for `obsidian` |
| `papers_dir` | Safe relative path inside the Vault | Only for `obsidian` |

An English workspace configuration needs only the two always-required fields:

```bash
export DEEPPAPERNOTE_OUTPUT_LANGUAGE=en
export DEEPPAPERNOTE_SAVE_MODE=workspace
```

The equivalent optional User Configuration is:

```json
{
  "output_language": "en",
  "save_mode": "workspace"
}
```

A Simplified Chinese Obsidian configuration also names the Vault and paper directory:

```bash
export DEEPPAPERNOTE_OUTPUT_LANGUAGE=zh-CN
export DEEPPAPERNOTE_SAVE_MODE=obsidian
export DEEPPAPERNOTE_OBSIDIAN_VAULT="/absolute/path/to/your/vault"
export DEEPPAPERNOTE_PAPERS_DIR="Research/Papers"
```

The equivalent optional User Configuration is:

```json
{
  "output_language": "zh-CN",
  "save_mode": "obsidian",
  "obsidian_vault": "/absolute/path/to/your/vault",
  "papers_dir": "Research/Papers"
}
```

Configuration is resolved before paper identity or other expensive paper work. DeepPaperNote first resolves the explicit request, CLI arguments, and current process environment. If those values form a complete valid configuration, the run proceeds without reading User Configuration. Otherwise the Agent reads `config.json` as fallback and presents one Configuration Prompt Batch only for unresolved fields; an unreadable fallback file fails closed instead of continuing.

Current-process environment values are first-class Run Overrides and never change the optional file. Shell startup files are consulted only as migration candidates when inherited values are incomplete and `config.json` is absent. Preference Changes preserve unknown JSON fields, and malformed JSON is backed up before confirmed replacement.

### Run Overrides and Preference Changes

Runtime values follow this exact precedence:

`explicit request > CLI > current process environment > User Configuration`

- “Generate this paper's note in English just this once” is a Run Override and leaves `config.json` byte-for-byte unchanged.
- “Generate this paper's note in Simplified Chinese just this once” is the corresponding `zh-CN` Run Override.
- “Change my default output language to English” is a Preference Change and updates the future default after confirmation.
- CLI options `--language`, `--save-mode`, `--vault`, and `--papers-dir` are Run Overrides. For example:

```bash
python3 skills/deeppapernote/scripts/run_pipeline.py --input '<paper>' --language en --save-mode obsidian --vault /absolute/path/to/vault --papers-dir Research/Papers
```

Workspace mode does not use `obsidian_vault` or `papers_dir` for that run, but it preserves those preferences for future Obsidian runs. Run Overrides never become Preference Changes automatically.

### Output Language Profiles and Formal Save

- `zh-CN` uses `核心信息`, `原文摘要翻译`, `创新点`, `一句话总结`, `研究问题`, `数据与任务定义`, `方法主线`, `关键结果`, `深度分析`, `局限`, `我的笔记`, and `引用`, with `机制流程` under the method section. Figure callouts use `建议位置：`, `放置原因：`, and `当前状态：`; a materialized-image caption begins with `论文原图编号：`.
- `en` uses `Core Information`, `Abstract`, `Contributions`, `One-Sentence Summary`, `Research Question`, `Data and Task Definition`, `Method`, `Key Results`, `Deep Analysis`, `Limitations`, `Research Notes`, and `References`, with `Mechanism Flow`. Figure callouts use `Suggested location:`, `Why it matters:`, and `Current status:`; a materialized-image caption begins with `Original paper item:`.

In either profile, Abstract faithfully renders the source abstract in the requested language; later contribution claims and interpretation stay in later sections. The same canonical Skill and one pipeline carry the chosen language through lint and Formal Save.

Formal Save writes the Markdown note and its paper-local `images/` directory to the selected workspace or Obsidian target. The `images/` directory remains part of the saved paper layout even when no image is inserted. A blocked save reports the existing target and never silently switches modes.

## 🔧 Optional Enhancements

None of these are required for ordinary digital PDFs.

| Enhancement | What it helps with |
| --- | --- |
| Zotero integration | Reuses local paper records and PDF attachments before searching online |
| Semantic Scholar API | Improves metadata lookup for papers that are difficult to resolve |
| OCR tooling | Recovers page text from scanned or low-quality PDFs |

### Zotero Local API

The built-in, read-only Zotero Local API integration supports three resolution modes:

- `auto` (default): prefer a unique local item and retain web fallback
- `off`: skip Zotero lookup
- `required`: stop unless Zotero uniquely resolves the reference

An ambiguous local match always fails closed instead of selecting an arbitrary item. Compatible agent-runtime or MCP integrations remain optional alternatives.

When one of these capabilities is needed, ask your agent to inspect the current environment and guide the setup for that machine.

## 🧭 Inspirations

DeepPaperNote was influenced by projects that take paper reading, evidence extraction, and note generation seriously, especially:

- [heleninsights-dot/phd-deepread-workflow](https://github.com/heleninsights-dot/phd-deepread-workflow)
- [juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv)

## 🤝 Contributing

Pull requests should target `develop`, not `main`. Changes that may affect final note quality should be evaluated with [`evals/regression-workflow.md`](./evals/regression-workflow.md) and [`evals/note-quality-rubric.md`](./evals/note-quality-rubric.md).

## Star History

[![Star History Chart](./assets/star-history.svg)](https://www.star-history.com/?repos=917Dhj%2FDeepPaperNote&type=date&legend=top-left)

<p align="center">
  <em>Thanks for reading, using, and supporting DeepPaperNote. May your paper-reading days be a little clearer, calmer, and more rewarding.</em>
</p>

<p align="center">
  <a href="./LICENSE">MIT License</a> &copy; <a href="https://github.com/917Dhj">917Dhj</a>
</p>
