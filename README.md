<div align="center">

# DeepPaperNote

**Turn a complex paper into an Obsidian note you will actually want to keep.**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![Homepage](https://img.shields.io/badge/homepage-online-2563eb)](https://917dhj.github.io/DeepPaperNote/)
[![Status](https://img.shields.io/badge/status-stable-16a34a)](https://github.com/917Dhj/DeepPaperNote)
[![Release](https://img.shields.io/github/v/release/917Dhj/DeepPaperNote?display_name=tag&color=0f766e)](https://github.com/917Dhj/DeepPaperNote/releases/tag/v2.0.0)
[![License](https://img.shields.io/badge/license-MIT-c9a227)](./LICENSE)
[![Agents](https://img.shields.io/badge/agents-Claude%20Code%20%2B%20Codex-7c3aed)](./skills/deeppapernote/SKILL.md)
[![Output](https://img.shields.io/badge/output-Obsidian-16a34a)](./skills/deeppapernote/references/obsidian-format.md)
[![Figures](https://img.shields.io/badge/figures-image--first-f59e0b)](./skills/deeppapernote/references/figure-placement.md)
[![Changelog](https://img.shields.io/badge/changelog-latest-0f766e)](./CHANGELOG.md)

</div>

[![DeepPaperNote Hero](./assets/hero-academic.svg)](https://917dhj.github.io/DeepPaperNote/)

**Do you often run into this situation: you want to study a classic paper carefully, but the hardest part is no longer reading it — it is turning that reading into usable notes?** The real time sink usually looks like this:

- jumping back and forth between PDFs, Zotero, web pages, and your note app
- manually organizing metadata, abstracts, figures, and the method backbone
- understanding part of the paper, but still spending a long time turning that understanding into structured notes
- ending up with a note that looks complete but is not something you actually want to revisit later

DeepPaperNote is built for exactly that layer of repetitive, mechanical, but very expensive work. It takes over the gathering, structuring, figure placement, and note production work so you can keep your attention on actual thinking.

DeepPaperNote is a skill for **deep paper reading**. The same core skill can be used from Claude Code and Codex. It cares about a harder set of questions:

- What problem is this paper actually solving?
- How does the mechanism really work?
- Are the key equations, experiments, and figure context preserved?
- Does the final note become something worth keeping in your long-term knowledge base?

> [!tip]
> If you already have an Obsidian or Zotero workflow, DeepPaperNote automates the most tedious parts of evidence gathering, structuring, and note production.

## 🎯 What problems does it solve?

![DeepPaperNote usage example](./assets/usage-example.png)

| 🎯 Your need / pain point | ✅ What DeepPaperNote does |
| --- | --- |
| You want to understand a complex paper faster | It organizes the method backbone, key results, figure context, and limitations into a note you can actually read through |
| You want to study a classic paper without handwriting a pile of mechanical notes | It handles metadata collection, structure building, figure placeholders, and full note generation so you can spend your energy on understanding |
| You want the paper to live inside Obsidian as a long-term asset | It files the paper into a domain-appropriate place inside your Obsidian knowledge base, then creates a paper-specific folder, Markdown note, and local `images/` directory |
| You already manage papers in Zotero and do not want to redo the work | It can prefer local records and attachments, reducing mismatches and often speeding the workflow up |
| You do not want another polished-looking summary | It leans toward mechanism breakdown, key numbers, formulas, edge cases, and honest limitations |

**In one sentence:**

> DeepPaperNote is a paper-reading-note workflow, not a paper-summary generator.

## ✨ How does it do that?

DeepPaperNote does not achieve higher note quality by simply rewriting the abstract in smoother prose. It raises note quality through a few workflow rules:

| 🧭 Core principle | 📝 What it means in practice |
| --- | --- |
| 🤖 Model-led understanding | The model is responsible for mechanism breakdown, method structure, key comparisons, and limitations instead of template-like summary writing. |
| 🗂️ Evidence first | It gathers evidence from PDFs, metadata sources, and optional Zotero workflows before writing. The note captures the full evidence chain: what the paper proves, what remains unproven, which experiments matter, where negative or limiting results appear, and how conclusions are bounded. |
| 🧪 Technical detail first | For technical papers, it tries to preserve key numbers, formulas, implementation logic, and real boundary conditions rather than stopping at high-level paraphrase. |
| 📄 Paper-type-aware writing | Different paper types receive different reading strategies. Method papers, benchmark and dataset papers, survey papers, and empirical papers each receive focused treatment of the aspects that matter most for that type. |
| 📊 Clear result tables | When a paper compares multiple models, datasets, tasks, settings, or metrics, DeepPaperNote turns the central comparison into compact Markdown tables and follows them with interpretation of what the numbers actually mean. |
| 🖼️ Image-first figures | When a figure candidate is usable and has a valid image path, it is inserted as a real image. Placeholders are reserved for real failures: missing candidates, visual defects, contamination, truncation, or identity mismatch. |
| 🔗 Native knowledge-base output | It first routes the paper into a domain-appropriate place in your existing knowledge-base structure, then creates a paper folder with YAML properties, a fixed core metadata block, a stable `images/` directory, and clean figure/table embeds. |
| 📚 Local-library-first resolution | If the paper already exists in Zotero, it can reuse local items and attachments, which is often both more reliable and faster. |

## 👀 Who It Is For

<table>
  <tr>
    <td valign="top" width="33%">
      <strong>👓 People studying hard or classic papers closely</strong><br><br>
      You are not reading papers just to skim the abstract and move on. You are reading papers with dense formulas, complex architectures, or layered experiments, and you want a note that actually untangles the method backbone, key results, and figure structure.
    </td>
    <td valign="top" width="33%">
      <strong>🗂️ People building a long-term Obsidian knowledge base</strong><br><br>
      You want paper notes to remain searchable, linkable, and reusable over time. DeepPaperNote files papers into a more suitable place based on their domain, then creates the Markdown note and <code>images/</code> folder so the result fits a real knowledge base.
    </td>
    <td valign="top" width="33%">
      <strong>🤖 People who want more than AI summaries</strong><br><br>
      You are not looking for a polished-looking recap. You want to know what the paper actually solves, how the method works, which results matter, and where the real limitations or misunderstandings are. DeepPaperNote aims closer to a research note than a summary generator.
    </td>
  </tr>
</table>

## 🚀 Quick Start

### 1) Install DeepPaperNote into your agent skill directory

DeepPaperNote supports both Claude Code and Codex.

#### npx Skills (Recommended)

For most users, install directly with npx. Run in your terminal:

```bash
npx skills add 917Dhj/DeepPaperNote --skill deeppapernote
```

This command installs the `deeppapernote` skill from the DeepPaperNote plugin repository. Skills in the shared `.agents/skills` directory can be recognized and used by Codex and most other agents. If you also want to use DeepPaperNote in Claude Code, choose Claude Code in the **Additional agents** prompt.

You can also install for a specific agent directly:

```bash
npx skills add 917Dhj/DeepPaperNote --skill deeppapernote -a codex
npx skills add 917Dhj/DeepPaperNote --skill deeppapernote -a claude-code
```

##### Update

To update an existing DeepPaperNote installation, rerun the same command; it will replace the copy in the target skill directory.

#### Manual install

If you prefer the manual path, download the latest [release](https://github.com/917Dhj/DeepPaperNote/releases) zip and extract it.

For Codex, place the extracted `skills/deeppapernote` folder into:

```bash
~/.codex/skills/deeppapernote
```

For Claude Code, place the extracted `skills/deeppapernote` folder into:

```bash
~/.claude/skills/deeppapernote
```

If you clone the source repository directly, install the skill directory from the checkout:

```bash
git clone https://github.com/917Dhj/DeepPaperNote.git
cp -R DeepPaperNote/skills/deeppapernote ~/.codex/skills/deeppapernote
cp -R DeepPaperNote/skills/deeppapernote ~/.claude/skills/deeppapernote
```

After installation, restart your agent so the skill is loaded.

### 2) Install the core Python dependency

Before your first real paper run, install the most important Python dependency:

```bash
python3 -m pip install PyMuPDF
```

Why this step matters:

- DeepPaperNote reads PDFs through `PyMuPDF`
- if `PyMuPDF` is missing, the core PDF extraction pipeline will not work

### 3) Start using it immediately

After that, just hand a paper to the agent. A title, DOI, URL, arXiv ID, or local PDF all work. Prompts like these are enough:

Typical prompts:

- `Generate a deep-reading note for this paper: Attention Is All You Need`
- `Turn this paper into an Obsidian note: https://arxiv.org/abs/1706.03762`
- `Read this PDF and produce a Markdown note with figure context`
- `Use DeepPaperNote on this paper: 10.48550/arXiv.1706.03762`

By default, DeepPaperNote writes the note in **Chinese**. At the moment, Chinese is the only note language that can fully benefit from the skill's current writing and linting rules. If you need English notes, please stay tuned for a future update.

By default, DeepPaperNote will:

- resolve the paper identity
- gather metadata and PDF evidence
- insert figures directly when usable; keep placeholders only for real failures such as missing candidates, visual defects, or copy errors
- generate the final Markdown note
- save it into Obsidian when configured, or ask for your vault path before falling back to the current workspace's output folder

### 4) You do not need perfect setup on day one

You can try DeepPaperNote even if you have not finished configuring Obsidian, Zotero, or OCR yet.

If you want the Python dependencies for local development:

```bash
python3 -m pip install -e '.[dev]'
```

If you want to check the environment first, you can also ask the agent with short requests such as:

- `Please check whether DeepPaperNote is ready on this machine`
- `查看 deeppapernote 的可用情况`
- `deeppapernote 有什么功能`

## 🔧 Configuration (works out of the box, improves with setup)

Once you have PyMuPDF installed, you're ready to start generating notes with DeepPaperNote right away. The configurations outlined below are extensions of the core features, designed to help you seamlessly integrate the generated notes into your actual research workflow.

- if no Obsidian vault is configured, it can still save notes under the current workspace's fallback output folder, `DeepPaperNote_output` by default
- if you want an Obsidian-native long-term workflow, you should configure your vault path
- everything else in this section is optional and improves specific workflows

### Core setup: point DeepPaperNote to your Obsidian vault

The cleanest setup is:

```bash
export DEEPPAPERNOTE_OBSIDIAN_VAULT="/absolute/path/to/your/Obsidian_Documents"
```

If you want your agent to keep seeing this default configuration in future terminal sessions:

- on macOS / Linux, add it to your shell config such as `~/.zshrc`, then reload your shell (or restart the agent):

```bash
echo 'export DEEPPAPERNOTE_OBSIDIAN_VAULT="/absolute/path/to/your/Obsidian_Documents"' >> ~/.zshrc
source ~/.zshrc
```

- on Windows PowerShell, persist it as a user environment variable and then restart your terminal:

```powershell
setx DEEPPAPERNOTE_OBSIDIAN_VAULT "C:\Users\YourName\Documents\Obsidian_Documents"
```

<details>
<summary><strong>🛠️ Show advanced configuration (directories / Zotero / Semantic Scholar / OCR)</strong></summary>

### Directory-related settings

If you want to customize paper output paths or intermediate artifact paths:

```bash
export DEEPPAPERNOTE_PAPERS_DIR="Research/Papers"
export DEEPPAPERNOTE_OUTPUT_DIR="tmp/DeepPaperNote"
```

| ⚙️ Variable | Required | 📝 Purpose |
| --- | --- | --- |
| `DEEPPAPERNOTE_OBSIDIAN_VAULT` | Recommended | Root path of your Obsidian vault |
| `DEEPPAPERNOTE_PAPERS_DIR` | Optional | Vault-relative paper output folder, default: `Research/Papers` |
| `DEEPPAPERNOTE_OUTPUT_DIR` | Optional | Local temporary artifact directory, default: `tmp/DeepPaperNote` |
| `DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR` | Optional | Fallback output folder under the current working directory when no Obsidian vault is configured, default: `DeepPaperNote_output` |

If you want your agent to keep using these values by default:

- on macOS / Linux, add them to your `~/.zshrc` as well:

```bash
echo 'export DEEPPAPERNOTE_PAPERS_DIR="Research/Papers"' >> ~/.zshrc
source ~/.zshrc
```

- on Windows PowerShell, persist them as user environment variables:

```powershell
setx DEEPPAPERNOTE_PAPERS_DIR "Research/Papers"
```

Why the optional path settings can help:

- `DEEPPAPERNOTE_PAPERS_DIR`
  Useful if your vault does not store papers under `Research/Papers`, or if you want DeepPaperNote to fit an existing folder convention without extra manual moves.
- `DEEPPAPERNOTE_OUTPUT_DIR`
  Useful if you want all intermediate artifacts in a predictable location for debugging, cleanup, or experimentation.

Domain routing is controlled by the editable taxonomy in `skills/deeppapernote/references/domain_rules.yaml`. DeepPaperNote checks application domains before fallback method domains, and it only reuses an existing first-level Obsidian folder when the title or abstract provides conservative evidence for that folder.

### Optional: Zotero for local-library-first workflows

DeepPaperNote can work without Zotero.
If you already keep papers in Zotero, DeepPaperNote now has a built-in, read-only integration with the desktop [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api). It queries only the loopback API at `127.0.0.1:23119`, requires no API key or third-party Python package, and never reads the Zotero SQLite database directly.

This is most worth setting up if you already use Zotero as your main paper-management or reading workflow.

To enable it:

1. Keep the Zotero desktop app running.
2. In Zotero, enable **Settings → Advanced → Allow other applications on this computer to communicate with Zotero**.

DeepPaperNote probes the Local API automatically during paper resolution. Its `--zotero-mode` policy has three options:

| Mode | Behavior |
| --- | --- |
| `auto` (default) | Prefer a unique local item; retain web fallback for title, DOI, and arXiv queries when Zotero is unavailable or has no match |
| `off` | Make no Zotero Local API request and preserve the previous resolution path |
| `required` | Stop unless Zotero uniquely resolves the reference; a missing local PDF does not invalidate confirmed Zotero metadata |

An ambiguous local match always fails closed instead of choosing an arbitrary item. An explicit Zotero key also fails closed when it cannot be verified locally because it has no safe web fallback. Explicit local PDFs and trusted JSON artifacts bypass the lookup in every mode.

Compatible agent-runtime or MCP integrations remain optional alternatives:

| 🧩 Option | 🎯 Best for | 📝 Notes |
| --- | --- | --- |
| Built-in Local API | Normal local-library-first use | Recommended path; read-only, offline-capable, no API key, and no extra integration layer |
| [kujenga/zotero-mcp](https://github.com/kujenga/zotero-mcp) | Lightweight read access | Closer to a minimal Zotero MCP server for search, metadata, and text access, but it usually still needs some adaptation for your agent runtime |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) | Richer research workflow features | More feature-rich, but stable use usually still requires some integration work on your side |

Why it matters:

- local Zotero hits are usually the best identity anchor
- if the paper is already in your local Zotero library, DeepPaperNote can often reuse local records and attachments instead of searching and downloading again, which also tends to make note generation faster
- the agent can prefer your local paper library before internet search
- local attachments can reduce wrong-title matches
- it is especially helpful when you already curate papers in Zotero and do not want DeepPaperNote to rediscover the same paper from weaker web matches
- it also improves reliability for published papers whose title may collide with preprints, workshop versions, or mirrored pages

Important note:

- the built-in client sends only read-only `GET` requests and does not expose or forward Zotero's unauthenticated loopback port
- the built-in client currently targets the logged-in user's personal library; group-library select links are rejected instead of silently querying the wrong library
- no local PDF is required for a successful Zotero identity match; DeepPaperNote can keep the confirmed metadata and use its normal PDF acquisition fallback
- third-party runtime integrations are **not** always plug-and-play and are not required by the built-in workflow

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
- it is **not** used to understand images directly

Without OCR, DeepPaperNote still works well on normal digital PDFs. For scanned or low-quality PDFs, if extracted evidence is too weak for a real deep note, the workflow should ask for OCR or a better source rather than finishing a lower-quality output.

Required software and packages for OCR:

| 🧱 Layer | 📦 Requirement | 📝 Purpose |
| --- | --- | --- |
| System tool | `tesseract` | The actual OCR engine |
| Python package | `pytesseract` | Python bridge to `tesseract` |
| Python package | `Pillow` | Opens rendered page images before OCR |

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

| 🏷️ Version | 🚦 Status | ✨ Highlights |
| --- | --- | --- |
| v2.0.0 | ✅ Released | Major upgrade for deeper evidence-first notes, raw-source grounding, paper-type-aware writing, and more reliable figure/table handling |
| v1.1.1 | ✅ Released | Patch release tightening figure placeholder validation and table crop quality checks |
| v1.1.0 | ✅ Released | Major figure/table extraction upgrade with caption-anchored crops, visual quality gates, and placeholder-first figure asset candidates |
| v1.0.1 | ✅ Released | Patch release for Obsidian-native frontmatter formatting, lint compatibility fixes, and cleaner README assets |
| v1.0.0 | ✅ Released | First stable release: pure cross-agent skill structure for Claude Code, Codex, Cursor, Copilot, Gemini CLI, and other Agent Skills-compatible environments |
| v0.3.1-alpha | ✅ Released | Default Obsidian paper root changed to `Research/Papers`, with runtime path resolution and save behavior aligned to the new location |
| v0.3.0-alpha | ✅ Released | Major quality upgrade: dedicated innovation section, explicit mechanism flow, stronger workflow discipline, final readability review, math syntax gate, and the new `Original Abstract Translation` front-matter block |
| v0.2.0-alpha | ✅ Released | Replication-oriented note-writing upgrade: explicit `note_plan`, equation-aware output, stricter final self-review, bilingual abstract handling, and stronger formatting checks |
| v0.1.0-alpha | ✅ Released | First public alpha: evidence-bundle workflow, Zotero-first helpers, placeholder-first figure handling, workspace fallback, OCR fallback, tests, and CI |
| Unreleased | 🛠️ In development | Built-in read-only Zotero Local API resolution, safe attachment reuse, explicit lookup policies, and environment diagnostics |

## ⚙️ Workflow

DeepPaperNote resolves one paper, builds grounded source artifacts, lets the model plan and write the note, validates the result, and saves it into Obsidian. The canonical execution contract lives in [`SKILL.md`](./skills/deeppapernote/SKILL.md).

Core principle:

- scripts gather source text, metadata, assets, and quality signals
- the model understands and writes
- linting, final quality review, and final readability review are the final gates before saving

Related docs:

- [Architecture](./skills/deeppapernote/references/architecture.md)

## 🖼️ Figure Strategy

DeepPaperNote treats figure insertion and placeholder decisions as two separate questions.

When a figure or table candidate is usable — the crop is visually clean, it matches the intended figure, and the image path is valid — it is inserted into the note as a real image embed.

Placeholders are reserved for real problems:

- no usable candidate was found
- the crop has visual defects, truncation, or contamination
- the image cannot be confirmed to match the intended figure
- the file copy or write step failed

When a placeholder is needed, DeepPaperNote keeps the semantic position, explanation, and context so the note structure stays intact and you know which figure belonged there:

```md
> [!figure] Fig. 3 Data Distribution and Quality Evaluation
> Suggested location: Data and task definition
> Why here: This figure combines sample composition, conversation-length statistics, and expert quality checks, making it one of the most important figures for understanding the data boundaries.
> Current status: Placeholder kept; current extraction only recovered partial subpanels and cannot yet reconstruct the full original figure reliably.
```

See [figure placement rules](./skills/deeppapernote/references/figure-placement.md).

## ✅ Quality Bar

DeepPaperNote has a concrete bar for what counts as a usable note.

The final note should:

- clearly separate the research question and the task definition
- explain the real method or analytical pipeline
- capture the numbers that actually matter
- cover key experimental settings and conditions
- distinguish what the evidence proves from what it does not prove
- point out where the paper is easiest to misread
- include at least one honest limitation with bounded conclusions
- include at least one reusable research or engineering takeaway
- use real heading structure: `#`, `##`, `###`
- avoid mixed Chinese-English prose in the body

If the evidence is not strong enough, the workflow should degrade gracefully or fail instead of pretending that a deep reading note is complete.

Related docs:

- [Evidence First](./skills/deeppapernote/references/evidence-first.md)
- [Deep Analysis](./skills/deeppapernote/references/deep-analysis.md)
- [Note Quality](./skills/deeppapernote/references/note-quality.md)
- [Final Writing](./skills/deeppapernote/references/final-writing.md)
- [Figure Placement](./skills/deeppapernote/references/figure-placement.md)

## 🗂️ Repository Layout

```text
DeepPaperNote/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── README.md
├── README.zh-CN.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── assets/
│   ├── hero-academic.svg
│   └── usage-example.png
├── skills/
│   └── deeppapernote/
│       ├── SKILL.md
│       ├── agents/
│       │   └── openai.yaml
│       ├── references/
│       └── scripts/
└── tests/
```

## 🧰 Recommended Environment

| 🧰 Component | 🚦 Status | 📝 Notes |
| --- | --- | --- |
| Claude Code / Codex | Recommended | Supported agent environments |
| Python 3.10+ | Required | Runs the helper scripts |
| PyMuPDF | Required | Core PDF dependency; install it with `python3 -m pip install PyMuPDF` |
| Local Obsidian vault | Recommended | Writes directly into a long-term note system; otherwise uses the current workspace's fallback output folder |
| Zotero Local API / compatible integration | Optional | Reuses local metadata and PDF attachments before web resolution |
| OCR tools | Optional | Improves handling of scanned PDFs |

## 🧭 Design Principles

The core judgment behind DeepPaperNote is simple:

1. **A good paper note is not just a paragraph-style summary.**

A useful note should help you understand:

- how the method works
- where the evidence comes from
- what the experiments actually show
- what the real boundaries and limitations are

2. **The goal of paper reading is a reusable research asset.**

Not just “I kind of get it right now,” but something you can revisit, cite, and build on later.

3. **Note generation should serve a real research workflow.**

That is why it is designed to fit naturally with:

- Obsidian
- Zotero
- local paper management
- long-term knowledge-base building

## 🧭 Inspirations

DeepPaperNote was influenced by projects that take paper reading, evidence extraction, and note generation seriously, especially:

- [heleninsights-dot/phd-deepread-workflow](https://github.com/heleninsights-dot/phd-deepread-workflow)
- [juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv)

## 🤝 Contributing

DeepPaperNote is developed on the `develop` branch. Please open pull requests against `develop`, not `main`.

For changes that may affect note quality, the PR should be evaluated with the workflow and rubric in `evals/`:

- [`evals/regression-workflow.md`](./evals/regression-workflow.md)
- [`evals/note-quality-rubric.md`](./evals/note-quality-rubric.md)

I only accept note-quality-related changes when they show a real improvement under the evaluation workflow. Cleaner formatting, broader abstractions, or internal refactors are not enough by themselves unless they materially improve the final generated note.

## Star History

<a href="https://www.star-history.com/?repos=917Dhj%2FDeepPaperNote&type=date&legend=top-left">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="https://api.star-history.com/image?repos=917Dhj/DeepPaperNote&type=date&theme=dark&legend=top-left"
    />
    <source
      media="(prefers-color-scheme: light)"
      srcset="https://api.star-history.com/image?repos=917Dhj/DeepPaperNote&type=date&legend=top-left"
    />
    <img
      alt="Star History Chart"
      src="https://api.star-history.com/image?repos=917Dhj/DeepPaperNote&type=date&legend=top-left"
    />
  </picture>
</a>

<p align="center">
  <em>Thanks for reading, using, and supporting DeepPaperNote. May your paper-reading days be a little clearer, calmer, and more rewarding.</em>
</p>

<p align="center">
  <a href="./LICENSE">MIT License</a> &copy; <a href="https://github.com/917Dhj">917Dhj</a>
</p>
