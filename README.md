<div align="center">

# DeepPaperNote

**Turn a hard paper into an Obsidian note you will actually want to keep.**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![Status](https://img.shields.io/badge/status-alpha-2563eb?style=for-the-badge)](https://github.com/917Dhj/DeepPaperNote)
[![Release](https://img.shields.io/github/v/release/917Dhj/DeepPaperNote?display_name=tag&style=for-the-badge)](https://github.com/917Dhj/DeepPaperNote/releases/tag/v0.2.0-alpha)
[![License](https://img.shields.io/badge/license-MIT-475569?style=for-the-badge)](./LICENSE)
[![Codex](https://img.shields.io/badge/Codex-skill-111827?style=for-the-badge)](./SKILL.md)
[![Output](https://img.shields.io/badge/output-Obsidian-16a34a?style=for-the-badge)](./references/obsidian-format.md)
[![Figures](https://img.shields.io/badge/figures-placeholder--first-f59e0b?style=for-the-badge)](./references/figure-placement.md)
[![Writing](https://img.shields.io/badge/writing-model--first-7c3aed?style=for-the-badge)](./references/model-synthesis.md)
[![Changelog](https://img.shields.io/badge/changelog-latest-0f766e?style=for-the-badge)](./CHANGELOG.md)

</div>

![DeepPaperNote Hero](./assets/hero.svg)

When a paper is packed with dense formulas, crowded architecture diagrams, tangled experimental design, and pages of ablations, the problem is often not that the paper is unimportant. It is that the paper is simply hard to digest.

DeepPaperNote is a Codex skill for **deep paper reading**. It is not another tool that paraphrases the abstract and stops there. It cares about a harder set of questions:

- What problem is this paper actually solving?
- How does the mechanism really work?
- Are the key equations, experiments, and figure context preserved?
- Does the final note become something worth keeping in your long-term knowledge base?

**If you are tired of AI paper-summary tools that look complete but still leave you with nothing you would revisit a week later, this skill is probably for you.**

Let scripts handle the repetitive work. Save your attention for actual thinking.

> [!tip]
> If you already have an Obsidian or Zotero workflow, DeepPaperNote is not trying to replace it. It is trying to automate the most tedious parts of evidence gathering, structuring, and note drafting.

## ✨ Why DeepPaperNote?

Most paper-summary tools stop after producing a neat-looking abstract rewrite. DeepPaperNote cares about two harder questions: **did you actually understand the paper?** and **is the resulting note worth keeping?**

| Category | 😵 Typical paper-summary tool | ✅ DeepPaperNote |
| --- | --- | --- |
| 🎯 Output goal | A smooth-looking summary | A note you can revisit, reuse, and keep |
| 🔍 Focus | Abstract and high-level conclusions | Mechanisms, evidence, experiments, figure context, and structure |
| 🧪 Technical depth | Often stops at high-level paraphrase | Tries to preserve key numbers, formulas, implementation logic, and honest limitations |
| 🖼️ Figure handling | Easy to skip when extraction is unstable | Prioritizes figure placement and context so the note structure stays intact |
| 📚 Use case | Quick browsing | Deep reading, long-term note-taking, and Obsidian knowledge management |
| ♻️ Long-term value | Disposable reading aid | Reusable research note |

**In one sentence:**

> DeepPaperNote is a paper-reading-note workflow, not a paper-summary generator.

## 👀 Who It Is For

- People who regularly wrestle with hard, technical, cross-domain, or high-density papers
- People who often feel, "I know every word here, but I still do not understand the paragraph"
- People who do not want vague AI summaries and instead want to understand mechanisms, results, and boundaries
- People who want to build a reusable local paper-knowledge base in Obsidian

## 🚀 Quick Start

### 1) Install it into your Codex skills directory

Clone this repository into your Codex skills directory:

```bash
git clone https://github.com/917Dhj/DeepPaperNote.git ~/.codex/skills/DeepPaperNote
```

After installation, restart Codex so the skill is loaded.

### 2) Start using it immediately

After that, just hand a paper to Codex. A title, DOI, URL, arXiv ID, or local PDF all work. Prompts like these are enough:

Typical prompts:

- `Generate a deep-reading note for this paper`
- `Turn this paper into an Obsidian note`
- `Read this PDF and produce a Markdown note with figure context`
- `Use DeepPaperNote on this paper and keep the mechanism, key experiments, and figure context intact`

By default, DeepPaperNote writes the note in **Chinese**. At the moment, Chinese is the only note language that can fully benefit from the skill's current writing and linting rules. If you need English notes, please stay tuned for a future update.

By default, DeepPaperNote will:

- resolve the paper identity
- gather metadata and PDF evidence
- plan figure placeholders and attempt high-confidence figure replacement
- generate the final Markdown note
- save it into Obsidian when configured, or automatically fall back to the current directory

### 3) You do not need perfect setup on day one

You can try DeepPaperNote even if you have not finished configuring Obsidian, Zotero, or OCR yet.

If you want the Python dependencies for local development:

```bash
python3 -m pip install -e .
```

If you want to check the environment first, you can also ask Codex with short prompts such as:

- `/deeppapernote doctor`
- `/deeppapernote start`
- `查看 deeppapernote 的可用情况`
- `deeppapernote 有什么功能`

In that mode, DeepPaperNote should explain its capabilities, inspect the current setup, and tell you what is already configured or still missing.

If you want a more explicit onboarding prompt, see [ONBOARDING_PROMPT.md](./ONBOARDING_PROMPT.md).

## 🔧 Configuration (works out of the box, improves with setup)

DeepPaperNote can be tried with zero configuration.

- if no Obsidian vault is configured, it can still save notes into the current working directory
- if you want an Obsidian-native long-term workflow, you should configure your vault path
- everything else in this section is optional and improves specific workflows

### Core setup: point DeepPaperNote to your Obsidian vault

The cleanest setup is:

```bash
export DEEPPAPERNOTE_OBSIDIAN_VAULT="/absolute/path/to/your/Obsidian_Documents"
```

<details>
<summary><strong>🛠️ Show advanced configuration (directories / Zotero MCP / Semantic Scholar / OCR)</strong></summary>

### Directory-related settings

If you want to customize paper output paths or intermediate artifact paths:

```bash
export DEEPPAPERNOTE_PAPERS_DIR="20_Research/Papers"
export DEEPPAPERNOTE_OUTPUT_DIR="tmp/DeepPaperNote"
```

| Variable | Required | Purpose |
| --- | --- | --- |
| `DEEPPAPERNOTE_OBSIDIAN_VAULT` | Recommended | Root path of your Obsidian vault |
| `DEEPPAPERNOTE_PAPERS_DIR` | Optional | Vault-relative paper output folder, default: `20_Research/Papers` |
| `DEEPPAPERNOTE_OUTPUT_DIR` | Optional | Local temporary artifact directory, default: `tmp/DeepPaperNote` |
| `DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR` | Optional | Fallback output folder under the current working directory when no Obsidian vault is configured, default: `DeepPaperNote_output` |

Why the optional path settings can help:

- `DEEPPAPERNOTE_PAPERS_DIR`
  Useful if your vault does not store papers under `20_Research/Papers`, or if you want DeepPaperNote to fit an existing folder convention without extra manual moves.
- `DEEPPAPERNOTE_OUTPUT_DIR`
  Useful if you want all intermediate artifacts in a predictable location for debugging, cleanup, or experimentation.

### Optional: Zotero MCP for local-library-first workflows

DeepPaperNote can work without Zotero.
But if you want Codex to search your local Zotero library first, you should configure a Zotero MCP option that Codex can actually use.

This is most worth setting up if you already use Zotero as your main paper-management or reading workflow.

Recommended ways to think about it:

| Option | Best for | Notes |
| --- | --- | --- |
| [kujenga/zotero-mcp](https://github.com/kujenga/zotero-mcp) | Lightweight read access | Closer to a minimal Zotero MCP server for search, metadata, and text access, but not natively designed for Codex, so it usually still needs some adaptation |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) | Richer research workflow features | More feature-rich, but also not natively built for Codex, so using it well in Codex usually requires additional adaptation |

Why it matters:

- local Zotero hits are usually the best identity anchor
- if the paper is already in your local Zotero library, DeepPaperNote can often reuse local records and attachments instead of searching and downloading again, which also tends to make note generation faster
- Codex can prefer your local paper library before internet search
- local attachments can reduce wrong-title matches
- it is especially helpful when you already curate papers in Zotero and do not want DeepPaperNote to rediscover the same paper from weaker web matches
- it also improves reliability for published papers whose title may collide with preprints, workshop versions, or mirrored pages

Important note:

- DeepPaperNote does **not** require one specific Zotero MCP implementation
- for DeepPaperNote, the key capability is that Codex can search Zotero items, inspect metadata, and ideally read local full text
- the two routes above are **not** plug-and-play Codex-native options today, so stable use in Codex usually requires some adaptation on your side

### Optional: Semantic Scholar API key

This is not required, but if you have a Semantic Scholar API key you can expose it as:

```bash
export DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY="your_api_key"
```

Why it can help:

- metadata lookup is usually more stable when Semantic Scholar is available
- title-based paper resolution can be more reliable for hard-to-match papers
- author, venue, and abstract backfill may be more complete in some cases
- it gives DeepPaperNote one more strong source before falling back to weaker guesses

### Optional: OCR tooling for scanned PDFs

OCR is not required for many modern PDFs.
But it becomes useful when a paper is:

- a scanned PDF
- an image-based PDF with poor embedded text
- an older paper where direct text extraction is incomplete

Why DeepPaperNote uses OCR:

- to recover page text when direct PDF extraction is too weak
- to preserve method and results evidence that would otherwise be lost
- to improve page-level context around figures and captions

Current OCR logic in DeepPaperNote:

- DeepPaperNote first tries normal PDF text extraction with `PyMuPDF`
- for each page, it counts how much searchable text was extracted
- if a page has too little extracted text, it becomes an OCR fallback candidate
- OCR is then applied to that page only
- the recovered OCR text is mainly used as page context for later evidence handling and figure/page semantic matching

Important scope note:

- OCR is currently a **page-text fallback**
- it is **not** the primary extraction path for all PDFs
- it is **not** used as a replacement for model-side understanding
- it is **not** used to "understand images" directly

Without OCR, DeepPaperNote still works well on normal digital PDFs, but scanned or low-quality PDFs may produce weaker evidence.

Required software and packages for OCR:

| Layer | Requirement | Purpose |
| --- | --- | --- |
| System tool | `tesseract` | The actual OCR engine |
| Python package | `pytesseract` | Python bridge to `tesseract` |
| Python package | `Pillow` | Opens rendered page images before OCR |
| Existing PDF layer | `PyMuPDF` | Renders pages and extracts normal PDF text |

Install on macOS:

```bash
brew install tesseract
python3 -m pip install --user pytesseract Pillow
```

Install on Windows:

```powershell
winget install UB-Mannheim.TesseractOCR
py -m pip install --user pytesseract Pillow
```

If `winget` is unavailable, install Tesseract OCR manually and then run:

```powershell
py -m pip install --user pytesseract Pillow
```

Quick verification:

```bash
tesseract --version
python3 -c "import pytesseract, PIL; print('python_ok')"
python3 -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

</details>

## 📝 Changelog Preview

For release-level updates, see [CHANGELOG.md](./CHANGELOG.md).

| Version | Status | Highlights |
| --- | --- | --- |
| v0.2.0-alpha | ✅ Released | Replication-oriented note-writing upgrade: explicit `note_plan`, equation-aware output, stricter final self-review, bilingual abstract handling, and stronger formatting checks |
| v0.1.0-alpha | ✅ Released | First public alpha: Codex workflow, synthesis bundle pipeline, Zotero-first helpers, placeholder-first figure handling, workspace fallback, OCR fallback, tests, and CI |
| Unreleased | 🕒 No new release-level changes yet | There are currently no additional public release notes beyond v0.2.0-alpha |

## Why DeepPaperNote

Most paper-summary workflows stop too early:

- they overfit to the abstract
- they flatten technical details into generic bullets
- they silently skip figures when extraction is messy
- they produce notes that look neat but are not useful a week later

DeepPaperNote takes a different stance:

- scripts gather, structure, and verify evidence
- the model is responsible for understanding and writing
- figures follow a placeholder-first strategy
- textual correctness matters more than image completeness

It is not trying to produce “a summary of the paper.”
It is trying to produce **a research note worth keeping**.

## ⚙️ Workflow

The default path is:

1. resolve the paper identity
2. collect metadata
3. fetch a PDF or enough full-text evidence
4. extract evidence
5. extract PDF image assets
6. plan figure positions
7. build a synthesis bundle
8. let Codex/GPT write the note
9. lint the final note
10. write it into Obsidian

Core principle:

- scripts gather evidence
- the model understands and writes
- linting is the final gate before saving

Related docs:

- [Workflow](./references/workflow.md)
- [Architecture](./references/architecture.md)
- [Model Synthesis](./references/model-synthesis.md)

## 🖼️ Figure Strategy

DeepPaperNote uses a **placeholder-first** figure policy.

If a figure is important for understanding the paper, the note should keep a clear placeholder even when image extraction is incomplete.

Recommended placeholder format:

```md
> [!figure] Fig. 3 Data Distribution and Quality Evaluation
> Suggested location: Data and task definition
> Why here: This figure combines sample composition, conversation-length statistics, and expert quality checks, making it one of the most important figures for understanding the data boundaries.
> Current status: Placeholder kept; current extraction only recovered partial subpanels and cannot yet reconstruct the full original figure reliably.
```

Basic rule:

- images may be incomplete
- images may be temporarily missing
- text should remain as correct as possible

See [figure placement rules](./references/figure-placement.md).

## ✅ Quality Bar

DeepPaperNote has a concrete standard for what counts as a usable note.

The final note should:

- preserve the original paper identity and enough metadata to trace it later
- clearly separate the research question, task definition, method, results, and limitations
- avoid half-English / half-Chinese prose in Chinese mode
- preserve important figure context even when image replacement is incomplete
- feel worth keeping in a long-term knowledge base

See:

- [Note Quality](./references/note-quality.md)
- [Final Writing](./references/final-writing.md)
- [Figure Placement](./references/figure-placement.md)

## 🗂️ Repository Layout

```text
DeepPaperNote/
├── SKILL.md
├── README.md
├── README.en.md
├── README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
├── ONBOARDING_PROMPT.md
├── pyproject.toml
├── agents/
├── assets/
├── references/
├── scripts/
└── tests/
```

## 🧰 Current Status

| Area | Status | Notes |
| --- | --- | --- |
| Core single-paper workflow | ✅ Working | End-to-end paper → note path exists |
| Obsidian-native output | ✅ Working | Folder-per-paper with `images/` |
| Workspace fallback | ✅ Working | Works without an Obsidian vault |
| Zotero-first helper flow | ✅ Working | Optional, depends on user setup |
| OCR fallback | ✅ Working | Only for low-text PDF pages |
| Placeholder-first figures | ✅ Working | Real image replacement remains conservative |
| Tests | ✅ Minimal suite added | Core path, linting, and fallback checks |
| CI | ✅ GitHub Actions configured | Basic automated validation |

## 🧭 Inspirations

DeepPaperNote was influenced by projects that take paper reading, evidence extraction, and note generation seriously, especially:

- [heleninsights-dot/phd-deepread-workflow](https://github.com/heleninsights-dot/phd-deepread-workflow)
- [juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv)

The main difference is that DeepPaperNote deliberately keeps scripts focused on evidence handling, while leaving actual paper understanding and final note writing to the language model.

## 🚀 Roadmap

- strengthen note quality on hard technical papers
- improve high-confidence figure replacement
- expand tests and regression cases
- keep the core reusable even though the first public release targets Codex
