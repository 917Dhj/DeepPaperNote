from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lint_note import (
    figure_structure_issues,
    figure_structure_passes,
    find_missing_sections,
    front_matter_order_warnings,
    has_figure_marker,
    inspect_note_plan,
    inspect_figure_callouts,
    math_render_issues,
    mixed_language_issues,
    strip_frontmatter,
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


def test_chinese_placeholder_policy_prose_is_not_flagged_as_nonstandard_placeholder() -> None:
    note = """# Title

## 深度分析

这里讨论图表占位策略为什么不能替代正文分析。
"""
    assert figure_structure_issues(note) == []


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


def test_note_plan_missing_is_soft_lint_warning(tmp_path) -> None:
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

> [!figure] 图一 方法概览
> 建议位置：方法主线
> 放置原因：帮助理解整体过程。
> 当前状态：保留占位；未找到高置信度整图。

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

    assert payload["planning_artifact_found"] is False
    assert payload["planning_artifact_issues"] == ["planning_artifact_missing"]
    assert "planning_artifact_missing" in payload["warnings"]
    assert payload["passes_basic_structure"] is True
    assert payload["passes_style_gate"] is True
    assert payload["passes_math_gate"] is True
    assert payload["passes_figure_gate"] is True


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


def test_inspect_note_plan_reports_invalid_field_types(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "dominant_domain": "reasoning",
                "must_cover": "method",
                "key_numbers": [],
                "real_comparisons": [],
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
                "dominant_domain": "reasoning",
                "must_cover": [],
                "key_numbers": [],
                "real_comparisons": [],
                "section_plan": [],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert issues == ["planning_section_plan_empty"]


def test_inspect_note_plan_accepts_valid_plan(tmp_path) -> None:
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "paper_type": "AI_method",
                "dominant_domain": "reasoning",
                "must_cover": ["方法主线"],
                "key_numbers": ["42"],
                "real_comparisons": ["baseline"],
                "section_plan": [{"section": "方法主线"}],
            }
        ),
        encoding="utf-8",
    )

    found, issues = inspect_note_plan(plan_path)
    assert found is True
    assert issues == []
