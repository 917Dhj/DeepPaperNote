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
- 子 Codex CLI prompt 模板
- 每次运行安装的 skill 版本
- vault 布局
- 输出 artifact 布局
- 评估 rubric 版本

## 交接文档

每个 Agent 开始前都应读取上一阶段输出的文档，然后把自己的结果写成下一
个 Agent 可读取的文档。prompt 中使用占位符，不写死本地路径。

推荐交接链路：

```text
paper-set.md
  -> baseline-run-manifest.md
  -> candidate-run-manifest.md
  -> artifact-audit-report.md
  -> note-evaluation-report.md
  -> regression-summary.md
```

runner manifest 还应指向 run root 下的机器可读 artifacts。

## Goal 模式与子 Runner Prompt

每个 workflow 阶段的 Agent 都应以 goal mode 启动。本文档中的每个 Agent
Prompt Template 都以 `/goal` 开头。

Baseline Runner 和 Candidate Runner 为每篇论文启动的独立 Codex CLI session
是例外：这些子 session 不使用 `/goal`。

每篇论文必须用完全相同的单句 prompt 启动独立 Codex CLI，替换占位符后不
得添加任何额外信息：

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

不要给这个子 prompt 添加额外约束、解释、source path、agent instruction、
model note 或前后缀。必须在 manifest 中记录实际使用的完整子 prompt。

## 推荐 Agent 角色

这些角色可以作为独立 session，也可以作为清晰隔离的阶段来执行。

### Paper Finder Agent

选择测试论文。它只读搜索，不运行 DeepPaperNote。

### Baseline Runner Agent

记录冻结的 baseline 身份，运行 baseline skill 版本，并写出 baseline 笔记
和 artifacts。它不评估质量。

### Candidate Runner Agent

在完全相同的论文集合上运行 candidate skill 版本，并写出 candidate 笔记和
artifacts。它不评估质量。

### Artifact Auditor Agent

检查 candidate run 是否遵守 Source Corpus、bundle、grounding、lint、
figure/table 和保存契约。它不评价最终正文质量。

### Note Evaluator Agent

使用 `evals/note-quality-rubric.md` 比较 baseline note 和 candidate note。
它不生成、不修补笔记。

### Regression Judge Agent

综合 runner 状态、artifact audit 和 note evaluation，给出一次实验的总体判
定。

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

Paper Finder Agent 应输出一个 Markdown 报告，包含：

- 4 篇主测试论文
- 2 篇备用论文
- 每篇论文对应的测试压力点
- 如下表格：

```text
Title | Type | Venue/Year | Note path | PDF or source evidence | Why it is a good test | What the change should help with | Risk
```

### Paper Finder Agent Prompt Template

```text
/goal

目标：
为 DeepPaperNote 回归测试选择一组可复用的真实论文。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- 可选的历史论文选择文档：<PRIOR_SELECTION_DOC_OR_NONE>
- 论文来源根目录或索引：<PAPER_SOURCE_ROOT>

任务：
- 找出 6 篇候选论文：4 篇主测试论文和 2 篇备用论文。
- 优先选择身份信息稳定、有可用 PDF/source material、技术深度足够的论文。
- 尽量覆盖 benchmark/evaluation、method/model/system、appendix-heavy、figure/table-heavy、limitations-heavy 压力点。
- 不要运行 DeepPaperNote。
- 不要修改笔记、PDF 或 vault。

约束：
- 只做 read-only 搜索。
- 不要因为论文看起来有名就推荐；必须给出本地 note 或 source evidence。

输出：
- 将 Markdown 论文集报告写入 <PAPER_SET_DOC>。
- 包含指定选择表格。
- 标出 4 篇主测试论文和 2 篇备用论文。
- 对每篇主测试论文写明预期压力点，以及这篇论文能暴露什么回归问题。
```

## 阶段 2：运行 Baseline Notes

先跑 baseline，再跑 candidate。没有冻结 baseline，就只能说 candidate 看
起来可接受，不能说它相对 baseline 有提升。

Baseline Runner 负责 baseline manifest。生成笔记前，它必须记录：

- baseline git ref 或 release tag
- installed skill 来源
- runner 工具
- 模型设置
- prompt 模板
- 运行时间
- paper-set 文档路径
- run root 和 vault 布局
- artifact 收集规则

对每篇已选论文：

1. 创建隔离 run directory。
2. 创建或指定隔离 test vault。
3. 安装或同步 baseline skill 版本。
4. 为每篇论文启动一个独立 Codex CLI session，并使用规定的精确子 prompt。
5. 保存原始最终笔记和所有 artifacts。
6. 在 baseline manifest 中记录 present/missing artifacts。
7. 生成后不要编辑笔记。

单篇论文的子 Codex CLI prompt 必须严格等于：

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

runner 可以在这个子 prompt 之外控制 working directory、temp vault、已安装
skill 版本、日志和 manifest 收集，但不得给子 prompt 添加任何额外文字。
baseline 和 candidate 必须使用相同的子 prompt 模板。

不要复用旧 baseline artifacts，除非它们使用了相同论文集合、runner 设置、
子 Codex CLI prompt 模板和 artifact 收集规则。

### Baseline Runner Agent Prompt Template

```text
/goal

目标：
使用冻结的 baseline DeepPaperNote 版本为已选论文集生成 baseline 笔记，并写出完整 baseline manifest。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- 论文集报告：<PAPER_SET_DOC>
- baseline ref 或 release 说明：<BASELINE_REF_DOC_OR_VALUE>

任务：
- 在运行任何论文前记录 baseline 身份。
- 使用本 workflow 规定的单篇论文子 Codex CLI prompt 模板。
- 对每篇主测试论文创建隔离 run directory 和 test vault。
- 同步或安装 baseline skill 版本。
- 为每篇主测试论文启动一个单独的、独立的 Codex CLI session。
- 每个子 Codex CLI session 中只能使用这个 prompt，替换占位符后不得添加任何其他文字：`给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。`
- 不要给子 Codex CLI prompt 添加任何额外信息。
- 保存原始最终笔记、runner logs 和所有可用 artifacts。
- 记录实际使用的完整子 prompt、temp vault path、run directory、final note path、logs、exit status、可用 artifacts 和缺失 artifacts。

约束：
- 本 workflow 阶段 Agent 使用 `/goal`；单篇论文的子 Codex CLI session 不使用 `/goal`。
- 不要把多篇论文合并到同一个 Codex CLI session 中运行。
- 不要评估笔记质量。
- 不要修补或重写生成笔记。
- 不要运行 candidate 代码。
- 不要改变论文集。

输出：
- 写入 <BASELINE_MANIFEST_DOC>。
- manifest 必须包含 baseline 身份、runner 设置、子 Codex CLI prompt 模板、每篇论文实际使用的完整子 prompt、每篇论文状态、最终笔记路径、artifact 路径、logs、exit status 和缺失 artifacts。
- 如可行，同时在 <BASELINE_RUN_ROOT> 下写入或更新机器可读 manifest 数据。
```

## 阶段 3：运行 Candidate Notes

candidate 在相同论文列表上、baseline 之后运行。

对每篇已选论文：

1. 使用相同论文身份输入。
2. 使用相同 runner 工具和模型设置。
3. 使用完全相同的子 Codex CLI prompt 模板。
4. 使用隔离的 candidate run directory 和 test vault。
5. 安装或同步 candidate skill 版本。
6. 保存原始最终笔记和所有 artifacts。
7. 在 candidate manifest 中记录 present/missing artifacts。
8. 生成后不要编辑笔记。

当 baseline runner 和 candidate runner 共享全局状态时，例如共享 installed
skill 目录，不应并发运行。

单篇论文的子 Codex CLI prompt 必须与 baseline 使用完全相同的模板：

```text
给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。
```

### Candidate Runner Agent Prompt Template

```text
/goal

目标：
在完全相同的论文集上运行 candidate DeepPaperNote 版本，并写出能和 baseline manifest 对齐的 candidate manifest。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- 论文集报告：<PAPER_SET_DOC>
- baseline manifest：<BASELINE_MANIFEST_DOC>
- candidate ref 或变更说明：<CANDIDATE_REF_DOC_OR_VALUE>

candidate与baseline版本定义：
- baseline版本：<main>分支
- candidate版本：<CANDIDATE BRANCH>分支

任务：
- 确认论文集和子 Codex CLI prompt 模板与 baseline manifest 一致。
- 同步或安装 candidate skill 版本。
- 对每篇主测试论文创建隔离 candidate run directory 和 test vault。
- 为每篇主测试论文启动一个单独的、独立的 Codex CLI session。
- 每个子 Codex CLI session 中只能使用这个 prompt，替换占位符后不得添加任何其他文字：`给这篇论文生成一个深度笔记：<PAPER_TITLE>。笔记保存到<TEMP_VAULT_PATH>中。`
- 不要给子 Codex CLI prompt 添加任何额外信息。
- 保存原始最终笔记、runner logs 和所有可用 artifacts。
- 记录实际使用的完整子 prompt、temp vault path、run directory、final note path、logs、exit status、可用 artifacts 和缺失 artifacts。
- 把每个 candidate output 映射到对应 baseline output。

约束：
- 单篇论文的子 Codex CLI session 不使用 `/goal`。
- 不要把多篇论文合并到同一个 Codex CLI session 中运行。
- 不要评估笔记质量。
- 不要修补或重写生成笔记。
- 不要重跑 baseline。
- 除非 baseline manifest 无效，否则不要改变论文集。

输出：
- 写入 <CANDIDATE_MANIFEST_DOC>。
- manifest 必须包含 candidate 身份、runner 设置、子 Codex CLI prompt 模板、每篇论文实际使用的完整子 prompt、每篇论文状态、最终笔记路径、artifact 路径、logs、exit status、缺失 artifacts 和 baseline/candidate 对应关系。
- 如可行，同时在 <CANDIDATE_RUN_ROOT> 下写入或更新机器可读 manifest 数据。
```

## 阶段 4：Artifact Audit

Artifact Auditor 判断运行是否遵守工作流契约。它不评价最终 prose 质量。

auditor 应检查：

- Source Corpus artifacts 是否存在且内部一致
- `source_manifest.json` 和 `raw_sections.jsonl` 是否作为 canonical
  text-derived reading input
- 旧的 diagnostic derived views 是否又变成 model-facing writing inputs
- acquisition resolve、metadata、fetch、Canonical Identity Artifact 和
  Identity Repair Trace artifacts 是否存在，或是否被明确记录为缺失
- canonical identity 的 provenance 是否指回预期的 resolve 和 metadata
  artifacts
- fetch 是否消费 canonical identity/source manifestation contract，而不是
  重新使用松散的 resolve 或 metadata identity fields
- repaired identity、accepted-with-warnings identity、repair-exhausted failure
  和 equivalent manifestation 场景是否由 explicit identity verdict、warning、
  failure class、equivalence 和 repair trace evidence 解释
- truncation 或 partial reading 是否显式记录
- grounding lint 是否使用有效 section IDs 或 page ranges
- figure/table decisions 是否 fail closed
- final save 行为是否保留必要文件和路径

Artifact audit 结果：

- `pass`
- `partial`
- `fail`
- `unknown`

acquisition identity behavior 也必须用 explicit evidence 映射到这些结果：

- `pass`：resolve、metadata、fetch、canonical identity 和 repair trace
  artifacts 被 consistent reuse/consume；identity verdict 是 accepted 或
  accepted-with-warnings；warning 仅限 metadata/provenance；Source Corpus
  evidence 绑定到 selected source manifestation。
- `partial`：运行仍可进入 note evaluation，但非阻塞的 provenance、warning
  或 repair trace evidence 不完整，导致 acquisition audit 置信度下降。
- `fail`：identity evidence 矛盾或不安全；repair-exhausted failure 没有在
  downstream consumption 前 fail closed；fetch 使用了 stale 或 wrong identity；
  selected PDF/source manifestation 不一致；或 repaired identity 缺少 trace。
- `unknown`：manifest 中缺少必要 acquisition artifacts，或 artifact 不可访问，
  auditor 无法判断 identity contract 是否被遵守。

artifact 改善不等同于最终笔记改善。当 artifacts 或契约改善，但最终笔记质量
没有实质提升时，它只能支持 `architectural_improvement_only` 结论。

acquisition identity improvement 只有在证据表明它 prevent/fix wrong identity、
wrong PDF、metadata contradiction、missing source evidence、broken path、
citation damage 或 comparable downstream failure 时，才能计入 final
note-visible improvement。否则即使 acquisition architecture 更干净，也只能归入
`architectural_improvement_only`。

### Artifact Auditor Agent Prompt Template

```text
/goal

目标：
审查 baseline 和 candidate run 是否产出了完整、符合契约的 artifacts。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- 论文集报告：<PAPER_SET_DOC>
- baseline manifest：<BASELINE_MANIFEST_DOC>
- candidate manifest：<CANDIDATE_MANIFEST_DOC>

任务：
- 检查两个 manifest 中列出的 artifacts。
- 检查 Source Corpus、synthesis bundle、grounding、lint、figure/table 和 save artifacts。
- 检查 acquisition resolve、metadata、fetch、canonical identity 和 repair trace artifacts。
- 验证 canonical identity 和 repair trace evidence 是否被 consistent reuse/consume。
- 用具体证据把 identity behavior 映射到 pass/partial/fail/unknown。
- 当运行中出现 repaired identity、accepted-with-warnings identity、repair-exhausted failure 和 equivalent manifestation 场景时，逐项覆盖。
- 记录 candidate artifacts 是否遵守预期契约。
- 记录缺失或不一致 artifacts。
- 区分 artifact 改善和最终笔记质量改善。

约束：
- 不要评价最终正文质量。
- 不要编辑笔记或 artifacts。
- 不要重跑 DeepPaperNote。
- 不要仅凭 artifacts 存在就推断成功。

输出：
- 写入 <ARTIFACT_AUDIT_REPORT>。
- 对每篇主测试论文给出 pass/partial/fail/unknown、证据路径、identity verdict evidence、source manifestation evidence、repair trace evidence 和风险。
- 最后给出总体 artifact verdict，以及是否存在阻塞 note evaluation 的问题。
```

## 阶段 5：Note Evaluation

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

### Note Evaluator Agent Prompt Template

```text
/goal

目标：
评估 candidate 最终笔记是否比 baseline 最终笔记有实质提升。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- <REPO_ROOT>/evals/note-quality-rubric.md
- <REPO_ROOT>/evals/note-evaluator-prompt.md
- 论文集报告：<PAPER_SET_DOC>
- baseline manifest：<BASELINE_MANIFEST_DOC>
- candidate manifest：<CANDIDATE_MANIFEST_DOC>
- artifact audit report：<ARTIFACT_AUDIT_REPORT>

任务：
- 对每篇主测试论文，比较 raw baseline note 和 raw candidate note。
- 使用固定 rubric 的 hard gates 和 scored dimensions。
- 在可用时使用 source evidence 和 artifacts。
- 当 source evidence 缺失时，把相关 evidence-grounded dimensions 标为较低置信度。
- 标出内容提升、回归和平局。

约束：
- 不要重写或修补笔记。
- 不要重跑 DeepPaperNote。
- 除非 artifact 问题影响笔记质量，否则不要评价 artifact contract quality。
- 不要因为格式更整洁就判定内容质量提升。

输出：
- 写入 <NOTE_EVALUATION_REPORT>。
- 对每篇主测试论文包含 required rubric JSON。
- 添加每篇论文的简短比较总结和最终 per-paper verdict。
```

## 阶段 6：Regression Judgment

Regression Judge 综合：

- 论文集报告
- baseline manifest
- candidate manifest
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

对于 acquisition identity work，regression summary 必须分开记录两个字段：

- `architectural_improvement_only`：candidate 改善了 artifact reuse、
  provenance、canonical identity、repair trace 或 reporting clarity，但 final
  notes 没有可见质量提升。
- `final_note_visible_improvement`：candidate prevent/fix wrong identity、
  wrong PDF、metadata contradiction、missing source evidence、broken path、
  citation damage 或 comparable downstream failure，且这些问题会体现在生成笔记
  或 source evidence 中。

不要仅因为 resolve、metadata、fetch、canonical identity 或 repair trace artifacts
更干净、更完整，就把 acquisition architecture improvement 升级为 final note
quality improvement。

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
- architectural_improvement_only 与 final note-visible acquisition improvement
- 单篇论文改善
- 广泛真实改善
- 失败或无法得出结论的实验

### Regression Judge Agent Prompt Template

```text
/goal

目标：
判断本次回归实验是否支持声称 real improvement。

先读取：
- <REPO_ROOT>/evals/regression-workflow-zh.md
- <REPO_ROOT>/evals/note-quality-rubric.md
- 论文集报告：<PAPER_SET_DOC>
- baseline manifest：<BASELINE_MANIFEST_DOC>
- candidate manifest：<CANDIDATE_MANIFEST_DOC>
- artifact audit report：<ARTIFACT_AUDIT_REPORT>
- note evaluation report：<NOTE_EVALUATION_REPORT>

任务：
- 检查 runner success、artifact audit outcomes 和 note evaluation verdicts。
- 检查 acquisition identity improvements 属于 architectural_improvement_only 还是 final note-visible。
- 给出 per-paper verdict。
- 给出一个 experiment-level verdict。
- 判断是否可以声称 optimization success。
- 标出 next recommended action。

约束：
- 不要重跑工具。
- 不要编辑生成笔记。
- 不要用平均分覆盖 hard-gate failures。
- 不要因为 formatting-only gains 或单篇 cherry-picked paper 声称 real improvement。

输出：
- 写入 <REGRESSION_SUMMARY_DOC>。
- 包含 experiment id、baseline version、candidate version、paper list、runner settings summary、artifact audit summary、note evaluation summary、per-paper verdicts、experiment-level verdict 和 next recommended action。
```
