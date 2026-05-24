from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lint_note import (
    core_info_structure_issues,
    figure_structure_issues,
    figure_structure_passes,
    find_missing_sections,
    front_matter_order_warnings,
    has_figure_marker,
    inspect_note_plan,
    inspect_figure_callouts,
    inspect_substantive_content,
    math_render_issues,
    mechanical_translation_artifact_issues,
    mixed_language_issues,
    strip_frontmatter,
    suspicious_code_formatted_math,
    suspicious_mid_sentence_linebreaks,
)


def _valid_note_text() -> str:
    return """# Paper

## 核心信息

- 标题: Paper
- 发表时间: 2024
- DOI: 10.1234/example

## 原文摘要翻译

论文围绕长链路推理中的错误传播问题，提出一种把检索证据、工具调用状态和最终答案联合建模的框架，并报告了主要实验结论。

## 创新点

- 论文把检索证据选择和工具调用规划放在同一个状态转移过程里建模，使错误证据不会在后续步骤中被默认当成可靠输入。
- 论文设计了失败调用回溯机制，显式记录每一步工具返回的置信度和异常类型，从而让最终答案能区分证据不足和模型推理错误。

## 一句话总结

这篇论文用可审计的工具调用状态机降低长链路问答中的错误累积。

## 研究问题

论文关注多步问答系统在检索证据不完整、工具调用失败和中间状态被误用时，如何保持最终答案的可追溯性与可靠性。

## 数据与任务定义

任务输入包括用户问题、候选检索证据和可调用工具列表；输出包括最终答案、每一步工具调用记录以及失败原因标注。

## 方法主线

### 机制流程

输入问题先进入证据筛选模块，随后工具规划器选择下一步调用，最后由答案生成器结合状态日志输出可追溯结论。

> [!figure] 图一 方法概览
> 建议位置：方法主线
> 放置原因：帮助理解整体过程。
> 当前状态：保留占位；未找到高置信度整图。

## 关键结果

在三个多步问答数据集上，方法把答案准确率从 71.2% 提升到 78.5%，并将不可追溯错误比例从 18% 降到 9%。

## 深度分析

这项工作的关键价值不只是提升最终分数，而是把失败工具调用从隐藏中间状态变成可检查证据，因此适合需要审计链路的知识密集型问答。

## 局限

论文主要在英文问答数据上验证，工具集合也集中在检索和计算两类，尚未证明该状态机能稳定覆盖多模态工具或高延迟外部服务。

## 我的笔记

我会重点关注它的失败回溯机制是否能迁移到论文精读流程，因为 DeepPaperNote 同样需要区分证据缺失和模型总结不足。

## 引用

- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example
"""


def test_figure_callout_requires_status_line() -> None:
    note = """# Title

## 核心信息

> [!figure] Fig. 1 方法图
> 建议位置：方法主线
> 放置原因：帮助理解整体流程。
"""
    warnings = inspect_figure_callouts(note)
    assert "figure_callout_missing_status" in warnings


def test_legacy_placeholder_block_is_flagged() -> None:
    note = """# Title

[FIGURE_PLACEHOLDER]
id: Fig.1
[/FIGURE_PLACEHOLDER]
"""
    warnings = inspect_figure_callouts(note)
    assert "legacy_figure_placeholder_block_used" in warnings


def test_figure_bucket_heading_is_figure_structure_issue() -> None:
    note = """# Title

## 深度分析

### 剩余图表占位

> [!figure] Fig. 6 补充图
> 建议位置：深度分析
> 放置原因：帮助理解补充材料。
> 当前状态：保留占位；未找到高置信度整图。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "figure_placeholder_bucket_heading" for issue in issues)
    assert figure_structure_passes(note) is False


def test_figure_callout_target_section_mismatch_is_flagged() -> None:
    note = """# Title

## 深度分析

> [!figure] Fig. 1 问题边界图
> 建议位置：研究问题
> 放置原因：帮助定义问题边界。
> 当前状态：保留占位；未找到高置信度整图。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "figure_callout_placement_mismatch" for issue in issues)


def test_figure_callout_inside_declared_section_passes() -> None:
    note = """# Title

## 方法主线

### 机制流程

> [!figure] Fig. 2 总体流程
> 建议位置：方法主线
> 放置原因：帮助理解执行链。
> 当前状态：保留占位；未找到高置信度整图。

> [!figure] Fig. 3 机制细节
> 建议位置：机制流程
> 放置原因：帮助理解执行链细节。
> 当前状态：保留占位；未找到高置信度整图。
"""
    assert figure_structure_issues(note) == []
    assert figure_structure_passes(note) is True


def test_figure_callout_with_inserted_image_status_fails_figure_structure_gate() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 2 总体流程
> 建议位置：方法主线
> 放置原因：帮助理解执行链。
> 当前状态：已替换为真实图片；当前插入的是论文原图的局部面板。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "inserted_figure_redundant_callout" for issue in issues)
    assert figure_structure_passes(note) is False


def test_dqn_style_callout_plus_embed_fails_figure_structure_gate() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 1 Agent-environment loop
> 建议位置：方法主线
> 放置原因：帮助理解强化学习交互闭环。
> 当前状态：已复制到 images/figure_1.png，并插入为真实图片。
![[Research/Papers/DQN/images/figure_1.png]]
*论文原图编号：Fig. 1。Agent-environment loop。*
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "inserted_figure_redundant_callout" for issue in issues)
    assert figure_structure_passes(note) is False


def test_non_figure_remaining_heading_is_not_flagged() -> None:
    note = """# Title

## 深度分析

### 剩余问题

这里讨论论文还没有回答的问题。
"""
    assert figure_structure_issues(note) == []


def test_figure_callout_missing_location_fails_figure_structure_gate() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 1 方法图
> 放置原因：帮助理解整体流程。
> 当前状态：保留占位；未找到高置信度整图。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "figure_callout_missing_location" for issue in issues)
    assert figure_structure_passes(note) is False


def test_figure_callout_missing_title_fails_figure_structure_gate() -> None:
    note = """# Title

## 方法主线

> [!figure]
> 建议位置：方法主线
> 放置原因：帮助理解整体流程。
> 当前状态：保留占位；未找到高置信度整图。
"""
    warnings = inspect_figure_callouts(note)
    issues = figure_structure_issues(note)
    assert "figure_callout_missing_title" in warnings
    assert any(issue["reason"] == "figure_callout_missing_title" for issue in issues)
    assert figure_structure_passes(note) is False


def test_nonstandard_bracket_figure_placeholder_fails_figure_structure_gate() -> None:
    note = """# Title

## 研究问题

[图表占位 | Fig. 1] 论文给出的整体任务示意图。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "nonstandard_figure_placeholder_format" for issue in issues)
    assert figure_structure_passes(note) is False


def test_nonstandard_colon_and_english_figure_placeholders_fail_gate() -> None:
    note = """# Title

## 关键结果

图表占位：Table 2 跨数据集结果。

Figure Placeholder | Fig. 3 reasoning example.
"""
    issues = figure_structure_issues(note)
    assert len([issue for issue in issues if issue["reason"] == "nonstandard_figure_placeholder_format"]) == 2
    assert figure_structure_passes(note) is False


def test_image_embed_without_italic_caption_fails_figure_structure_gate() -> None:
    note = """# Title

## 方法主线

![Fig. 2 Architecture](images/page_005_fig_figure_2.png)
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "inserted_figure_missing_caption" for issue in issues)
    assert figure_structure_passes(note) is False


def test_flashattention_style_embed_with_italic_caption_passes() -> None:
    note = """# Title

## 方法主线

![[Research/Papers/FlashAttention/images/page_005_fig_figure_2.png]]
*论文原图编号：Fig. 2。FlashAttention 的分块计算流程图。这里插入是因为它最能帮助理解方法主线。*
"""
    assert figure_structure_issues(note) == []
    assert figure_structure_passes(note) is True
    assert has_figure_marker(note) is True


def test_usable_candidate_soft_placeholder_reasons_fail_figure_structure_gate() -> None:
    statuses = [
        "图像裁剪可读，但最终笔记采用占位以保持轻量。",
        "图像匹配度高，但最终笔记不插入真实图片。",
        "表格裁剪清晰，但正文已摘录核心数值。",
        "虽然有可用候选图，但表格内容在正文中更适合直接转写关键数值。",
        "已人工查看，裁剪清晰且图号匹配；但 Fig. 1 已承担主流程说明，因此作为低优先级补充图保留占位。",
        "已人工查看，图像清晰且图号匹配；由于它服务于辅助集说明，而非主结论，因此作为低优先级补充图保留占位。",
    ]
    for status in statuses:
        note = f"""# Title

## 方法主线

> [!figure] Fig. 2 候选图
> 建议位置：方法主线
> 放置原因：帮助理解执行链。
> 当前状态：{status}
"""
        issues = figure_structure_issues(note)
        assert any(issue["reason"] == "usable_candidate_unresolved_decision" for issue in issues)
        assert figure_structure_passes(note) is False


def test_usable_candidate_visual_defect_placeholder_reason_passes() -> None:
    note = """# Title

## 方法主线

> [!figure] Table 5 评测表
> 建议位置：方法主线
> 放置原因：帮助理解评测协议。
> 当前状态：候选裁剪可用，但混入相邻 Table 6。
"""
    assert figure_structure_issues(note) == []
    assert figure_structure_passes(note) is True


def test_usable_candidate_lower_priority_placeholder_reason_fails() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 3 补充机制图
> 建议位置：方法主线
> 放置原因：帮助理解补充机制。
> 当前状态：候选裁剪可用；已插入 Figure 2 作为同一机制更核心图，因此本图低优先级。
"""
    issues = figure_structure_issues(note)
    assert any(issue["reason"] == "usable_candidate_unresolved_decision" for issue in issues)
    assert figure_structure_passes(note) is False


def test_usable_candidate_materialization_blocked_reason_passes() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 4 工具链图
> 建议位置：方法主线
> 放置原因：帮助理解工具链。
> 当前状态：候选可用但 materialize_figure_asset.py 复制失败/权限不足。
"""
    assert figure_structure_issues(note) == []
    assert figure_structure_passes(note) is True


def test_missing_asset_must_not_be_reported_as_materialization_blocked() -> None:
    note = """# Title

## 方法主线

> [!figure] Fig. 4 系统图
> 建议位置：方法主线
> 放置原因：帮助理解整体执行链。
> 当前状态：保留占位：对应图像资产缺失导致 materialize_figure_asset.py 复制 blocked；保留结构占位用于回查原图。
"""
    issues = figure_structure_issues(note)
    assert any(
        issue["reason"] == "missing_asset_misreported_as_materialization_blocked"
        for issue in issues
    )
    assert figure_structure_passes(note) is False


def test_chinese_placeholder_policy_prose_is_not_flagged_as_nonstandard_placeholder() -> None:
    note = """# Title

## 深度分析

这里讨论图表占位策略为什么不能替代正文分析。
"""
    assert figure_structure_issues(note) == []


def test_mechanical_translation_detector_flags_figure_title_artifacts() -> None:
    note = "> [!figure] Figure 7 Storing the KV缓存 of two requests at the same time in vLLM"

    issues = mechanical_translation_artifact_issues(note)

    assert len(issues) == 1
    assert issues[0]["artifact"]


def test_mechanical_translation_detector_flags_metadata_artifacts() -> None:
    note = "- 机构: UC Berkeley, Stanford University, In相关 Researcher, UC San Diego"

    issues = mechanical_translation_artifact_issues(note)

    assert len(issues) == 1
    assert issues[0]["line_number"] == 1


def test_mechanical_translation_detector_accepts_stable_proper_nouns() -> None:
    note = "> [!figure] Fig. 2 Overview of the training pipeline，训练流程概览。"

    assert mechanical_translation_artifact_issues(note) == []


def test_mixed_language_detector_flags_prose_line() -> None:
    note = "这篇论文 uses a model and the result is better than baseline in several settings."
    issues = mixed_language_issues(note)
    assert len(issues) == 1


def test_mixed_language_detector_exempts_figure_status_lines() -> None:
    note = "> 当前状态：保留占位；当前提取结果只拿到 partial crop，无法稳定恢复。"
    issues = mixed_language_issues(note)
    assert issues == []


def test_mixed_language_detector_exempts_figure_callout_title_only() -> None:
    note = "> [!figure] Fig. 2 Overview of the training pipeline，训练流程概览。"
    issues = mixed_language_issues(note)
    assert issues == []


def test_mixed_language_detector_flags_ordinary_blockquote_prose() -> None:
    note = "> 这段解释 uses a model and the result is better than baseline in experiments."
    issues = mixed_language_issues(note)
    assert len(issues) == 1


def test_mixed_language_detector_exempts_core_info_section() -> None:
    note = """## 核心信息

- 标题：
`AffectGPT: A New Dataset, Model, and Benchmark for Emotion Understanding with Multimodal Large Language Models`
- 作者：
Zheng Lian, Haoyu Chen, Lan Chen
- 机构：
Institute of Automation, Chinese Academy of Sciences
"""
    issues = mixed_language_issues(note)
    assert issues == []


def test_mixed_language_detector_exempts_core_info_wrapped_value_lines() -> None:
    note = """## 核心信息

- 作者：
Zheng Lian, Haoyu Chen, Lan Chen, Haiyang Sun
and additional collaborators from multiple institutions
"""
    issues = mixed_language_issues(note)
    assert issues == []


def test_mixed_language_detector_flags_summary_section_when_mixed() -> None:
    note = """## 原文摘要翻译

这篇论文 uses a multimodal framework and achieves strong performance.
"""
    issues = mixed_language_issues(note)
    assert len(issues) == 1


def test_mid_sentence_linebreak_detector_flags_pdf_style_wrapping() -> None:
    note = "这篇论文最重要的贡献在于，\n它重新定义了视觉自回归的预测顺序。"
    issues = suspicious_mid_sentence_linebreaks(note)
    assert len(issues) == 1


def test_mid_sentence_linebreak_detector_ignores_real_paragraph_breaks() -> None:
    note = "这篇论文最重要的贡献在于重新定义了视觉自回归的预测顺序。\n\n## 方法主线"
    issues = suspicious_mid_sentence_linebreaks(note)
    assert issues == []


def test_code_formatted_math_detector_flags_inline_code_formula() -> None:
    note = "核心分解可以写成 `p(r_1, r_2)=\\prod_k p(r_k | r_{<k})`。"
    issues = suspicious_code_formatted_math(note)
    assert len(issues) == 1


def test_code_formatted_math_detector_flags_fenced_formula_block() -> None:
    note = """```
L = x + y
```"""
    issues = suspicious_code_formatted_math(note)
    assert len(issues) == 1


def test_math_render_detector_flags_double_escaped_tex_command() -> None:
    note = """## 方法主线

$$
\\\\tau = \\\\exp(x)
$$
"""
    issues = math_render_issues(note)
    assert any(issue["reason"] == "double_escaped_tex_command" for issue in issues)


def test_math_render_detector_flags_invalid_frac_arguments() -> None:
    note = r"""$$
\mathrm{Precision} =
\frac{a}
\left|b\right|}
$$
"""
    issues = math_render_issues(note)
    assert any(issue["reason"] == "invalid_frac_arguments" for issue in issues)


def test_math_render_detector_flags_environment_mismatch() -> None:
    note = r"""$$
\begin{cases}
a
$$
"""
    issues = math_render_issues(note)
    assert any(issue["reason"] == "environment_mismatch" for issue in issues)


def test_math_render_detector_flags_left_right_mismatch() -> None:
    note = r"""$$
\left| x + y
$$
"""
    issues = math_render_issues(note)
    assert any(issue["reason"] == "left_right_mismatch" for issue in issues)


def test_math_render_detector_flags_unbalanced_braces() -> None:
    note = r"""$$
\bar{R_t
$$
"""
    issues = math_render_issues(note)
    assert any(issue["reason"] == "unbalanced_braces" for issue in issues)


def test_math_render_detector_accepts_valid_cases_formula() -> None:
    note = r"""$$
\tau =
\begin{cases}
1, & \bar R_t^{(c)} \ge \bar R_t^{(w)} \\
\exp(\bar R_t^{(c)} - \bar R_t^{(w)}), & \bar R_t^{(c)} < \bar R_t^{(w)}
\end{cases}
$$
"""
    issues = math_render_issues(note)
    assert issues == []


def test_find_missing_sections_requires_innovation_section() -> None:
    note = """# Title

## 核心信息

## 原文摘要翻译

## 一句话总结

## 研究问题

## 数据与任务定义

## 方法主线

## 关键结果

## 深度分析

## 局限

## 我的笔记

## 引用
"""
    missing = find_missing_sections(note)
    assert "创新点" in missing


def test_substantive_gate_passes_specific_note() -> None:
    issues = inspect_substantive_content(_valid_note_text())

    assert issues == []


def test_substantive_gate_rejects_empty_shell_innovation() -> None:
    note = _valid_note_text().replace(
        "- 论文把检索证据选择和工具调用规划放在同一个状态转移过程里建模，使错误证据不会在后续步骤中被默认当成可靠输入。\n"
        "- 论文设计了失败调用回溯机制，显式记录每一步工具返回的置信度和异常类型，从而让最终答案能区分证据不足和模型推理错误。",
        "本文提出一种新方法，具有创新性。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "innovation_empty_shell" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_substantive_gate_warns_single_specific_innovation() -> None:
    note = _valid_note_text().replace(
        "- 论文把检索证据选择和工具调用规划放在同一个状态转移过程里建模，使错误证据不会在后续步骤中被默认当成可靠输入。\n"
        "- 论文设计了失败调用回溯机制，显式记录每一步工具返回的置信度和异常类型，从而让最终答案能区分证据不足和模型推理错误。",
        "- 论文把检索证据选择和工具调用规划放在同一个状态转移过程里建模，使错误证据不会在后续步骤中被默认当成可靠输入。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "innovation_too_few_specific_points" for issue in issues)
    assert all(issue["severity"] != "error" for issue in issues)


def test_substantive_gate_rejects_generic_key_results() -> None:
    note = _valid_note_text().replace(
        "在三个多步问答数据集上，方法把答案准确率从 71.2% 提升到 78.5%，并将不可追溯错误比例从 18% 降到 9%。",
        "实验结果表明方法有效。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "key_results_empty_shell" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_substantive_gate_rejects_honest_missing_in_key_results() -> None:
    note = _valid_note_text().replace(
        "在三个多步问答数据集上，方法把答案准确率从 71.2% 提升到 78.5%，并将不可追溯错误比例从 18% 降到 9%。",
        "本文未给出可复现的定量 benchmark；依据是正文和附录都只报告案例分析，没有指标表或 baseline 对比，因此这里不能伪造数值结论，只能说明结论强度受限。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "key_results_honest_missing_not_allowed" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_substantive_gate_rejects_honest_missing_outside_references() -> None:
    note = _valid_note_text().replace(
        "输入问题先进入证据筛选模块，随后工具规划器选择下一步调用，最后由答案生成器结合状态日志输出可追溯结论。",
        "本文未给出可复现的方法流程；依据是正文和附录都没有展开模块输入输出，因此这里不能补写机制细节，只能说明方法理解受限。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "section_honest_missing_not_allowed" for issue in issues)
    assert any(issue["section"] == "方法主线" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_substantive_gate_rejects_placeholder_references() -> None:
    note = _valid_note_text().replace(
        "- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example",
        "待补充。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "references_placeholder" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_substantive_gate_accepts_real_reference_entry() -> None:
    note = _valid_note_text().replace(
        "- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example",
        "- [[Auditable Tool Use|Smith et al. 2024]] 提供了工具调用审计的直接参考。",
    )

    issues = inspect_substantive_content(note)

    assert not any(issue["section"] == "引用" for issue in issues)


def test_substantive_gate_allows_honest_missing_in_references() -> None:
    note = _valid_note_text().replace(
        "- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example",
        "本文未给出可解析的参考文献条目；依据是正文和附录未提供 DOI、arXiv 或编号引用，因此引用完整性受限。",
    )

    issues = inspect_substantive_content(note)

    assert not any(issue["severity"] == "error" for issue in issues)
    assert any(issue["reason"] == "references_unavailable_declared" for issue in issues)


def test_substantive_gate_rejects_generic_limitation() -> None:
    note = _valid_note_text().replace(
        "论文主要在英文问答数据上验证，工具集合也集中在检索和计算两类，尚未证明该状态机能稳定覆盖多模态工具或高延迟外部服务。",
        "未来工作需要更多数据。",
    )

    issues = inspect_substantive_content(note)

    assert any(issue["reason"] == "limitations_empty_shell" for issue in issues)
    assert any(issue["severity"] == "error" for issue in issues)


def test_strip_frontmatter_removes_yaml_block() -> None:
    text = "---\ntags:\n  - papers/NLP\ndate: 2024-01-01\n---\n\n# Title\n\n## 核心信息\n"
    assert strip_frontmatter(text).lstrip().startswith("# Title")


def test_strip_frontmatter_is_noop_without_frontmatter() -> None:
    text = "# Title\n\n## 核心信息\n"
    assert strip_frontmatter(text) == text


def test_title_heading_not_flagged_when_frontmatter_present() -> None:
    # A note that starts with YAML frontmatter should NOT trigger title_heading_missing.
    # We test via strip_frontmatter directly since main() does I/O.
    text = "---\ntags:\n  - papers/NLP\naliases:\n  - MyPaper\ndate: 2024-01-01\ndoi: 10.1234/test\n---\n\n# My Paper Title\n"
    assert strip_frontmatter(text).lstrip().startswith("# ")


def test_mid_sentence_linebreaks_not_triggered_by_frontmatter() -> None:
    # Frontmatter lines like "date: 2024-01-01\ndoi: 10.xxx" must not be treated as
    # mid-sentence prose linebreaks.
    frontmatter_only = "---\ntags:\n  - papers/NLP\naliases:\n  - MyPaper\ndate: 2024-01-01\ndoi: 10.1234/test\n---\n"
    issues = suspicious_mid_sentence_linebreaks(strip_frontmatter(frontmatter_only))
    assert issues == []


def test_front_matter_order_requires_innovation_after_abstract() -> None:
    note = """# Title

## 核心信息

## 原文摘要翻译

## 一句话总结

## 创新点
"""
    warnings = front_matter_order_warnings(note)
    assert "front_matter_order_invalid" in warnings


def test_core_info_accepts_fixed_metadata_schema() -> None:
    note = """# Title

## 核心信息

- 标题: Example Paper
- 标题翻译: 示例论文
- 作者: Ada Lovelace; Alan Turing
- 机构: Example Lab
- 发表时间: 2024
- 发表渠道: arXiv
- DOI: 10.1234/example
- arXiv: 2401.00001
- 论文链接: https://arxiv.org/abs/2401.00001
- 代码 / 项目: https://github.com/example/project
- 数据 / 资源: https://example.org/data
- 论文类型: AI_method

## 原文摘要翻译
"""

    assert core_info_structure_issues(note) == []


def test_core_info_rejects_prose_and_ad_hoc_fields() -> None:
    note = """# Title

## 核心信息

- 标题: Example Paper
- 作者: Ada Lovelace
- 我的评价: 很重要

这篇论文的核心不是提出新模型，而是建立一个评测场。

## 原文摘要翻译
"""

    issues = core_info_structure_issues(note)

    assert any(issue["reason"] == "core_info_unknown_field" for issue in issues)
    assert any(issue["reason"] == "core_info_non_metadata_line" for issue in issues)


def test_core_info_rejects_out_of_order_fields() -> None:
    note = """# Title

## 核心信息

- 作者: Ada Lovelace
- 标题: Example Paper

## 原文摘要翻译
"""

    issues = core_info_structure_issues(note)

    assert any(issue["reason"] == "core_info_field_order_invalid" for issue in issues)


def test_core_info_issues_fail_basic_structure_gate(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    plan_path = tmp_path / "Paper.plan.json"
    note_path.write_text(
        _valid_note_text().replace(
            "- DOI: 10.1234/example",
            "- DOI: 10.1234/example\n\n这篇论文在元数据块里追加了一句导读。",
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "method paper",
                "dominant_domain": "NLP",
                "must_cover": ["problem", "method"],
                "key_numbers": ["78.5"],
                "real_comparisons": ["baseline"],
                "central_claims": [
                    {
                        "claim": "The method improves traceability.",
                        "supporting_evidence": [{"section_id": "sec:method"}],
                        "what_it_actually_proves": "The described mechanism records tool states.",
                        "what_it_does_not_prove": "It does not prove production robustness.",
                    }
                ],
                "claim_boundaries": ["The evidence is limited to the reported workflow."],
                "negative_or_limiting_results": ["The paper does not report multi-service failures."],
                "mechanism_result_map": ["The failure-state mechanism explains lower unrecoverable errors."],
                "comparative_positioning": ["The method is compared against answer-only baselines."],
                "reuse_takeaways": ["Track failure state explicitly."],
                "followup_questions": ["Check whether the mechanism survives missing tool outputs."],
                "section_plan": [{"section": "方法主线", "evidence_sources": [{"section_id": "sec:method"}]}],
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--input",
            str(note_path),
            "--plan-file",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["passes_basic_structure"] is False
    assert "core_info_non_metadata_line" in payload["warnings"]


def test_note_plan_missing_fails_plan_gate(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    note_path.write_text(_valid_note_text(), encoding="utf-8")

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--input", str(note_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["planning_artifact_found"] is False
    assert payload["planning_artifact_issues"] == ["planning_artifact_missing"]
    assert "planning_artifact_missing" in payload["warnings"]
    assert payload["passes_basic_structure"] is True
    assert payload["passes_style_gate"] is True
    assert payload["passes_math_gate"] is True
    assert payload["passes_figure_gate"] is True
    assert payload["passes_plan_gate"] is False


def test_mechanical_translation_artifacts_fail_style_gate(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    plan_path = tmp_path / "Paper.plan.json"
    note_path.write_text(
        _valid_note_text().replace(
            "放置原因：帮助理解整体过程。",
            "放置原因：Figure 7 Storing the KV缓存 of two requests.",
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "The paper proposes a model mechanism and evaluates it experimentally.",
                "dominant_domain": "reasoning",
                "must_cover": ["方法主线"],
                "key_numbers": ["78.5"],
                "real_comparisons": ["baseline"],
                "central_claims": [
                    {
                        "claim": "The method improves traceability.",
                        "supporting_evidence": [{"section_id": "sec:method"}],
                        "what_it_actually_proves": "The described mechanism records tool states.",
                        "what_it_does_not_prove": "It does not prove production robustness.",
                    }
                ],
                "claim_boundaries": ["The evidence is limited to the reported workflow."],
                "negative_or_limiting_results": ["The paper does not report multi-service failures."],
                "mechanism_result_map": ["The failure-state mechanism explains lower unrecoverable errors."],
                "comparative_positioning": ["The method is compared against answer-only baselines."],
                "reuse_takeaways": ["Track failure state explicitly."],
                "followup_questions": ["Check whether the mechanism survives missing tool outputs."],
                "section_plan": [{"section": "方法主线", "evidence_sources": [{"section_id": "sec:method"}]}],
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--input",
            str(note_path),
            "--plan-file",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["passes_style_gate"] is False
    assert "mechanical_translation_artifacts_present" in payload["warnings"]
    assert payload["mechanical_translation_artifact_issues"]


def test_note_plan_empty_required_values_fail_plan_gate(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    plan_path = tmp_path / "Paper.plan.json"
    note_path.write_text(_valid_note_text(), encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "",
                "paper_type_rationale": "",
                "dominant_domain": "   ",
                "must_cover": [],
                "key_numbers": [],
                "real_comparisons": [],
                "central_claims": [],
                "claim_boundaries": [],
                "negative_or_limiting_results": [],
                "mechanism_result_map": [],
                "comparative_positioning": [],
                "reuse_takeaways": [],
                "followup_questions": [],
                "section_plan": [],
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--input", str(note_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["planning_artifact_found"] is True
    assert payload["passes_plan_gate"] is False
    assert payload["planning_artifact_issues"] == [
        "planning_paper_type_empty",
        "planning_paper_type_rationale_empty",
        "planning_dominant_domain_empty",
        "planning_must_cover_empty",
        "planning_key_numbers_empty",
        "planning_real_comparisons_empty",
        "planning_central_claims_empty",
        "planning_claim_boundaries_empty",
        "planning_negative_or_limiting_results_empty",
        "planning_mechanism_result_map_empty",
        "planning_comparative_positioning_empty",
        "planning_reuse_takeaways_empty",
        "planning_followup_questions_empty",
        "planning_section_plan_empty",
    ]


def test_note_plan_explicit_not_reported_entries_pass_plan_gate(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    plan_path = tmp_path / "Paper.plan.json"
    note_path.write_text(_valid_note_text(), encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "The paper proposes a model mechanism and evaluates it experimentally.",
                "dominant_domain": "reasoning",
                "must_cover": ["方法主线"],
                "key_numbers": ["论文未报告明确核心数字"],
                "real_comparisons": ["论文未提供直接对比"],
                "central_claims": [
                    {
                        "claim": "The paper offers a method mechanism.",
                        "supporting_evidence": [{"section_id": "sec:method"}],
                        "what_it_actually_proves": "The mechanism is described in source sections.",
                        "what_it_does_not_prove": "It does not prove all deployment cases.",
                    }
                ],
                "claim_boundaries": ["The comparison evidence is limited."],
                "negative_or_limiting_results": ["论文未清楚报告负向消融。"],
                "mechanism_result_map": ["The state log explains why errors can be recovered."],
                "comparative_positioning": ["The method is positioned against answer-only tool use."],
                "reuse_takeaways": ["Use explicit state logs when evaluating tool chains."],
                "followup_questions": ["Test the state log with slower external tools."],
                "section_plan": [{"section": "方法主线"}],
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--input", str(note_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["planning_artifact_issues"] == []
    assert payload["passes_plan_gate"] is True


def test_write_obsidian_note_refuses_failed_plan_gate(tmp_path) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
                "passes_figure_gate": True,
                "passes_plan_gate": False,
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Plan Gate Paper",
            "--content",
            "# Plan Gate Paper",
            "--lint-json",
            str(lint_path),
            "--vault",
            str(tmp_path / "vault"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "plan gate failed" in result.stderr


def test_real_image_embed_counts_as_figure_marker_in_full_lint(tmp_path) -> None:
    note_path = tmp_path / "Paper.md"
    note_path.write_text(
        """# Paper

## 核心信息

这是一条完整元信息占位。

## 原文摘要翻译

这是一段中文摘要翻译。

## 创新点

这里记录论文的具体创新。

## 一句话总结

这篇论文解决一个清晰问题。

## 研究问题

问题边界描述清楚。

## 数据与任务定义

任务输入和输出定义清楚。

## 方法主线

### 执行流程

这里说明方法过程。

![[Research/Papers/Paper/images/page_001_fig_figure_1.png]]
*论文原图编号：Fig. 1。方法流程图。*

## 关键结果

结果部分记录关键发现。

## 深度分析

分析部分说明为什么成立。

## 局限

这里记录限制。

## 我的笔记

这里记录个人理解。

## 引用

这里记录引用信息。
""",
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "lint_note.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--input", str(note_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert "no_figure_markers" not in payload["warnings"]
    assert payload["passes_figure_gate"] is True
    assert payload["passes_substantive_content"] is False
    assert any(
        issue["reason"] == "innovation_empty_shell"
        for issue in payload["substantive_content_issues"]
    )


def test_write_obsidian_note_refuses_failed_substantive_gate(tmp_path) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
                "passes_figure_gate": True,
                "passes_plan_gate": True,
                "passes_substantive_content": False,
            }
        ),
        encoding="utf-8",
    )

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Substantive Gate Paper",
            "--content",
            "# Substantive Gate Paper",
            "--lint-json",
            str(lint_path),
            "--vault",
            str(tmp_path / "vault"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "substantive content gate failed" in result.stderr


def passing_lint_payload() -> dict:
    return {
        "passes_basic_structure": True,
        "passes_style_gate": True,
        "passes_math_gate": True,
        "passes_figure_gate": True,
        "passes_plan_gate": True,
        "passes_substantive_content": True,
    }


def test_write_obsidian_note_materializes_insert_decision(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_image = tmp_path / "page_001_fig_figure_1.png"
    source_image.write_bytes(b"fake-png")
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(json.dumps(passing_lint_payload()), encoding="utf-8")
    decisions_path = tmp_path / "figure_decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "source_id": "Figure 1",
                        "decision": "insert",
                        "source_image_path": str(source_image),
                        "source_image_filename": source_image.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "write.json"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Figure Insert Paper",
            "--filename",
            "Figure Insert Paper.md",
            "--subdir",
            "Research/Papers/Figure Insert Paper",
            "--content",
            "# Figure Insert Paper\n\n![Figure 1](images/page_001_fig_figure_1.png)\n*Fig. 1 caption.*\n",
            "--lint-json",
            str(lint_path),
            "--figure-decisions",
            str(decisions_path),
            "--vault",
            str(vault),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    materialized = payload["materialized_figures"][0]
    assert materialized["relative_markdown_path"] == "images/page_001_fig_figure_1.png"
    assert Path(materialized["dest_image_path"]).read_bytes() == b"fake-png"


def test_write_obsidian_note_rejects_unreferenced_insert_decision(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_image = tmp_path / "page_001_fig_figure_1.png"
    source_image.write_bytes(b"fake-png")
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(json.dumps(passing_lint_payload()), encoding="utf-8")
    decisions_path = tmp_path / "figure_decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "source_id": "Figure 1",
                        "decision": "insert",
                        "source_image_path": str(source_image),
                        "source_image_filename": source_image.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Figure Insert Paper",
            "--content",
            "# Figure Insert Paper\n\n正文没有引用图片。\n",
            "--lint-json",
            str(lint_path),
            "--figure-decisions",
            str(decisions_path),
            "--vault",
            str(vault),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "is not referenced as an image embed" in result.stderr


def test_write_obsidian_note_rejects_plain_path_for_insert_decision(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_image = tmp_path / "page_001_fig_figure_1.png"
    source_image.write_bytes(b"fake-png")
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(json.dumps(passing_lint_payload()), encoding="utf-8")
    decisions_path = tmp_path / "figure_decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "source_id": "Figure 1",
                        "decision": "insert",
                        "source_image_path": str(source_image),
                        "source_image_filename": source_image.name,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Figure Insert Paper",
            "--content",
            "# Figure Insert Paper\n\n正文只提到 images/page_001_fig_figure_1.png 这个路径。\n",
            "--lint-json",
            str(lint_path),
            "--figure-decisions",
            str(decisions_path),
            "--vault",
            str(vault),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "is not referenced as an image embed" in result.stderr


def test_write_obsidian_note_rejects_unsafe_insert_filename(tmp_path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_image = tmp_path / "page_001_fig_figure_1.png"
    source_image.write_bytes(b"fake-png")
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(json.dumps(passing_lint_payload()), encoding="utf-8")
    decisions_path = tmp_path / "figure_decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "source_id": "Figure 1",
                        "decision": "insert",
                        "source_image_path": str(source_image),
                        "source_image_filename": "../escaped.png",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "write_obsidian_note.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--title",
            "Figure Insert Paper",
            "--content",
            "# Figure Insert Paper\n\n![Figure 1](images/../escaped.png)\n*Fig. 1 caption.*\n",
            "--lint-json",
            str(lint_path),
            "--figure-decisions",
            str(decisions_path),
            "--vault",
            str(vault),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Unsafe figure image filename" in result.stderr


def test_inspect_note_plan_reports_missing_file(tmp_path) -> None:
    found, issues = inspect_note_plan(tmp_path / "missing.plan.json")
    assert found is False
    assert issues == ["planning_artifact_missing"]


def test_inspect_note_plan_reports_invalid_json(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text("{not-json", encoding="utf-8")

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert issues == ["planning_artifact_invalid_json"]


def test_inspect_note_plan_reports_missing_required_fields(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(json.dumps({"paper_type": "AI_method"}), encoding="utf-8")

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert "planning_required_fields_missing" in issues


def test_inspect_note_plan_rejects_invalid_paper_type(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "method",
                "paper_type_rationale": "The model-facing plan should use the shared paper type enum.",
                "dominant_domain": "reasoning",
                "must_cover": ["方法主线"],
                "key_numbers": ["42"],
                "real_comparisons": ["baseline"],
                "central_claims": [
                    {
                        "claim": "The method improves a target behavior.",
                        "supporting_evidence": [{"section_id": "sec:method"}],
                        "what_it_actually_proves": "The source states the mechanism and reported setting.",
                        "what_it_does_not_prove": "It does not prove all deployment cases.",
                    }
                ],
                "claim_boundaries": ["The claim is limited to reported settings."],
                "negative_or_limiting_results": ["No external failure case is reported."],
                "mechanism_result_map": ["The mechanism explains the reported target behavior."],
                "comparative_positioning": ["The plan names the relevant baseline comparison."],
                "reuse_takeaways": ["Track the mechanism separately from the final result."],
                "followup_questions": ["Check whether the mechanism transfers to a new dataset."],
                "section_plan": [{"section": "方法主线"}],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert "planning_paper_type_invalid" in issues


def test_inspect_note_plan_reports_invalid_field_types(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "The paper proposes a model mechanism.",
                "dominant_domain": "reasoning",
                "must_cover": "method",
                "key_numbers": [],
                "real_comparisons": [],
                "central_claims": "not-a-list",
                "claim_boundaries": [],
                "negative_or_limiting_results": [],
                "mechanism_result_map": [],
                "comparative_positioning": [],
                "reuse_takeaways": [],
                "followup_questions": [],
                "section_plan": [{"section": "方法主线"}],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert "planning_required_fields_invalid" in issues


def test_inspect_note_plan_reports_empty_section_plan(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "The paper proposes a model mechanism.",
                "dominant_domain": "reasoning",
                "must_cover": [],
                "key_numbers": [],
                "real_comparisons": [],
                "central_claims": [],
                "claim_boundaries": [],
                "negative_or_limiting_results": [],
                "mechanism_result_map": [],
                "comparative_positioning": [],
                "reuse_takeaways": [],
                "followup_questions": [],
                "section_plan": [],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert issues == [
        "planning_must_cover_empty",
        "planning_key_numbers_empty",
        "planning_real_comparisons_empty",
        "planning_central_claims_empty",
        "planning_claim_boundaries_empty",
        "planning_negative_or_limiting_results_empty",
        "planning_mechanism_result_map_empty",
        "planning_comparative_positioning_empty",
        "planning_reuse_takeaways_empty",
        "planning_followup_questions_empty",
        "planning_section_plan_empty",
    ]


def test_inspect_note_plan_accepts_valid_plan(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "paper_type_rationale": "The paper proposes a model mechanism.",
                "dominant_domain": "reasoning",
                "must_cover": ["方法主线"],
                "key_numbers": ["42"],
                "real_comparisons": ["baseline"],
                "central_claims": [
                    {
                        "claim": "The method improves a target behavior.",
                        "supporting_evidence": [{"section_id": "sec:method"}],
                        "what_it_actually_proves": "The source states the mechanism and reported setting.",
                        "what_it_does_not_prove": "It does not prove all deployment cases.",
                    }
                ],
                "claim_boundaries": ["The claim is limited to reported settings."],
                "negative_or_limiting_results": ["No external failure case is reported."],
                "mechanism_result_map": ["The mechanism explains the reported target behavior."],
                "comparative_positioning": ["The plan names the relevant baseline comparison."],
                "reuse_takeaways": ["Track the mechanism separately from the final result."],
                "followup_questions": ["Check whether the mechanism transfers to a new dataset."],
                "section_plan": [{"section": "方法主线"}],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert issues == []
