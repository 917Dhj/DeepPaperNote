from __future__ import annotations

from lint_note import (
    find_missing_sections,
    front_matter_order_warnings,
    inspect_figure_callouts,
    math_render_issues,
    mixed_language_issues,
    suspicious_code_formatted_math,
    suspicious_mid_sentence_linebreaks,
)


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


def test_mixed_language_detector_flags_prose_line() -> None:
    note = "这篇论文 uses a model and the result is better than baseline in several settings."
    issues = mixed_language_issues(note)
    assert len(issues) == 1


def test_mixed_language_detector_exempts_figure_status_lines() -> None:
    note = "> 当前状态：保留占位；当前提取结果只拿到 partial crop，无法稳定恢复。"
    issues = mixed_language_issues(note)
    assert issues == []


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


def test_front_matter_order_requires_innovation_after_abstract() -> None:
    note = """# Title

## 核心信息

## 原文摘要翻译

## 一句话总结

## 创新点
"""
    warnings = front_matter_order_warnings(note)
    assert "front_matter_order_invalid" in warnings
