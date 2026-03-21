<div align="center">

# DeepPaperNote

**Turn one research paper into a high-quality Obsidian note you would actually keep.**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![Status](https://img.shields.io/badge/status-alpha-2563eb?style=for-the-badge)](https://github.com/917Dhj/DeepPaperNote)
[![Codex](https://img.shields.io/badge/Codex-first-111827?style=for-the-badge)](./SKILL.md)
[![Output](https://img.shields.io/badge/output-Obsidian-16a34a?style=for-the-badge)](./references/obsidian-format.md)
[![Figures](https://img.shields.io/badge/figures-placeholder--first-f59e0b?style=for-the-badge)](./references/figure-placement.md)
[![Writing](https://img.shields.io/badge/writing-model--first-7c3aed?style=for-the-badge)](./references/model-synthesis.md)
[![Changelog](https://img.shields.io/badge/changelog-latest-0f766e?style=for-the-badge)](./CHANGELOG.md)

</div>

![DeepPaperNote Hero](./assets/hero.svg)

DeepPaperNote is a **Codex-first agent skill** for a very specific workflow:

- read one paper carefully
- gather evidence from PDF, metadata sources, and optionally Zotero
- let the language model do the real interpretation
- write a polished Markdown note into an Obsidian vault

It is built for people who want something better than an abstract rewrite.

## Quick Start

1. Put this repository in your Codex skills directory:

   ```text
   ~/.codex/skills/DeepPaperNote
   ```

2. Restart Codex.

3. Trigger the skill with a paper title, DOI, arXiv ID, URL, Zotero item, or local PDF.

Typical prompts:

- `给这篇论文生成深度笔记`
- `把这篇文章整理成 obsidian 笔记`
- `读这篇论文并生成 md 笔记`

4. DeepPaperNote will:
   - resolve the paper identity
   - gather metadata and PDF evidence
   - build a synthesis bundle
   - let Codex/GPT write the final note
   - lint the note before writing it into Obsidian

## Why DeepPaperNote

Most paper-summary workflows stop too early:

- they overfit to the abstract
- they flatten technical details into generic bullets
- they silently skip figures when extraction is messy
- they produce notes that look neat but are not useful a week later

DeepPaperNote takes a different stance:

- `scripts` gather, normalize, and verify evidence
- Codex/GPT does the actual understanding and writing
- figure handling is `placeholder-first`
- text correctness matters more than image completeness

The goal is not "summarize a paper".
The goal is "produce a note you would actually keep in a serious research vault".

## ✨ What Makes It Different

| Feature | What it means in practice |
| --- | --- |
| Model-first understanding | Scripts do deterministic work and do **not** pretend to understand the paper better than the model. |
| Deep-reading notes | The note should reconstruct the paper's argument, not paraphrase the abstract. |
| Figure placeholder-first | Major figures and tables should stay in the note structure even when extraction is partial. |
| Obsidian-native output | Each paper gets its own folder with a note file and local `images/` directory. |
| Zotero-first | If the paper exists in local Zotero, use that as the most reliable identity anchor first. |

## ⚙️ How It Works

The default workflow is:

1. resolve the paper identity
2. collect metadata
3. acquire the PDF or strong full-text evidence
4. extract evidence
5. extract PDF image assets
6. plan figure placement
7. build a synthesis bundle
8. let Codex/GPT write the note
9. lint the final note
10. write it into Obsidian

Core principle:

- scripts gather evidence
- the model writes
- lint guards quality before save

See also:

- [Workflow](./references/workflow.md)
- [Architecture](./references/architecture.md)
- [Model Synthesis](./references/model-synthesis.md)

## 🖼️ Figure Strategy

DeepPaperNote uses a placeholder-first strategy.

If a major figure matters, the note should preserve it even when extraction is imperfect.

Preferred placeholder format:

```md
> [!figure] Fig. 3 数据分布与质量评估
> 建议位置：数据与任务定义
> 放置原因：这张图同时展示样本构成、对话长度统计和专家质检结果，是理解 `PsyInterview` 数据边界最重要的图之一。
> 当前状态：保留占位；当前提取结果只拿到局部子图，无法稳定恢复成可独立解释的完整原图。
```

Rule of thumb:

- figures may be partial
- figures may be missing
- text must stay accurate

See [Figure Placement](./references/figure-placement.md).

## ✅ Quality Bar

DeepPaperNote is strict about what counts as a successful note.

The note should:

- distinguish research problem from task definition
- explain the real method or analysis flow
- include key numbers that actually matter
- point out what is easy to misread
- state at least one honest limitation
- use real heading levels: `#`, `##`, `###`
- avoid half-Chinese half-English prose lines

If evidence quality is too weak, the skill should fail closed or clearly degrade the output, not pretend it performed a true deep read.

See:

- [Evidence First](./references/evidence-first.md)
- [Deep Analysis](./references/deep-analysis.md)
- [Final Writing](./references/final-writing.md)
- [Note Quality](./references/note-quality.md)

## 🗂️ Repository Layout

```text
DeepPaperNote/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── hero.svg
│   └── note_template.md
├── references/
│   ├── architecture.md
│   ├── deep-analysis.md
│   ├── evidence-first.md
│   ├── figure-placement.md
│   ├── final-writing.md
│   ├── metadata-sources.md
│   ├── model-synthesis.md
│   ├── note-quality.md
│   ├── obsidian-format.md
│   ├── paper-types.md
│   └── workflow.md
└── scripts/
    ├── build_synthesis_bundle.py
    ├── collect_metadata.py
    ├── common.py
    ├── contracts.py
    ├── create_input_record.py
    ├── extract_evidence.py
    ├── extract_pdf_assets.py
    ├── fetch_pdf.py
    ├── lint_note.py
    ├── locate_zotero_attachment.py
    ├── materialize_figure_asset.py
    ├── plan_figures.py
    ├── resolve_paper.py
    ├── run_pipeline.py
    └── write_obsidian_note.py
```

## 🧰 Recommended Environment

| Component | Status | Notes |
| --- | --- | --- |
| Codex desktop / CLI | Recommended | Primary target environment |
| Python 3.10+ | Required | Runs the helper scripts |
| Obsidian vault | Recommended | Default output target |
| Zotero + MCP | Optional | Best for local-library-first workflows |
| OCR tooling | Optional | Helpful for scanned PDFs |

## 📌 Current Status

This repository is in active early-stage development.

| Area | Current state |
| --- | --- |
| Single-paper preprocessing pipeline | ✅ Working |
| Synthesis bundle generation | ✅ Working |
| Zotero-first helper workflow | ✅ Working |
| Obsidian writing flow | ✅ Working |
| Placeholder-first figure planning | ✅ Working |
| Style and structure linting | ✅ Working |
| Public examples | Not added yet |
| Test suite | Not added yet |
| CI | Not added yet |
| Packaging metadata | Not added yet |
| Figure matching / OCR robustness | Needs improvement |

## 🧭 Design Principles

- `Model-first`: understanding belongs to the language model
- `Evidence-first`: writing should be grounded in extracted evidence
- `Placeholder-first`: missing figures must not erase note structure
- `Truth over neatness`: uncertain extraction should be stated honestly
- `Research usefulness over summary polish`: the note should remain valuable later

## 🚀 Future Direction

DeepPaperNote is currently a Codex-first skill.

The long-term direction is:

- keep the core workflow portable
- keep the Codex adapter first-class
- later add adapters for other agent environments if the core remains stable

## Inspirations

DeepPaperNote is informed by paper-reading and note-generation workflows that influenced the design of this skill:

- [heleninsights-dot/phd-deepread-workflow](https://github.com/heleninsights-dot/phd-deepread-workflow)
- [juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv)

What DeepPaperNote tries to do differently is stay strongly `model-first`:
- scripts gather evidence and assets
- the language model does the real paper understanding
- figure handling remains placeholder-first when extraction is uncertain

## Contributing

Contributions are welcome, especially around:

- README and examples
- tests and CI
- PDF/OCR robustness
- figure matching quality
- note quality evaluation
- multi-agent adapter design

## License

License to be added before wider public release.
