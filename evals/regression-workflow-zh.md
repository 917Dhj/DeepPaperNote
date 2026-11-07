# DeepPaperNote 回归评估流程

状态：v3
读者：运行或审阅 DeepPaperNote 评估实验的 agent
范围：用真实论文检验一次改动，从冒烟运行到完整的笔记质量回归

本文是 `evals/regression-workflow.md` 的中文译文。两者不一致时以英文版为准，并修正本译文。

评分标准见 `evals/note-quality-rubric.md`（v3），笔记评估者的提示词模板见 `evals/note-evaluator-prompt.md`。Agent 提示词模板只保留英文版，见英文正本的 Agent Prompt Templates 一节。

下文保留英文的术语（如 canonical identity、repair trace、wrong PDF）是产物名、场景名或判定值，与英文正本一一对应，不要翻译。

## 选择层级

| 层级 | 何时使用 | 能说明什么 |
| --- | --- | --- |
| 确定性 | 每个 Pull Request | `python3 -m pytest -q`；改动抽取或图表选择时加跑 `python3 -m pytest -q -m corpus`（见 `evals/paper-corpus.md`） |
| 冒烟 | 改动 `SKILL.md`、某个 reference 或阶段顺序 | 工作流在真实论文上仍能跑完 |
| 完整 | 想声称最终笔记变好了 | candidate 的笔记是否在超出运行间噪声的程度上优于 baseline |

冒烟通过不能支撑任何质量结论。只有完整层级的实验才能得出 `real_improvement`。

## 核心原则

- 实验在受控条件下比较原始生成结果。评估前任何人都不得修改、补全或润色笔记。
- 生成笔记的 agent 不评估该笔记。
- 评估者是盲评：它只看到笔记 A 和笔记 B，永远不知道哪篇来自 baseline。
- 每组只跑一次不构成证据。生成过程有随机性，所以完整层级要测出两次 baseline 运行之间的噪声，只承认超过噪声的差异。

## 受控变量

同一实验的所有运行都要固定以下变量，并记录在 manifest 中：

- **Baseline 与 candidate 提交。** Baseline 是被测改动的父提交：改动之前的那个提交；如果是 Pull Request，则是它与 `develop` 的 merge base。除非 `main` 恰好就是这个提交，否则不要用 `main` 作 baseline；`main` 可能落后 `develop` 很多次合并，会把这些合并的影响混进结果。
- **宿主与模型。** 每个实验只用一个宿主，默认 Codex CLI，模型与推理设置保持一致。改动 `SKILL.md` 时，要在它面向的每个宿主上都跑冒烟层级。
- **论文集与 PDF 字节。** 使用下文的固定论文集，运行前用 `evals/expectations/<paper>.json` 核对每个 PDF 的 SHA-256。
- **输入模式与子会话提示词。** 见“子会话提示词”。
- **运行配置。** 每次运行使用独立的配置文件，避免用户配置、shell profile 或此前的偏好混入。写入 `<RUN_DIR>/config.json`：

  ```json
  {
    "output_language": "<OUTPUT_LANGUAGE>",
    "save_mode": "obsidian",
    "obsidian_vault": "<TEMP_VAULT_PATH>",
    "papers_dir": "Papers"
  }
  ```

  除非实验另有说明，`<OUTPUT_LANGUAGE>` 取 `zh-CN`；`<TEMP_VAULT_PATH>` 是一个已存在的空目录的绝对路径。启动子会话时设置 `DEEPPAPERNOTE_CONFIG_PATH=<RUN_DIR>/config.json` 和 `DEEPPAPERNOTE_DISABLE_SHELL_CONFIG=1`，不设置其他任何 `DEEPPAPERNOTE_` 变量。

- **隔离。** 每次运行有自己的运行目录和临时 vault。共用同一个已安装 skill 目录的运行不得并发。
- **Rubric 版本。** 同一实验的所有评估使用同一版本的 rubric。

## 论文集

使用 `evals/papers/` 中的固定论文集。PDF 只在本地、被 Git 忽略；它们的哈希提交在 `evals/expectations/` 中。

| 角色 | 论文 | 压力点 |
| --- | --- | --- |
| 主测 | `arxiv-sam` | 方法加数据集，图表密集，有附录，Visual Review 负担重 |
| 主测 | `tacl-lost-middle` | 评测类论文，图多，结论受局限性约束 |
| 主测 | `osdi-distserve` | 系统论文，含算法和对比表 |
| 主测 | `ncomms-medsam` | 期刊版式，医学领域，通栏图注 |
| 备用 | `arxiv-transformer` | 短篇机制论文 |
| 备用 | `zh-aptamer-review` | 中文综述 |

冒烟层级使用 `arxiv-transformer` 和 `arxiv-sam`。只有当某篇主测论文因与改动无关的原因无法启动时，才用备用论文替换，并记录原因。

扩充论文集时，由 Paper Finder agent 挑选身份稳定、PDF 可读、技术深度足以写深读笔记，并且补上现有论文集缺少的压力点的论文：benchmark 或评测、方法或系统、附录密集、图表密集、局限性密集。新论文在被实验使用之前，先按 `evals/paper-corpus.md` 建立 `evals/expectations/` 条目。

## 子会话提示词

每次运行启动一个独立的子会话，只给一条提示词，此外什么都不给：不加额外约束、解释、源文件路径、agent 指令、模型说明、前缀或后缀。子会话不使用 `/goal`，下文的工作流 agent 使用。不要在同一个子会话里跑两篇论文。

| 输入模式 | 用于 | 提示词 |
| --- | --- | --- |
| PDF（默认） | 所有笔记质量比较 | `给这篇论文生成一个深度笔记：<PDF_PATH>。笔记保存到<TEMP_VAULT_PATH>中。` |
| 标题 | 改动 resolve、metadata、fetch 或身份逻辑时 | `给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。` |

PDF 模式让两组拿到同样的字节，并跳过 Zotero 查找。标题模式端到端地覆盖获取流程，所以结果还取决于网络和 Zotero 是否在运行；两者都要记录。同一实验的两组使用同一种模式。记录每次运行的完整提示词。

## 运行记录

每个子会话结束后，运行者在该运行目录下保存：

- 原始最终笔记，以及该运行写出的全部产物
- 子会话提示词、日志和退出状态
- `status-bindings.json`，按 `<SKILL_ROOT>/references/run-state.md` 的格式写明该运行的 admission、note plan、草稿、lint、审查和保存文件，以及运行上下文。这些文件没有固定文件名，不带 bindings 的状态查询会把这些阶段报为 `missing`，即使运行已经完成，`summary.saved_verified` 也是 false。子会话写了 bindings 文件、且其中的路径与 `<RUN_WORKDIR>` 中的文件一致时，直接沿用；否则根据这些文件和运行配置写一份。
- `run_state.json`，即 `python3 <SKILL_ROOT>/scripts/run_state.py status --workdir <RUN_WORKDIR> --prefix <RUN_PREFIX> --bindings <RUN_DIR>/status-bindings.json` 的输出。它记录哪些阶段通过、过期产物、来源缺口，以及最终报告使用的 `summary`。子会话自行选择工作目录时，从其日志中的 `workdir=` 行取 `<RUN_WORKDIR>`。

当 `run_state.json` 显示所有必需阶段都通过、`summary.saved_verified` 为真且 `summary.saved_sha256_match` 为真时，该运行算作**完成**。

## 冒烟层级

1. 在改动面向的每个宿主上，用 PDF 模式让 candidate 各跑一次两篇冒烟论文。
2. 保留每次运行的运行记录。
3. 一位审阅者（人或 agent）对照 rubric 的硬门槛 H1 到 H8 阅读每篇笔记。它不打分，也不做比较。
4. 写出 `smoke-report.md`：逐次运行记录宿主、按 `run_state.json` 判断的完成情况、任何 `next_action` 或来源缺口，以及每个硬门槛的结果和一行证据。

所有运行都完成且所有硬门槛都通过，冒烟层级才算通过。报告时只能说“工作流仍能跑完”，不能当作质量结论。

## 完整层级

### 角色

每个角色可以是独立会话，也可以是隔离清楚的阶段：

- **Baseline Runner：** 记录 baseline 身份，然后运行 baseline。不判断质量。
- **Candidate Runner：** 在同一论文集上运行 candidate，然后构建盲评配对。不判断质量。
- **Artifact Auditor：** 对照工作流契约检查每次运行。不评判文字。
- **Note Evaluator：** 用 rubric 给盲评配对打分。永远看不到 manifest、分组或提交。
- **Regression Judge：** 揭盲并给出判定。

每个 agent 读取上一阶段的文档，写出自己的文档交给下一阶段。提示词使用占位符，不写本地路径：

```text
baseline-run-manifest.md
  -> candidate-run-manifest.md + evaluation-pairs.md + blinding-map.json（封存）
  -> artifact-audit-report.md
  -> note-evaluation-report.md
  -> regression-summary.md
```

### 运行

每篇主测论文在每组各跑两次，每次都是新的子会话：四篇论文乘两组乘两次，共 16 次运行。运行目录使用中性编号，例如 `run-07`，让路径不暴露分组；编号与分组的对应关系记在 manifest 中。

只有当提交、宿主、模型、论文集、输入模式、子会话提示词和运行配置全部一致时，才能复用此前的 baseline 运行。

### 盲评配对

所有运行记录完成后，Candidate Runner 为每篇论文构建三组配对：

| 配对 | 比较 | 用途 |
| --- | --- | --- |
| 噪声 | baseline 第 1 次与 baseline 第 2 次 | 同一版本两次运行相差多少 |
| 比较 1 | baseline 第 1 次与 candidate 第 1 次 | |
| 比较 2 | baseline 第 2 次与 candidate 第 2 次 | |

对每组配对，它随机决定哪次运行是 A，给配对一个中性编号，把所有配对一起打乱，然后写出：

- `evaluation-pairs.md`：逐组记录编号、论文、论文预期的 `paper_type` 及其必答问题（按评分标准 Required Inputs 一节的要求），以及 A 和 B 各自的笔记、源证据和产物根目录
- `blinding-map.json`：逐组记录配对类型，以及 A 和 B 分别对应哪次运行、哪一组。只有 Regression Judge 读取它。

### 产物审计

审计者从每次运行的 `run_state.json` 开始，记录阶段结果、过期产物和来源缺口。然后检查脚本判断不了的部分：

- 接受的身份与 PDF 中的论文一致：标题、作者和标识符
- Visual Review 的决定合理：主方法图和主结果图没有被漏掉或丢弃，每个丢弃都给出编辑理由
- 笔记中的嵌入与冻结的决定一致，插入的图片存在于论文本地的 `images/` 目录
- 当 source manifest 记录了截断或部分阅读时，笔记中写明了这一点
- Grounding Lint 为核心论断引用了有效的章节 ID 或页码范围

每次运行得到 `pass`、`partial`、`fail` 或 `unknown`：

- `pass`：所有必需阶段都通过，上述检查都成立。
- `partial`：运行完成了，但来源、警告或 repair trace 的缺口降低了审计置信度。
- `fail`：某个必需阶段失败、上述某项检查不成立，或身份证据相互矛盾或不安全。
- `unknown`：必需产物缺失或无法读取，审计者无法判断。

标题模式的实验中，审计者还要用明确证据把获取身份的行为映射到这些结果：

- `pass`：resolve、metadata、fetch、canonical identity 和 repair trace 产物被一致地复用和消费；identity verdict 为 accepted 或 accepted-with-warnings；警告只涉及 metadata 或来源；Source Corpus 证据绑定到所选的 source manifestation。
- `partial`：运行仍可评估，但非阻断性的来源、警告或 repair trace 证据不完整。
- `fail`：身份证据相互矛盾或不安全；repair-exhausted failure 没有在下游消费前 fail closed；fetch 使用了过期或错误的身份；所选 PDF 或 source manifestation 不一致；或 repaired identity 缺少 trace。
- `unknown`：必需的获取产物缺失或无法读取。

只要运行中出现了 repaired identity、accepted-with-warnings identity、repair-exhausted failure 和 equivalent manifestation 场景，就逐项覆盖。

产物改进不等于最终笔记改进。只有当证据表明获取身份的改进防止或修复了 wrong identity、wrong PDF、metadata contradiction、missing source evidence、broken path、citation damage 或类似的下游失败时，它才算 note-visible。否则它只支持 `architectural_improvement_only`。

### 笔记评估

Note Evaluator 用 `evals/note-evaluator-prompt.md` 和 `evals/note-quality-rubric.md` 评估 `evaluation-pairs.md` 中的每组配对，一次一组，最好每组用一个新会话。它只读取这三个文件和配对中列出的路径，绝不读取 manifest、`blinding-map.json`、Git 历史或文件时间戳。它为每组配对写一份 rubric JSON 报告，汇总到 `note-evaluation-report.md`。

### 回归判定

Regression Judge 读取以上所有文档，包括 `blinding-map.json`，并揭开每组配对。

对每篇论文的每个 rubric 维度：

- **噪声幅度**是噪声配对中的分数差的绝对值。
- 当 candidate 在两组比较配对中得分都更高，且每次提升都超过噪声幅度时，candidate 在该维度**改进**。
- 当 candidate 在两组比较配对中得分都更低，且每次下降都超过噪声幅度时，candidate 在该维度**退化**。
- 其余情况都算噪声。

每篇论文给出一个判定：

- `hard_fail`：某篇 candidate 笔记未通过某个硬门槛，而同一配对中的 baseline 笔记通过了。
- `regression`：candidate 在某个核心内容维度（D1 到 D4、D9 或 D10）退化，且没有任何维度改进。
- `no_material_change`：所有差异都是噪声。
- `partial_improvement`：candidate 改进了部分维度，但不包括 D1、D2、D9 或 D10，或同时在某个维度退化。
- `real_improvement`：candidate 改进了 D1、D2、D9 或 D10，没有在 D4 退化，没有引入硬门槛失败，且评估者给出的理由把提升归于论文证据而非格式。

实验的判定是 `hard_fail`、`regression`、`no_material_change`、`partial_improvement`、`real_improvement` 或 `architectural_improvement_only` 之一：

- 任一论文为 `hard_fail` 时，判定为 `hard_fail`。
- 只有当四篇论文中至少三篇为 `real_improvement` 且没有任何一篇为 `regression` 时，才判定为 `real_improvement`。
- 产物或契约改进了，但没有任何论文超过 `no_material_change` 时，判定为 `architectural_improvement_only`。
- 其他情况，选最能概括各论文结果的判定，并写明理由。

以下都不算真实改进：格式更好看；笔记更长但证据覆盖不变；章节更多但机制或结果解释没有更好；产物更干净但笔记没变；在一篇论文上提升、同时在另一篇上严重退化。

对于获取身份的改动，分别记录两个字段：

- `architectural_improvement_only`：candidate 改进了产物复用、来源、canonical identity、repair trace 或报告清晰度，但最终笔记没有可见的质量提升。
- `final_note_visible_improvement`：candidate 防止或修复了在生成笔记或源证据中可见的 wrong identity、wrong PDF、metadata contradiction、missing source evidence、broken path、citation damage 或类似的下游失败。

### 实验总结

`regression-summary.md` 记录实验编号、baseline 与 candidate 提交、宿主与模型、输入模式、论文集、运行配置、每次运行的完成与审计结果、噪声幅度、每篇论文的判定及起决定作用的维度、实验判定、能否声称优化成功，以及下一步建议。它要把以下情况分开写：机制有提升但笔记没提升；笔记有提升但产物退化；架构层面的获取改进与 note-visible 的获取改进；以及无法得出结论的实验。

## Agent 提示词模板

见英文正本 `evals/regression-workflow.md` 的 Agent Prompt Templates 一节。每个工作流 agent 都以 goal 模式启动，所以每个模板都以 `/goal` 开头。
