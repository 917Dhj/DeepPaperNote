<div align="center">

# DeepPaperNote

**把单篇论文变成一篇你真的会留下来的高质量 Obsidian 精读笔记。**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![状态](https://img.shields.io/badge/status-alpha-2563eb?style=for-the-badge)](https://github.com/917Dhj/DeepPaperNote)
[![Codex](https://img.shields.io/badge/Codex-first-111827?style=for-the-badge)](./SKILL.md)
[![输出](https://img.shields.io/badge/output-Obsidian-16a34a?style=for-the-badge)](./references/obsidian-format.md)
[![图表](https://img.shields.io/badge/figures-placeholder--first-f59e0b?style=for-the-badge)](./references/figure-placement.md)
[![写作](https://img.shields.io/badge/writing-model--first-7c3aed?style=for-the-badge)](./references/model-synthesis.md)
[![更新日志](https://img.shields.io/badge/changelog-latest-0f766e?style=for-the-badge)](./CHANGELOG.md)

</div>

![DeepPaperNote Hero](./assets/hero.svg)

DeepPaperNote 是一个 **Codex 优先** 的 agent skill，专门做一件事：

- 精读一篇论文
- 从 PDF、元数据来源以及可选的 Zotero 中收集证据
- 让大模型真正负责理解和写作
- 把最终笔记写进 Obsidian vault

它不是为了生成“看起来工整的摘要”，而是为了生成“以后还会反复回看的研究笔记”。

## 🚀 快速开始

1. 把这个仓库放进你的 Codex skills 目录：

   ```text
   ~/.codex/skills/DeepPaperNote
   ```

2. 重启 Codex。

3. 给出论文标题、DOI、arXiv ID、URL、Zotero 条目或本地 PDF。

典型触发语句：

- `给这篇论文生成深度笔记`
- `把这篇文章整理成 obsidian 笔记`
- `读这篇论文并生成 md 笔记`

4. DeepPaperNote 会：
   - 解析论文身份
   - 获取元数据和 PDF 证据
   - 生成 synthesis bundle
   - 让 Codex/GPT 写最终笔记
   - 在写入 Obsidian 之前先做 lint 检查

## 为什么做这个

很多论文总结工具都停得太早：

- 过度依赖摘要
- 把技术细节压扁成通用 bullet
- 遇到图表提取不稳就直接跳过
- 产出的笔记看起来整齐，但一周后已经没有研究价值

DeepPaperNote 的基本立场是：

- `scripts` 负责取证、整理、校验
- Codex/GPT 负责真正理解论文和写作
- 图表处理遵循 `placeholder-first`
- 文字正确性高于图像完整性

它的目标不是“总结一篇论文”，而是“产出一篇你愿意长期保留的研究笔记”。

## ✨ 和一般论文总结工具有什么不同

| 特性 | 实际含义 |
| --- | --- |
| 模型优先 | 脚本负责确定性工作，不负责假装理解论文。 |
| 精读笔记而非摘要改写 | 需要重建论文的问题、任务、方法、结果和局限。 |
| 图表 placeholder-first | 即使没法稳定抽图，也要先保留重要图表在笔记结构中的位置。 |
| 原生适配 Obsidian | 每篇论文默认生成自己的文件夹和本地 `images/` 目录。 |
| Zotero-first | 如果本地 Zotero 已经有论文，优先用它来锚定论文身份。 |

## ⚙️ 工作流

默认流程是：

1. 解析论文身份
2. 收集元数据
3. 获取 PDF 或足够强的全文证据
4. 抽取证据
5. 提取 PDF 图像资产
6. 规划图表位置
7. 构建 synthesis bundle
8. 让 Codex/GPT 写笔记
9. lint 最终笔记
10. 写入 Obsidian

核心原则：

- 脚本负责取证
- 模型负责写作
- lint 在写入前兜底

相关文档：

- [Workflow](./references/workflow.md)
- [Architecture](./references/architecture.md)
- [Model Synthesis](./references/model-synthesis.md)

## 🖼️ 图表策略

DeepPaperNote 采用 `placeholder-first` 策略。

如果某个图表对理解论文很重要，那么即使图像提取不完整，也应该先把它以占位形式保留在笔记里。

推荐占位格式：

```md
> [!figure] Fig. 3 数据分布与质量评估
> 建议位置：数据与任务定义
> 放置原因：这张图同时展示样本构成、对话长度统计和专家质检结果，是理解 `PsyInterview` 数据边界最重要的图之一。
> 当前状态：保留占位；当前提取结果只拿到局部子图，无法稳定恢复成可独立解释的完整原图。
```

基本原则：

- 图可以不全
- 图可以暂时缺失
- 文字一定要尽量正确

详见 [Figure Placement](./references/figure-placement.md)。

## ✅ 质量标准

DeepPaperNote 对“什么算一篇合格笔记”有明确门槛。

最终笔记应该：

- 区分研究问题和任务定义
- 讲清楚真正的方法或分析流程
- 抓住真正重要的关键数字
- 指出哪些地方最容易被误读
- 至少写出一个真实局限
- 使用真实标题层级：`#`、`##`、`###`
- 避免正文出现半中半英的句子

如果证据质量不够，就应该降级或直接失败，而不是假装完成了深度精读。

相关文档：

- [Evidence First](./references/evidence-first.md)
- [Deep Analysis](./references/deep-analysis.md)
- [Final Writing](./references/final-writing.md)
- [Note Quality](./references/note-quality.md)

## 🗂️ 仓库结构

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

## 🧰 推荐环境

| 组件 | 状态 | 说明 |
| --- | --- | --- |
| Codex desktop / CLI | 推荐 | 当前主目标环境 |
| Python 3.10+ | 必需 | 运行辅助脚本 |
| 本地 Obsidian vault | 推荐 | 默认输出目标 |
| Zotero + MCP | 可选 | 对本地论文库工作流很有帮助 |
| OCR 工具 | 可选 | 对扫描版 PDF 更友好 |

## 📌 当前状态

这个仓库还处于早期开发阶段。

| 模块 | 当前状态 |
| --- | --- |
| 单篇论文预处理流程 | ✅ 已可用 |
| synthesis bundle 生成 | ✅ 已可用 |
| Zotero-first 辅助流程 | ✅ 已可用 |
| Obsidian 写入流程 | ✅ 已可用 |
| placeholder-first 图表规划 | ✅ 已可用 |
| 风格与结构 lint | ✅ 已可用 |
| 对外 examples | 暂未补齐 |
| 测试 | 暂未补齐 |
| CI | 暂未补齐 |
| packaging metadata | 暂未补齐 |
| 图像匹配 / OCR 稳定性 | 仍需加强 |

## 🧭 设计原则

- `Model-first`：理解论文属于语言模型
- `Evidence-first`：写作必须建立在证据之上
- `Placeholder-first`：缺图不能破坏笔记结构
- `Truth over neatness`：提取不确定时要诚实表达
- `Research usefulness over summary polish`：长期研究价值优先

## 🔭 后续方向

DeepPaperNote 目前首先是一个 Codex-first skill。

长期方向是：

- 保持核心流程可迁移
- 继续把 Codex adapter 做扎实
- 等核心稳定后，再考虑适配其他 agent 环境

## Inspirations

DeepPaperNote 在工作流设计上受到了这些论文阅读 / 笔记生成项目的启发：

- [heleninsights-dot/phd-deepread-workflow](https://github.com/heleninsights-dot/phd-deepread-workflow)
- [juliye2025/evil-read-arxiv](https://github.com/juliye2025/evil-read-arxiv)

但 DeepPaperNote 希望在这些思路基础上继续坚持几条自己的原则：
- `scripts` 主要负责取证和整理
- 真正的论文理解交给语言模型
- 图表处理优先保留 placeholder 结构，而不是为了插图牺牲文字正确性

## 贡献

欢迎贡献，尤其是：

- README 和 examples
- tests 和 CI
- PDF / OCR 稳定性
- 图像匹配质量
- 笔记质量评估
- 多 agent adapter 设计

## License

正式公开前会补上许可证。
