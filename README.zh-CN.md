<div align="center">

# DeepPaperNote

**把单篇论文变成一篇你真的会留下来的高质量 Obsidian 精读笔记。**

[English](./README.md) | [简体中文](./README.zh-CN.md)

[![状态](https://img.shields.io/badge/status-alpha-2563eb?style=for-the-badge)](https://github.com/917Dhj/DeepPaperNote)
[![许可证](https://img.shields.io/badge/license-MIT-475569?style=for-the-badge)](./LICENSE)
[![Codex](https://img.shields.io/badge/Codex-skill-111827?style=for-the-badge)](./SKILL.md)
[![输出](https://img.shields.io/badge/output-Obsidian-16a34a?style=for-the-badge)](./references/obsidian-format.md)
[![图表](https://img.shields.io/badge/figures-placeholder--first-f59e0b?style=for-the-badge)](./references/figure-placement.md)
[![写作](https://img.shields.io/badge/writing-model--first-7c3aed?style=for-the-badge)](./references/model-synthesis.md)
[![更新日志](https://img.shields.io/badge/changelog-latest-0f766e?style=for-the-badge)](./CHANGELOG.md)

</div>

![DeepPaperNote Hero](./assets/hero.png)

DeepPaperNote 是一个 **Codex skill**，专门做一件事：

- 精读一篇论文
- 从 PDF、元数据来源以及可选的 Zotero 中收集证据
- 让大模型真正负责理解和写作
- 优先把最终笔记写进 Obsidian vault；如果没有配置 vault，则退回当前工作区输出

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

如果你想在本地装 Python 依赖用于开发，可以执行：

```bash
python3 -m pip install -e .
```

安装后，你也可以直接对 Codex 发一些很短的命令式请求，比如：

- `/deeppapernote doctor`
- `/deeppapernote start`
- `查看 deeppapernote 的可用情况`
- `deeppapernote 有什么功能`

在这种模式下，DeepPaperNote 应该一边介绍自己的能力，一边检查当前配置情况，并告诉你哪些已经配置好了、哪些还缺失。

如果你还希望有一份更明确的引导提示词，也可以参考 [ONBOARDING_PROMPT.md](./ONBOARDING_PROMPT.md)。

## 🔧 配置说明

安装之后，如果你希望获得 Obsidian 原生的笔记管理体验，真正必需的配置只有一项，其他更多属于可选增强配置。

### 必需：告诉 DeepPaperNote 你的 Obsidian vault 在哪里

DeepPaperNote 会把最终笔记写进 Obsidian vault。
最直接的配置方式是设置环境变量：

```bash
export DEEPPAPERNOTE_OBSIDIAN_VAULT="/你的/Obsidian_Documents/绝对路径"
```

相关的可选配置还有：

```bash
export DEEPPAPERNOTE_PAPERS_DIR="20_Research/Papers"
export DEEPPAPERNOTE_OUTPUT_DIR="tmp/DeepPaperNote"
```

它们的含义是：

| 变量 | 是否必需 | 作用 |
| --- | --- | --- |
| `DEEPPAPERNOTE_OBSIDIAN_VAULT` | 正常写入 vault 时必需 | 你的 Obsidian vault 根目录 |
| `DEEPPAPERNOTE_PAPERS_DIR` | 可选 | vault 内论文输出目录，默认是 `20_Research/Papers` |
| `DEEPPAPERNOTE_OUTPUT_DIR` | 可选 | 本地临时产物目录，默认是 `tmp/DeepPaperNote` |
| `DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR` | 可选 | 当没有配置 Obsidian vault 时，当前工作区下的 fallback 输出目录，默认是 `DeepPaperNote_output` |

如果没有配置 Obsidian vault，DeepPaperNote 依然可以把笔记写到当前工作区下，而不是直接报错。
这对快速试用很有帮助，但从长期管理角度看，依然更推荐配置好自己的 Obsidian vault。

这些可选路径配置的实际好处是：

- `DEEPPAPERNOTE_PAPERS_DIR`
  如果你的 vault 不是把论文放在 `20_Research/Papers` 下，或者你已经有自己的目录约定，这个配置可以让 DeepPaperNote 直接适配你的现有结构，减少后续手动移动文件。
- `DEEPPAPERNOTE_OUTPUT_DIR`
  如果你希望中间产物统一落在一个固定位置，方便调试、清理或做实验，这个配置会比较有用。

### 可选：用于本地文献库优先工作流的 Zotero MCP

DeepPaperNote 不依赖 Zotero 才能工作。
但如果你希望 Codex 优先搜索你本地 Zotero 库中的论文，建议配置一个 **Codex 真的能用** 的 Zotero MCP 方案。

这项配置最适合这样的人：
- 你本来就用 Zotero 做文献管理
- 你平时主要在 Zotero 里读论文、整理附件和元数据

可以这样理解不同路线：

| 方案 | 更适合什么场景 | 说明 |
| --- | --- | --- |
| [kujenga/zotero-mcp](https://github.com/kujenga/zotero-mcp) | 轻量的只读访问 | 更接近一个最小化 Zotero MCP server，适合搜索条目、读元数据、读文本 |
| [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) | 更完整的研究工作流能力 | 功能更丰富，但在 Codex 环境里不一定开箱即用，可能还需要额外适配 |

为什么值得配：

- 本地 Zotero 命中通常是最可靠的论文身份锚点
- Codex 可以先查你的本地论文库，再决定要不要联网
- 本地附件也更有助于减少标题误匹配
- 如果你本来就用 Zotero 做论文管理，这会比重新去网上“猜测这篇论文是谁”稳得多
- 对正式发表版、预印本、镜像页面标题相似的场景，Zotero-first 通常会明显降低误匹配概率

需要特别说明的是：

- DeepPaperNote **不强依赖某一个固定的 Zotero MCP 仓库**
- 对 DeepPaperNote 来说，最核心的能力是：Codex 能搜索 Zotero 条目、查看元数据、最好还能读取本地全文
- 有些 Zotero MCP 项目最初是围绕其他 agent 客户端设计的，接到 Codex 上时可能需要额外改造

### 可选：Semantic Scholar API Key

这不是必需项，但如果你有 Semantic Scholar API key，可以设置：

```bash
export DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY="your_api_key"
```

它的好处主要是：

- 元数据补全通常会更稳一些
- 对一些标题不好匹配的论文，身份解析会更可靠
- 在作者、venue、摘要等信息回填上，有时会更完整
- 它能给 DeepPaperNote 多一个较强的元数据来源，减少退回到弱匹配的概率

### 可选：OCR 工具

很多现代 PDF 并不需要 OCR。
但如果论文是下面这些情况，OCR 会很有帮助：

- 扫描版 PDF
- 以图片为主、嵌入文本质量很差的 PDF
- 一些比较老的论文，直接抽文本时内容残缺

DeepPaperNote 为什么要用 OCR：

- 当直接 PDF 抽文本太差时，用它来补页内正文
- 避免方法和结果证据因为 PDF 编码问题而大量丢失
- 改善图表附近页内文字上下文的恢复效果

DeepPaperNote 当前的 OCR 使用逻辑是：

- 先用 `PyMuPDF` 做正常的 PDF 文本提取
- 对每一页统计可搜索文本的字符数
- 如果某一页直接抽到的文本太少，就把这页视为 OCR fallback 候选
- 只对这类页面单独做 OCR
- OCR 恢复出的文本，主要用于补页级证据和后续 figure/page 语义匹配的上下文

需要特别说明的是：

- OCR 目前只是 **页文本兜底方案**
- 它 **不是** 所有 PDF 的主提取路径
- 它 **不会** 代替模型去理解论文
- 它 **不会** 直接负责“理解图片内容”

如果没有 OCR，DeepPaperNote 处理普通数字版 PDF 依然没问题，但面对扫描版或低质量 PDF 时，证据质量会更弱一些。

OCR 需要的依赖如下：

| 层级 | 依赖 | 作用 |
| --- | --- | --- |
| 系统工具 | `tesseract` | 真正执行 OCR 识别 |
| Python 包 | `pytesseract` | Python 调用 `tesseract` 的桥接层 |
| Python 包 | `Pillow` | 打开页面渲染后的图像再交给 OCR |
| 现有 PDF 层 | `PyMuPDF` | 负责正常抽文本与页面渲染 |

在 macOS 上的安装方式：

```bash
brew install tesseract
python3 -m pip install --user pytesseract Pillow
```

快速验证：

```bash
tesseract --version
python3 -c "import pytesseract, PIL; print('python_ok')"
python3 -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

## 📝 更新日志概览

更完整的版本级更新请见 [CHANGELOG.md](./CHANGELOG.md)。

| 版本 | 状态 | 主要内容 |
| --- | --- | --- |
| Unreleased | 开发中 | 首个公开版 Codex 工作流、synthesis bundle 流程、Zotero-first 辅助能力、placeholder-first 图表规划 |

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
│   ├── hero.png
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
| 本地 Obsidian vault | 写笔记时必需 | 需要配置 `DEEPPAPERNOTE_OBSIDIAN_VAULT` |
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

DeepPaperNote 目前就是一个 Codex skill。

长期方向是：

- 保持核心流程可迁移
- 继续把 Codex 集成做扎实
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

本项目采用 [MIT License](./LICENSE)。
