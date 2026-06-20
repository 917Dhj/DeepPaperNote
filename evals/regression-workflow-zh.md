# DeepPaperNote 回归测试工作流

状态：v1
读者：运行或审查 DeepPaperNote 评估实验的 Agent
范围：面向真实论文的最终笔记质量回归测试

本文档定义整套实验流程：如何选择论文、运行 baseline 和 candidate、
收集 artifacts、评估输出，以及判断一次修改是否带来了真实提升。

质量评分标准见 `evals/note-quality-rubric.md`。Note Evaluator 的启动
prompt 模板见 `evals/note-evaluator-prompt.md`。

## 核心原则

回归实验比较的是受控条件下的原始生成结果。不要让同一个 Agent 既生成笔
记又评价自己的输出。评估前不要手工修补、补写或润色生成笔记。

一个有效实验需要保持这些变量稳定：

- 论文集合
- runner 工具和模型设置
- prompt 形状
- 每次运行安装的 skill 版本
- vault 布局
- 输出 artifact 布局
- 评估 rubric 版本

## 推荐 Agent 角色

这些角色可以作为独立 session，也可以作为清晰隔离的阶段来执行。

### Paper Finder Agent

选择测试论文。它只读搜索，不运行 DeepPaperNote。

### Baseline Runner Agent

运行冻结的 baseline skill 版本，生成 baseline 笔记和 artifacts。它不评估
质量。

### Candidate Runner Agent

在完全相同的论文集合上运行 candidate skill 版本。它不评估质量。

### Artifact Auditor Agent

检查 candidate run 是否遵守 Source Corpus、bundle、grounding、lint、
figure/table 和保存契约。它不评价最终正文质量。

### Note Evaluator Agent

使用 `evals/note-quality-rubric.md` 比较 baseline note 和 candidate note。
它不生成、不修补笔记。

### Regression Judge Agent

综合 Artifact Auditor 和 Note Evaluator 的输出，给出一次实验的总体判定。

## 阶段 1：选择真实论文

先选论文，再运行 baseline 或 candidate。

论文集合建议包含 4 篇主测试论文和 2 篇备用论文。第一轮应小到足以人工检
查输出；流程稳定后再扩大固定测试集。

### 选择标准

优先选择具备以下条件的论文：

- 有稳定身份信息，例如 DOI、arXiv ID、venue、年份或本地 PDF
- 有可用全文或可靠 PDF 附件
- 技术内容足够复杂，需要深度笔记
- 如有旧笔记或 baseline 笔记更好
- 覆盖不同压力点

尽量覆盖这些论文类型：

- benchmark 或 evaluation paper
- method、model 或 system paper
- appendix-heavy paper
- figure/table-heavy paper
- Discussion 或 Limitations 对理解结论很重要的 paper

避免选择太短、只有摘要级内容、缺少可用来源，或身份信息难以稳定确认的论
文。

### 论文选择输出

Paper Finder Agent 应输出如下表格：

```text
Title | Type | Venue/Year | Note path | PDF or source evidence | Why it is a good test | What the change should help with | Risk
```

最终论文列表必须标出：

- 4 篇主测试论文
- 2 篇备用论文
- 每篇论文对应的测试压力点

## 阶段 2：冻结 Baseline

先跑 baseline，再跑 candidate。没有冻结 baseline，就只能说 candidate 看
起来可接受，不能说它相对 baseline 有提升。

baseline 应该是：

- 一个已发布版本
- 一个修改前 commit
- 或另一个明确命名的参考版本

记录 baseline 身份：

- git ref 或 release tag
- installed skill 来源
- runner 工具
- 模型设置
- prompt 模板
- 运行时间

不要复用旧 baseline artifacts，除非它们使用了相同论文集合、runner 设置、
prompt 形状和 artifact 收集规则。

## 阶段 3：运行 Baseline Notes

对每篇已选论文：

1. 创建隔离 run directory。
2. 创建或指定隔离 test vault。
3. 安装或同步 baseline skill 版本。
4. 使用标准短 prompt 运行 runner 工具。
5. 保存原始最终笔记和所有 artifacts。
6. 生成后不要编辑笔记。

runner prompt 应保持简短，只说明：

- 不允许使用 subagents
- 使用已安装的 DeepPaperNote skill
- 保存到指定 test vault
- 论文任务

baseline 和 candidate 必须使用相同 prompt 形状。

## 阶段 4：运行 Candidate Notes

candidate 在相同论文列表上、baseline 之后运行。

对每篇已选论文：

1. 使用相同论文身份输入。
2. 使用相同 runner 工具和模型设置。
3. 使用相同 prompt 形状。
4. 使用隔离的 candidate run directory 和 test vault。
5. 安装或同步 candidate skill 版本。
6. 保存原始最终笔记和所有 artifacts。
7. 生成后不要编辑笔记。

当 baseline runner 和 candidate runner 共享全局状态时，例如共享 installed
skill 目录，不应并发运行。

## 阶段 5：收集 Artifacts

每篇论文的运行都应产生一个 manifest，把论文映射到对应笔记和 artifacts。

推荐 run layout：

```text
<RUN_ROOT>/
  manifest.json
  baseline/
    <paper_slug>/
      final_note.md
      artifacts/
  candidate/
    <paper_slug>/
      final_note.md
      artifacts/
  reports/
```

尽量收集这些 artifacts：

- final Markdown note
- runner transcript 或 last message
- metadata JSON
- source manifest
- raw sections JSONL
- synthesis bundle
- note plan JSON
- grounding lint output
- note lint output
- figure/table decisions
- figure/table assets 或 copy logs
- Obsidian save output

缺失 artifacts 必须记录，不要静默忽略。

## 阶段 6：Artifact Audit

Artifact Auditor 判断运行是否遵守工作流契约。它不评价最终 prose 质量。

auditor 应检查：

- Source Corpus artifacts 是否存在且内部一致
- `source_manifest.json` 和 `raw_sections.jsonl` 是否作为 canonical
  text-derived reading input
- 旧的 diagnostic derived views 是否又变成 model-facing writing inputs
- truncation 或 partial reading 是否显式记录
- grounding lint 是否使用有效 section IDs 或 page ranges
- figure/table decisions 是否 fail closed
- final save 行为是否保留必要文件和路径

Artifact audit 结果：

- `pass`
- `partial`
- `fail`
- `unknown`

artifact 改善不等同于最终笔记改善。当 artifacts 或契约改善，但最终笔记质量
没有实质提升时，它只能支持 `architectural_improvement_only` 结论。

## 阶段 7：Note Evaluation

Note Evaluator 使用 `evals/note-evaluator-prompt.md` 和
`evals/note-quality-rubric.md`。

对于每篇论文，evaluator 接收：

- 论文身份信息
- baseline final note
- candidate final note
- 可用 baseline artifacts
- 可用 candidate artifacts
- 可选 source evidence

evaluator 必须：

- 只比较原始笔记
- 运行所有 hard gates
- 给 8 个 rubric 维度打分
- 为重要分差引用证据
- 判断 candidate 是否优于 baseline
- 输出 rubric JSON report

evaluator 不得：

- 重写笔记
- 补写缺失章节
- 重新运行 DeepPaperNote
- 使用不同 rubric
- 仅因为格式更干净就判定内容提升

## 阶段 8：Regression Judgment

Regression Judge 综合：

- run manifest
- artifact audit report
- note evaluation report
- runner 失败或缺失 artifacts

它给出实验级 verdict。

### Verdict Values

使用这些值：

- `hard_fail`
- `regression`
- `no_material_change`
- `partial_improvement`
- `real_improvement`
- `architectural_improvement_only`

### 什么算 Real Improvement

`real_improvement` 指 candidate 在最终笔记质量上实质优于 baseline，而不是只
是更干净或结构更规整。

要声称 `real_improvement`，candidate 通常应满足：

- 通过 `evals/note-quality-rubric.md` 中所有已知 hard gates
- 改善 Evidence Chain Coverage 或 Mechanism/Protocol Depth
- 保持或改善 Claim Boundaries and Limitations
- 避免 factual、grounding、figure/table、citation、path 或 readability
  回归
- 提升原因能绑定到论文证据，而不是只绑定到格式
- 在大多数主测试论文上体现提升，而不是只挑中一篇成功案例

### 什么不算 Real Improvement

不要因为这些情况声称 real improvement：

- 只是格式更漂亮
- 笔记更长但 evidence coverage 没变强
- 章节更多但 mechanism 或 result 解释没有变好
- artifact contract 清理了，但最终笔记质量没变
- 一篇论文提升，但其他论文出现严重回归
- candidate note 触发严重 hard gate failure

当 artifacts 或 contracts 改善，但最终笔记质量还没有实质变好时，使用
`architectural_improvement_only`。

## 最小首轮实验

第一轮可复用回归测试建议：

1. 选择 4 篇主测试论文和 2 篇备用论文。
2. 运行一个 baseline 版本。
3. 运行一个 candidate 版本。
4. 对所有主测试论文做 artifact audit。
5. 对所有主测试论文做 note evaluation。
6. 生成一个实验总结。

在 baseline/candidate 流程稳定前，不要加入另一个 runner 工具。

## 最终实验总结

Regression Judge 应产出：

- experiment id
- baseline version
- candidate version
- paper list
- runner settings summary
- artifact audit summary
- note evaluation summary
- per-paper verdicts
- experiment-level verdict
- 是否可以声称 optimization success
- next recommended action

总结应区分：

- mechanism 改善但 note quality 没改善
- note quality 改善但 artifacts 回归
- 单篇论文改善
- 广泛真实改善
- 失败或无法得出结论的实验
