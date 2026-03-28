from __future__ import annotations

from lint_note import (
    abstract_translation_warnings,
    inspect_figure_callouts,
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


def test_abstract_translation_warning_when_only_english_abstract_exists() -> None:
    note = """## 原始摘要

### 英文原文

> We present a model.
"""
    warnings = abstract_translation_warnings(note)
    assert "abstract_translation_missing" in warnings
