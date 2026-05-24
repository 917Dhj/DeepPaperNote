#!/usr/bin/env python3
"""Check whether a drafted note meets structure and quality expectations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from contracts import (
    NOTE_PLAN_LIST_FIELDS,
    NOTE_PLAN_REQUIRED_FIELDS,
    NOTE_PLAN_STRING_FIELDS,
    NOTE_REQUIRED_SECTIONS,
    PAPER_TYPE_VALUES,
)

REQUIRED_SECTIONS = NOTE_REQUIRED_SECTIONS

CORE_INFO_FIELDS = [
    "标题",
    "标题翻译",
    "作者",
    "机构",
    "发表时间",
    "发表渠道",
    "DOI",
    "arXiv",
    "论文链接",
    "代码 / 项目",
    "数据 / 资源",
    "论文类型",
]

CORE_INFO_FIELD_INDEX = {field: idx for idx, field in enumerate(CORE_INFO_FIELDS)}

FIGURE_TARGET_SECTIONS = {
    "研究问题",
    "数据与任务定义",
    "方法主线",
    "关键结果",
    "深度分析",
    "局限",
    "我的笔记",
}

FIGURE_BUCKET_RESIDUE_TOKENS = {
    "剩余",
    "残余",
    "未放置",
    "未处理",
    "待补",
}

FIGURE_BUCKET_VISUAL_TOKENS = {
    "图",
    "表",
    "图片",
    "图表",
    "占位",
}

ENGLISH_FIGURE_BUCKET_RESIDUE_TOKENS = {
    "remaining",
    "leftover",
    "unplaced",
    "unresolved",
    "backlog",
}

ENGLISH_FIGURE_BUCKET_VISUAL_TOKENS = {
    "figure",
    "figures",
    "fig",
    "figs",
    "table",
    "tables",
    "placeholder",
    "placeholders",
}

NONSTANDARD_FIGURE_PLACEHOLDER_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        \[\s*(?:图表|图片|图|表)\s*占位\s*\|[^\]]+\]
        |
        (?:图表|图片|图|表)\s*占位\s*[:：]\s*\S+
        |
        \[\s*(?:figure|fig|table)\s+placeholder\s*(?:\||:|\]|-|\s+(?:fig(?:ure)?|table)\.?\s*\d)
        |
        (?:figure|fig|table)\s+placeholder\s*(?:\||:|-|\s+(?:fig(?:ure)?|table)\.?\s*\d)
    )
    """
)

REAL_IMAGE_STATUS_RE = re.compile(
    r"""
    (?:
        已\s*(?:替换|插入|复制|拷贝|物化|写入)
        |
        (?:替换|插入)\s*为\s*真实图片
        |
        \b(?:inserted|replaced|copied|materialized)\b
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

USABLE_CANDIDATE_STATUS_RE = re.compile(
    r"""
    (?:
        候选[^。；，\n>]{0,24}(?<!不)(?:可用|可读|清晰)
        |
        (?<!不)可用[^。；，\n>]{0,12}候选
        |
        (?:图像|图片|表格|图|表)?\s*裁剪[^。；，\n>]{0,12}(?<!不)(?:可用|可读|清晰)
        |
        (?:图像|图片|表格|图|表)[^。；，\n>]{0,12}(?<!不)(?:可用|可读|清晰)
        |
        图号\s*匹配
        |
        匹配度\s*高
        |
        高\s*置信(?:度)?[^。；，\n>]{0,12}候选
        |
        usable\s+candidate
        |
        readable\s+crop
        |
        clear\s+crop
        |
        high[-\s]*(?:confidence|match)
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

USABLE_CANDIDATE_VISUAL_DEFECT_RE = re.compile(
    r"""
    (?:
        混入|污染|相邻|裁切|截断|切断|缺失|缺少|表体不完整|表格主体缺失|正文污染
        |
        只拿到|局部(?:子图|面板|截图|区域)|部分(?:子图|裁剪)
        |
        无法稳定|不可独立解释|质量门|reject_visual_quality
        |
        partial|subpanel|contaminat|truncat|incomplete|missing
        |
        caption\s*(?:missing|cut|truncated)
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

USABLE_CANDIDATE_MATERIALIZATION_BLOCKED_RE = re.compile(
    r"""
    (?:
        (?:materialize_figure_asset\.py|物化|复制|拷贝|写入|权限|permission|工具|copy)
        [^。；\n]{0,40}
        (?:失败|不足|拒绝|denied|blocked|error|报错)
        |
        (?:失败|不足|拒绝|denied|blocked|error|报错)
        [^。；\n]{0,40}
        (?:materialize|物化|复制|拷贝|写入|权限|permission|copy)
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

MISSING_ASSET_MATERIALIZATION_RE = re.compile(
    r"""
    (?:
        (?:资产缺失|未找到|没有|缺少|asset_candidate_missing|candidate\s+missing)
        [^。；\n]{0,50}
        (?:materialize_figure_asset\.py|物化|复制|拷贝|写入|权限|permission|copy|blocked)
        |
        (?:materialize_figure_asset\.py|物化|复制|拷贝|写入|权限|permission|copy|blocked)
        [^。；\n]{0,50}
        (?:资产缺失|未找到|没有|缺少|asset_candidate_missing|candidate\s+missing)
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)

MARKDOWN_IMAGE_EMBED_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$")
FIGURE_CALLOUT_TITLE_RE = re.compile(r"^>\s*\[!figure\][+-]?\s*(.*)$")

MECHANICAL_TRANSLATION_ARTIFACT_RE = re.compile(
    r"""
    (?:
        [\u4e00-\u9fff]+(?:ing|ed|s)\b
        |
        \b[A-Za-z]{2,}相关\b
        |
        [\u4e00-\u9fff](?:缓存|块)?\s+(?:of|with|for|on|in|from|and)\b
        |
        \b(?:of|with|for|on|in|from|and)\s+[\u4e00-\u9fff]
        |
        [\u4e00-\u9fff]\s+(?:table|translation|example|candidate|caption|slot|query|block|token|input|layout|serving|memory|management|overhead|latency|dependent|preemption)\b
        |
        \b(?:block|caption|slot|query|input|layout|serving|memory|management|overhead|latency|dependent|preemption)\s+[\u4e00-\u9fff]
        |
        \b(?:Single|Shared|Performance|Storing|Illustration)\b[^\n。；]{0,60}[\u4e00-\u9fff]
    )
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "lint note")
    p.add_argument("--input", required=True, help="Markdown note path.")
    p.add_argument("--plan-file", default="", help="Optional note_plan JSON path. Defaults to sibling <note>.plan.json.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    return p


def resolve_note_plan_path(note_path: Path, plan_file: str) -> Path:
    if plan_file:
        return Path(plan_file).expanduser().resolve()
    return note_path.with_suffix(".plan.json")


def inspect_note_plan(plan_path: Path) -> tuple[bool, list[str]]:
    if not plan_path.exists():
        return False, ["planning_artifact_missing"]

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True, ["planning_artifact_invalid_json"]

    if not isinstance(plan, dict):
        return True, ["planning_required_fields_invalid"]

    issues: list[str] = []
    missing_fields = [field for field in NOTE_PLAN_REQUIRED_FIELDS if field not in plan]
    if missing_fields:
        issues.append("planning_required_fields_missing")

    has_invalid_fields = False
    for field in NOTE_PLAN_STRING_FIELDS:
        if field in plan and not isinstance(plan[field], str):
            has_invalid_fields = True
        elif field in plan and not plan[field].strip():
            issues.append(f"planning_{field}_empty")
    if isinstance(plan.get("paper_type"), str) and plan["paper_type"].strip():
        if plan["paper_type"].strip() not in PAPER_TYPE_VALUES:
            issues.append("planning_paper_type_invalid")
    for field in NOTE_PLAN_LIST_FIELDS:
        if field in plan and not isinstance(plan[field], list):
            has_invalid_fields = True
        elif field in plan and not plan[field]:
            issues.append(f"planning_{field}_empty")
    if has_invalid_fields:
        issues.append("planning_required_fields_invalid")
    issues.extend(inspect_central_claims_plan(plan.get("central_claims")))

    return True, issues


def inspect_central_claims_plan(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return ["planning_central_claims_invalid"]

    issues: list[str] = []
    required_fields = (
        "claim",
        "supporting_evidence",
        "what_it_actually_proves",
        "what_it_does_not_prove",
    )
    for item in value:
        if not isinstance(item, dict):
            if "planning_central_claims_invalid" not in issues:
                issues.append("planning_central_claims_invalid")
            continue
        for field in required_fields:
            field_value = item.get(field)
            if field == "supporting_evidence":
                if not isinstance(field_value, list) or not field_value:
                    code = "planning_central_claims_supporting_evidence_missing"
                    if code not in issues:
                        issues.append(code)
                continue
            if not isinstance(field_value, str) or not field_value.strip():
                code = f"planning_central_claims_{field}_missing"
                if code not in issues:
                    issues.append(code)
    return issues


def extract_headers(text: str) -> list[str]:
    return [match.group(2).strip() for match in re.finditer(r"^(#{1,3})\s+(.+)$", text, flags=re.MULTILINE)]


def find_missing_sections(text: str) -> list[str]:
    missing = []
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            missing.append(section)
    return missing


def front_matter_order_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    required_order = ["## 原文摘要翻译", "## 创新点", "## 一句话总结"]
    positions = []
    for section in required_order:
        idx = text.find(section)
        if idx < 0:
            return warnings
        positions.append(idx)
    if positions != sorted(positions):
        warnings.append("front_matter_order_invalid")
    return warnings


METHOD_PAPER_SIGNAL_KEYWORDS = [
    "模型",
    "框架",
    "系统",
    "模块",
    "编码器",
    "解码器",
    "预融合",
    "attention",
    "encoder",
    "decoder",
    "pipeline",
    "framework",
]

MECHANISM_IO_TOKENS = [
    "输入",
    "输出",
    "送入",
    "送到",
    "生成",
    "得到",
]

MECHANISM_ACTION_TOKENS = [
    "融合",
    "投影",
    "压缩",
    "对齐",
    "池化",
    "提取",
    "编码",
    "解码",
    "拼接",
    "查询",
    "更新",
]


ENGLISH_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "to",
    "we",
    "when",
    "which",
    "with",
}

PLACEHOLDER_ONLY_PATTERNS = [
    r"^待补充[。.!！]*$",
    r"^todo[。.!！]*$",
    r"^暂无[。.!！]*$",
    r"^略[。.!！]*$",
    r"^参见原论文[。.!！]*$",
    r"^这里记录.*[。.!！]*$",
    r"^本节记录.*[。.!！]*$",
]

GENERIC_INNOVATION_PATTERNS = [
    r"本文提出(?:了)?一种新方法",
    r"具有创新性",
    r"novel approach",
    r"首次实现",
]

GENERIC_KEY_RESULT_PATTERNS = [
    r"实验结果表明方法有效",
    r"结果表明.*有效",
    r"取得(?:了)?较好效果",
    r"性能.*优越",
]

GENERIC_LIMITATION_PATTERNS = [
    r"未来工作.*更多数据",
    r"需要更多数据",
    r"future work can",
    r"more data",
    r"后续.*扩展",
]

HONEST_MISSING_TOKENS = ("本文未给出", "论文未给出", "未报告", "没有报告", "未提供")
HONEST_MISSING_BASIS_TOKENS = ("依据", "正文", "附录", "表格", "coverage", "作者")
HONEST_MISSING_IMPACT_TOKENS = ("影响", "限制", "受限", "不能", "无法", "结论强度")

DOUBLE_ESCAPED_TEX_COMMANDS = {
    "alpha",
    "bar",
    "begin",
    "beta",
    "end",
    "exp",
    "frac",
    "gamma",
    "ge",
    "hat",
    "left",
    "le",
    "log",
    "mathcal",
    "mathrm",
    "prod",
    "right",
    "sum",
    "tau",
    "tilde",
}


def is_metadata_line(line: str) -> bool:
    stripped = line.strip()
    prefixes = [f"- {field}:" for field in CORE_INFO_FIELDS]
    return any(stripped.startswith(prefix) for prefix in prefixes)


def is_exempt_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if is_metadata_line(stripped):
        return True
    if (
        stripped.startswith("> [!figure]")
        or stripped.startswith("> 建议位置：")
        or stripped.startswith("> 放置原因：")
        or stripped.startswith("> 当前状态：")
    ):
        return True
    if re.search(r"https?://", stripped):
        return True
    if re.search(r"`10\.\d{4,9}/", stripped):
        return True
    return False


def section_name_for_line(lines: list[str], line_index: int) -> str:
    current_section = ""
    for idx in range(0, line_index + 1):
        stripped = lines[idx].strip()
        match = re.match(r"^##\s+(.+)$", stripped)
        if match:
            current_section = match.group(1).strip()
    return current_section


def subsection_name_for_line(lines: list[str], line_index: int) -> str:
    current_subsection = ""
    for idx in range(0, line_index + 1):
        stripped = lines[idx].strip()
        if re.match(r"^##\s+.+$", stripped):
            current_subsection = ""
            continue
        match = re.match(r"^###\s+(.+)$", stripped)
        if match:
            current_subsection = match.group(1).strip()
    return current_subsection


def mixed_language_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        if is_exempt_line(line):
            continue
        stripped = line.strip()
        section_name = section_name_for_line(lines, idx - 1)
        subsection_name = subsection_name_for_line(lines, idx - 1)
        if section_name in {"核心信息", "引用"}:
            continue
        if not re.search(r"[\u4e00-\u9fff]", stripped):
            continue
        english_words = re.findall(r"\b[A-Za-z][A-Za-z0-9.-]*\b", stripped)
        if len(english_words) < 4:
            continue
        function_hits = [word for word in english_words if word.lower() in ENGLISH_FUNCTION_WORDS]
        if not function_hits and len(english_words) < 7:
            continue
        issues.append(
            {
                "line_number": idx,
                "line": stripped,
                "english_word_count": len(english_words),
                "function_word_hits": function_hits[:6],
            }
        )
    return issues


def mechanical_translation_artifact_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"---"} or re.search(r"https?://", stripped):
            continue
        match = MECHANICAL_TRANSLATION_ARTIFACT_RE.search(stripped)
        if not match:
            continue
        issues.append(
            {
                "line_number": idx,
                "line": stripped,
                "artifact": match.group(0),
            }
        )
    return issues


def inspect_figure_callouts(text: str) -> list[str]:
    warnings: list[str] = []
    lines = text.splitlines()
    i = 0
    saw_legacy_block = False
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("[FIGURE_PLACEHOLDER]"):
            saw_legacy_block = True
        if not stripped.startswith("> [!figure]"):
            i += 1
            continue
        if not figure_callout_title(stripped):
            warnings.append("figure_callout_missing_title")
        has_location = False
        has_reason = False
        has_status = False
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt.startswith(">"):
                break
            if nxt.startswith("> 建议位置："):
                has_location = True
            if nxt.startswith("> 放置原因："):
                has_reason = True
            if nxt.startswith("> 当前状态："):
                has_status = True
            j += 1
        if not has_location:
            warnings.append("figure_callout_missing_location")
        if not has_reason:
            warnings.append("figure_callout_missing_reason")
        if not has_status:
            warnings.append("figure_callout_missing_status")
        i = j
    if saw_legacy_block:
        warnings.append("legacy_figure_placeholder_block_used")
    return warnings


def figure_callout_title(line: str) -> str:
    match = FIGURE_CALLOUT_TITLE_RE.match(line.strip())
    if not match:
        return ""
    return match.group(1).strip()


def figure_status_text(line: str) -> str:
    stripped = line.strip()
    if not stripped.startswith("> 当前状态："):
        return ""
    return stripped.removeprefix("> 当前状态：").strip()


def has_accepted_usable_placeholder_reason(status_text: str) -> bool:
    return bool(
        USABLE_CANDIDATE_VISUAL_DEFECT_RE.search(status_text)
        or USABLE_CANDIDATE_MATERIALIZATION_BLOCKED_RE.search(status_text)
    )


def usable_candidate_decision_is_unresolved(status_text: str) -> bool:
    return bool(
        USABLE_CANDIDATE_STATUS_RE.search(status_text)
        and not has_accepted_usable_placeholder_reason(status_text)
    )


def is_figure_bucket_heading(title: str) -> bool:
    normalized = title.strip().lower()
    has_chinese_residue = any(token in normalized for token in FIGURE_BUCKET_RESIDUE_TOKENS)
    has_chinese_visual = any(token in normalized for token in FIGURE_BUCKET_VISUAL_TOKENS)
    if has_chinese_residue and has_chinese_visual:
        return True
    has_english_residue = any(token in normalized for token in ENGLISH_FIGURE_BUCKET_RESIDUE_TOKENS)
    has_english_visual = any(token in normalized for token in ENGLISH_FIGURE_BUCKET_VISUAL_TOKENS)
    return has_english_residue and has_english_visual


def figure_bucket_heading_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{2,3})\s+(.+)$", line.strip())
        if not match:
            continue
        heading = match.group(2).strip()
        if is_figure_bucket_heading(heading):
            issues.append(
                {
                    "line_number": idx,
                    "heading": heading,
                    "reason": "figure_placeholder_bucket_heading",
                }
            )
    return issues


def nonstandard_figure_placeholder_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        if NONSTANDARD_FIGURE_PLACEHOLDER_RE.match(stripped):
            issues.append(
                {
                    "line_number": idx,
                    "line": stripped,
                    "reason": "nonstandard_figure_placeholder_format",
                }
            )
    return issues


def figure_callout_placement_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[FIGURE_PLACEHOLDER]"):
            issues.append(
                {
                    "line_number": idx + 1,
                    "line": stripped,
                    "reason": "legacy_figure_placeholder_block_used",
                }
            )
            continue
        if not stripped.startswith("> [!figure]"):
            continue

        title = figure_callout_title(stripped)
        if not title:
            issues.append(
                {
                    "line_number": idx + 1,
                    "callout": stripped,
                    "reason": "figure_callout_missing_title",
                }
            )

        current_section = section_name_for_line(lines, idx)
        current_subsection = subsection_name_for_line(lines, idx)
        location = ""
        j = idx + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt.startswith(">"):
                break
            if nxt.startswith("> 建议位置："):
                location = nxt.removeprefix("> 建议位置：").strip()
                break
            j += 1

        if not location:
            issues.append(
                {
                    "line_number": idx + 1,
                    "callout": stripped,
                    "current_section": current_section,
                    "current_subsection": current_subsection,
                    "reason": "figure_callout_missing_location",
                }
            )
            continue

        if current_subsection and current_subsection in location:
            continue
        target_sections = [section for section in FIGURE_TARGET_SECTIONS if section in location]
        if target_sections and current_section not in target_sections:
            issues.append(
                {
                    "line_number": idx + 1,
                    "callout": stripped,
                    "current_section": current_section,
                    "current_subsection": current_subsection,
                    "declared_location": location,
                    "target_sections": target_sections,
                    "reason": "figure_callout_placement_mismatch",
                }
            )
    return issues


def figure_callout_real_image_status_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("> [!figure]"):
            continue
        j = idx + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt.startswith(">"):
                break
            status_text = figure_status_text(nxt)
            if status_text and REAL_IMAGE_STATUS_RE.search(nxt):
                issues.append(
                    {
                        "line_number": j + 1,
                        "line": nxt,
                        "reason": "inserted_figure_redundant_callout",
                    }
                )
                break
            j += 1
    return issues


def figure_callout_usable_candidate_status_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("> [!figure]"):
            continue
        j = idx + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt.startswith(">"):
                break
            status_text = figure_status_text(nxt)
            if status_text and usable_candidate_decision_is_unresolved(status_text):
                issues.append(
                    {
                        "line_number": j + 1,
                        "line": nxt,
                        "reason": "usable_candidate_unresolved_decision",
                    }
                )
                break
            j += 1
    return issues


def figure_callout_missing_asset_materialization_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("> [!figure]"):
            continue
        j = idx + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt.startswith(">"):
                break
            status_text = figure_status_text(nxt)
            if status_text and MISSING_ASSET_MATERIALIZATION_RE.search(status_text):
                issues.append(
                    {
                        "line_number": j + 1,
                        "line": nxt,
                        "reason": "missing_asset_misreported_as_materialization_blocked",
                    }
                )
                break
            j += 1
    return issues


def is_image_embed_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("![[") or bool(MARKDOWN_IMAGE_EMBED_RE.match(stripped))


def has_figure_marker(text: str) -> bool:
    return (
        "[!figure]" in text
        or "[FIGURE_PLACEHOLDER]" in text
        or any(is_image_embed_line(line) for line in text.splitlines())
    )


def is_italic_caption_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
        return True
    return stripped.startswith("_") and stripped.endswith("_") and not stripped.startswith("__")


def image_embed_caption_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not is_image_embed_line(stripped):
            continue
        if idx + 1 < len(lines) and is_italic_caption_line(lines[idx + 1]):
            continue
        issues.append(
            {
                "line_number": idx + 1,
                "line": stripped,
                "reason": "inserted_figure_missing_caption",
            }
        )
    return issues


def figure_structure_issues(text: str) -> list[dict[str, object]]:
    return (
        figure_bucket_heading_issues(text)
        + nonstandard_figure_placeholder_issues(text)
        + figure_callout_placement_issues(text)
        + figure_callout_real_image_status_issues(text)
        + figure_callout_usable_candidate_status_issues(text)
        + figure_callout_missing_asset_materialization_issues(text)
        + image_embed_caption_issues(text)
    )


def figure_structure_passes(text: str) -> bool:
    return not figure_structure_issues(text)


def core_info_structure_issues(text: str) -> list[dict[str, object]]:
    body = section_body(text, "核心信息")
    if not body:
        return []

    issues: list[dict[str, object]] = []
    seen_fields: set[str] = set()
    last_known_index = -1
    base_line = _line_number_from_offset(text, text.find("## 核心信息"))

    for offset, raw_line in enumerate(body.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        line_number = base_line + offset
        match = re.match(r"^-\s*([^:：]+)\s*[:：]\s*(.*)$", stripped)
        if not match:
            issues.append(
                {
                    "line_number": line_number,
                    "line": stripped,
                    "reason": "core_info_non_metadata_line",
                }
            )
            continue

        field = match.group(1).strip()
        if field not in CORE_INFO_FIELD_INDEX:
            issues.append(
                {
                    "line_number": line_number,
                    "line": stripped,
                    "reason": "core_info_unknown_field",
                    "field": field,
                }
            )
            continue

        if field in seen_fields:
            issues.append(
                {
                    "line_number": line_number,
                    "line": stripped,
                    "reason": "core_info_duplicate_field",
                    "field": field,
                }
            )
            continue

        field_index = CORE_INFO_FIELD_INDEX[field]
        if field_index < last_known_index:
            issues.append(
                {
                    "line_number": line_number,
                    "line": stripped,
                    "reason": "core_info_field_order_invalid",
                    "field": field,
                }
            )
        seen_fields.add(field)
        last_known_index = max(last_known_index, field_index)

    return issues


def is_prose_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "-", "*", "> ", "```", "![[", "*论文原图编号")):
        return False
    if stripped.startswith("`") and stripped.endswith("`"):
        return False
    return True


def suspicious_mid_sentence_linebreaks(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    for idx in range(len(lines) - 1):
        current = lines[idx].rstrip()
        nxt = lines[idx + 1].lstrip()
        if not is_prose_line(current) or not is_prose_line(nxt):
            continue
        if is_metadata_line(current) or is_metadata_line(nxt):
            continue
        if re.search(r"[。！？.!?：:]$", current):
            continue
        if not re.search(r"[，,；;、）)\]」』]$", current):
            if not re.search(r"[A-Za-z0-9`\u4e00-\u9fff]$", current):
                continue
        if not re.match(r"^[A-Za-z0-9`\u4e00-\u9fff(（“‘\"]", nxt):
            continue
        issues.append(
            {
                "line_number": idx + 1,
                "line": current.strip(),
                "next_line": nxt.strip(),
            }
        )
    return issues


def suspicious_code_formatted_math(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    in_fence = False
    fence_start = 0
    fence_lines: list[str] = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_start = idx
                fence_lines = []
            else:
                fence_text = "\n".join(fence_lines)
                if re.search(r"(?:^|\\n)\s*(?:[A-Za-z][A-Za-z0-9_]*\s*=|O\(|\\sum|\\prod|\\mathcal|\\log|\\frac)", fence_text):
                    issues.append(
                        {
                            "line_number": fence_start,
                            "line": "```",
                            "next_line": fence_lines[0].strip() if fence_lines else "",
                            "kind": "fenced_math_like_block",
                        }
                    )
                in_fence = False
                fence_start = 0
                fence_lines = []
            continue
        if in_fence:
            fence_lines.append(line)
            continue
        for match in re.finditer(r"`([^`\n]{3,120})`", line):
            content = match.group(1).strip()
            if re.search(r"(=|O\(|\\sum|\\prod|\\mathcal|\\log|\\frac)", content):
                issues.append(
                    {
                        "line_number": idx,
                        "line": line.strip(),
                        "next_line": content,
                        "kind": "inline_code_math_like",
                    }
                )
                break
    return issues


def _line_number_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _formula_snippet(content: str, limit: int = 120) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _strip_fenced_code_preserve_newlines(text: str) -> str:
    return re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)


def _extract_math_blocks(text: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    sanitized = _strip_fenced_code_preserve_newlines(text)
    blocks: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    consumed_lines: set[int] = set()

    block_pattern = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", flags=re.DOTALL)
    for match in block_pattern.finditer(sanitized):
        start = match.start()
        line_number = _line_number_from_offset(sanitized, start)
        content = match.group(1).strip()
        blocks.append(
            {
                "kind": "block",
                "line_number": line_number,
                "content": content,
                "snippet": _formula_snippet(content),
            }
        )
        line_span = match.group(0).count("\n")
        for extra in range(line_span + 1):
            consumed_lines.add(line_number + extra)

    delimiter_positions = [m.start() for m in re.finditer(r"(?<!\\)\$\$", sanitized)]
    if len(delimiter_positions) % 2 == 1:
        offset = delimiter_positions[-1]
        issues.append(
            {
                "line_number": _line_number_from_offset(sanitized, offset),
                "snippet": "$$",
                "reason": "unclosed_math_delimiter",
            }
        )

    inline_pattern = re.compile(r"(?<!\\)(?<!\$)\$(?!\$)(.+?)(?<!\\)\$(?!\$)")
    for idx, line in enumerate(sanitized.splitlines(), start=1):
        if idx in consumed_lines:
            continue
        for match in inline_pattern.finditer(line):
            content = match.group(1).strip()
            if not content:
                continue
            blocks.append(
                {
                    "kind": "inline",
                    "line_number": idx,
                    "content": content,
                    "snippet": _formula_snippet(content),
                }
            )
        if len(re.findall(r"(?<!\\)(?<!\$)\$(?!\$)", line)) % 2 == 1:
            issues.append(
                {
                    "line_number": idx,
                    "snippet": line.strip(),
                    "reason": "unclosed_math_delimiter",
                }
            )
    return blocks, issues


def _find_unbalanced_braces(expr: str) -> bool:
    depth = 0
    for char in expr:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _parse_group_argument(expr: str, start: int) -> int | None:
    idx = start
    while idx < len(expr) and expr[idx].isspace():
        idx += 1
    if idx >= len(expr) or expr[idx] != "{":
        return None
    depth = 0
    while idx < len(expr):
        if expr[idx] == "{":
            depth += 1
        elif expr[idx] == "}":
            depth -= 1
            if depth == 0:
                return idx + 1
        idx += 1
    return None


def _has_invalid_frac_arguments(expr: str) -> bool:
    for match in re.finditer(r"(?<!\\)\\frac\b", expr):
        next_index = _parse_group_argument(expr, match.end())
        if next_index is None:
            return True
        final_index = _parse_group_argument(expr, next_index)
        if final_index is None:
            return True
    return False


def _has_environment_mismatch(expr: str) -> bool:
    stack: list[str] = []
    pattern = re.compile(r"(?<!\\)\\(begin|end)\{([A-Za-z*]+)\}")
    for kind, env in pattern.findall(expr):
        if kind == "begin":
            stack.append(env)
            continue
        if not stack or stack[-1] != env:
            return True
        stack.pop()
    return bool(stack)


def _has_left_right_mismatch(expr: str) -> bool:
    return len(re.findall(r"(?<!\\)\\left\b", expr)) != len(re.findall(r"(?<!\\)\\right\b", expr))


def _has_double_escaped_tex_command(expr: str) -> bool:
    pattern = r"(?<!\\)\\\\(" + "|".join(sorted(DOUBLE_ESCAPED_TEX_COMMANDS)) + r")\b"
    return bool(re.search(pattern, expr))


def math_render_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    blocks, delimiter_issues = _extract_math_blocks(text)
    issues.extend(delimiter_issues)

    for block in blocks:
        content = str(block["content"])
        line_number = int(block["line_number"])
        snippet = str(block["snippet"])

        if _has_double_escaped_tex_command(content):
            issues.append(
                {
                    "line_number": line_number,
                    "snippet": snippet,
                    "reason": "double_escaped_tex_command",
                }
            )
        if _find_unbalanced_braces(content):
            issues.append(
                {
                    "line_number": line_number,
                    "snippet": snippet,
                    "reason": "unbalanced_braces",
                }
            )
        if _has_environment_mismatch(content):
            issues.append(
                {
                    "line_number": line_number,
                    "snippet": snippet,
                    "reason": "environment_mismatch",
                }
            )
        if _has_left_right_mismatch(content):
            issues.append(
                {
                    "line_number": line_number,
                    "snippet": snippet,
                    "reason": "left_right_mismatch",
                }
            )
        if _has_invalid_frac_arguments(content):
            issues.append(
                {
                    "line_number": line_number,
                    "snippet": snippet,
                    "reason": "invalid_frac_arguments",
                }
            )

    deduped: list[dict[str, object]] = []
    seen: set[tuple[int, str, str]] = set()
    for issue in issues:
        key = (int(issue["line_number"]), str(issue["snippet"]), str(issue["reason"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def section_body(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+.+$", text[start:], flags=re.MULTILINE)
    if not next_match:
        return text[start:]
    return text[start : start + next_match.start()]


def subsection_body(text: str, section_heading: str, subsection_heading: str) -> str:
    body = section_body(text, section_heading)
    if not body:
        return ""
    pattern = rf"^###\s+{re.escape(subsection_heading)}\s*$"
    match = re.search(pattern, body, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^(?:##|###)\s+.+$", body[start:], flags=re.MULTILINE)
    if not next_match:
        return body[start:]
    return body[start : start + next_match.start()]


def cleaned_section_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if (
            stripped.startswith("> [!figure]")
            or stripped.startswith("> 建议位置：")
            or stripped.startswith("> 放置原因：")
            or stripped.startswith("> 当前状态：")
        ):
            continue
        if stripped.startswith("!["):
            continue
        if stripped.startswith("*论文原图编号：") and stripped.endswith("*"):
            continue
        if stripped.startswith("> "):
            stripped = stripped[2:].strip()
        lines.append(stripped)
    return lines


def normalized_section_content(body: str) -> str:
    return normalize_lint_whitespace(" ".join(cleaned_section_lines(body)))


def normalize_lint_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def matches_any_pattern(text: str, patterns: list[str]) -> bool:
    normalized = normalize_lint_whitespace(text)
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)


def is_placeholder_like(text: str) -> bool:
    normalized = normalize_lint_whitespace(text)
    if not normalized:
        return True
    return matches_any_pattern(normalized, PLACEHOLDER_ONLY_PATTERNS)


def issue(section: str, reason: str, severity: str, snippet: str) -> dict[str, object]:
    return {
        "section": section,
        "reason": reason,
        "severity": severity,
        "snippet": normalize_lint_whitespace(snippet)[:160],
    }


def text_units(body: str) -> list[str]:
    units: list[str] = []
    for line in cleaned_section_lines(body):
        stripped = re.sub(r"^(?:[-*+]|\d+[.)、])\s*", "", line).strip()
        if stripped:
            units.append(stripped)
    if units:
        return units
    return [
        part.strip()
        for part in re.split(r"[。！？!?]\s*", normalized_section_content(body))
        if part.strip()
    ]


def meaningful_units(body: str, generic_patterns: list[str] | None = None) -> list[str]:
    generic_patterns = generic_patterns or []
    kept: list[str] = []
    for unit in text_units(body):
        if is_placeholder_like(unit):
            continue
        if generic_patterns and matches_any_pattern(unit, generic_patterns):
            continue
        compact = re.sub(r"[\s，。,.；;：:、\-*+()（）【】\[\]]+", "", unit)
        if len(compact) < 12:
            continue
        kept.append(unit)
    return kept


def has_number_token(text: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|％|[A-Za-z\u4e00-\u9fff]{0,8})", text))


def is_honest_missing_declaration(text: str) -> bool:
    normalized = normalize_lint_whitespace(text)
    if not any(token in normalized for token in HONEST_MISSING_TOKENS):
        return False
    if not any(token in normalized for token in HONEST_MISSING_BASIS_TOKENS):
        return False
    if not any(token in normalized for token in HONEST_MISSING_IMPACT_TOKENS):
        return False
    return len(normalized) >= 30


def has_reference_entry(text: str) -> bool:
    normalized = normalize_lint_whitespace(text)
    if re.search(r"10\.\d{4,9}/\S+", normalized):
        return True
    if re.search(r"\barXiv[:：]?\s*\d{4}\.\d{4,5}", normalized, flags=re.IGNORECASE):
        return True
    if re.search(r"\[\[[^\]]+\]\]", normalized):
        return True
    if re.search(r"\[[0-9]+\]", normalized):
        return True
    if re.search(r"\b[A-Z][A-Za-z-]+ et al\.?\s*,?\s*(?:19|20)\d{2}\b", normalized):
        return True
    if re.search(r"(?:19|20)\d{2}.*(?:DOI|doi|会议|期刊|arXiv)", normalized):
        return True
    return False


def inspect_substantive_content(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for section in REQUIRED_SECTIONS:
        body = section_body(text, section)
        content = normalized_section_content(body)
        if is_placeholder_like(content):
            issues.append(issue(section, "section_empty_shell", "error", content or section))
        if section not in {"关键结果", "引用"} and is_honest_missing_declaration(content):
            issues.append(issue(section, "section_honest_missing_not_allowed", "error", content))

    innovation = section_body(text, "创新点")
    innovation_content = normalized_section_content(innovation)
    innovation_units = meaningful_units(innovation, GENERIC_INNOVATION_PATTERNS)
    if not innovation_units:
        issues.append(issue("创新点", "innovation_empty_shell", "error", innovation_content))
    elif len(innovation_units) < 2:
        issues.append(issue("创新点", "innovation_too_few_specific_points", "warning", innovation_content))

    key_results = section_body(text, "关键结果")
    key_results_content = normalized_section_content(key_results)
    if is_honest_missing_declaration(key_results_content):
        issues.append(
            issue(
                "关键结果",
                "key_results_honest_missing_not_allowed",
                "error",
                key_results_content,
            )
        )
    elif not meaningful_units(key_results, GENERIC_KEY_RESULT_PATTERNS):
        issues.append(issue("关键结果", "key_results_empty_shell", "error", key_results_content))
    elif not has_number_token(key_results_content):
        issues.append(
            issue(
                "关键结果",
                "key_results_quantitative_result_missing",
                "warning",
                key_results_content,
            )
        )

    references = section_body(text, "引用")
    references_content = normalized_section_content(references)
    if is_honest_missing_declaration(references_content):
        issues.append(issue("引用", "references_unavailable_declared", "warning", references_content))
    elif is_placeholder_like(references_content) or not has_reference_entry(references_content):
        issues.append(issue("引用", "references_placeholder", "error", references_content))

    limitations = section_body(text, "局限")
    limitations_content = normalized_section_content(limitations)
    if not meaningful_units(limitations, GENERIC_LIMITATION_PATTERNS):
        issues.append(issue("局限", "limitations_empty_shell", "error", limitations_content))

    for section in ("方法主线", "深度分析"):
        body = section_body(text, section)
        content = normalized_section_content(body)
        if not meaningful_units(body):
            issues.append(issue(section, "section_empty_shell", "error", content or section))

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in issues:
        key = (str(item["section"]), str(item["reason"]), str(item["severity"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def method_section_requires_mechanism_flow(text: str) -> bool:
    body = section_body(text, "方法主线")
    if not body:
        return False
    lower = body.lower()
    keyword_hits = sum(1 for token in METHOD_PAPER_SIGNAL_KEYWORDS if token.lower() in lower)
    has_formula = "$$" in body or bool(re.search(r"\$[^$\n]{4,}\$", body))
    return has_formula or keyword_hits >= 2


def mechanism_flow_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    if not method_section_requires_mechanism_flow(text):
        return warnings
    if "### 机制流程" not in text:
        warnings.append("mechanism_flow_subsection_missing")
        return warnings

    body = subsection_body(text, "方法主线", "机制流程")
    if not body:
        warnings.append("mechanism_flow_subsection_empty")
        return warnings

    step_lines = [line.strip() for line in body.splitlines() if re.match(r"^\d+\.\s+", line.strip())]
    if not 3 <= len(step_lines) <= 4:
        warnings.append("mechanism_flow_step_count_unexpected")

    step_text = " ".join(step_lines)
    has_io_signal = any(token in step_text for token in MECHANISM_IO_TOKENS)
    has_action_signal = any(token in step_text for token in MECHANISM_ACTION_TOKENS)
    if not (has_io_signal and has_action_signal):
        warnings.append("mechanism_flow_too_abstract")

    return warnings


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (---...---) if present."""
    return re.sub(r"^---\n.*?\n---\n?", "", text, count=1, flags=re.DOTALL)


def main() -> None:
    from common import emit

    args = parser().parse_args()
    path = Path(args.input).expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    body_text = strip_frontmatter(text)
    headers = extract_headers(text)
    missing_sections = find_missing_sections(text)
    warnings: list[str] = []
    mixed_issues = mixed_language_issues(text)
    mechanical_artifact_issues = mechanical_translation_artifact_issues(text)
    linebreak_issues = suspicious_mid_sentence_linebreaks(body_text)
    code_math_issues = suspicious_code_formatted_math(text)
    math_issues = math_render_issues(text)
    figure_issues = figure_structure_issues(text)
    core_info_issues = core_info_structure_issues(text)
    substantive_issues = inspect_substantive_content(text)
    planning_artifact_found, planning_artifact_issues = inspect_note_plan(
        resolve_note_plan_path(path, args.plan_file)
    )
    warnings.extend(inspect_figure_callouts(text))
    for issue in figure_issues:
        reason = str(issue.get("reason", ""))
        if reason and reason not in warnings:
            warnings.append(reason)
    for issue in core_info_issues:
        reason = str(issue.get("reason", ""))
        if reason and reason not in warnings:
            warnings.append(reason)
    for issue in planning_artifact_issues:
        if issue not in warnings:
            warnings.append(issue)
    for issue in substantive_issues:
        reason = str(issue.get("reason", ""))
        if reason and reason not in warnings:
            warnings.append(reason)
    warnings.extend(front_matter_order_warnings(text))
    warnings.extend(mechanism_flow_warnings(text))
    if not body_text.lstrip().startswith("# "):
        warnings.append("title_heading_missing")
    if "## " not in text:
        warnings.append("no_level2_sections")
    if "### " not in text:
        warnings.append("no_level3_headings")
    if len(headers) < 5:
        warnings.append("too_few_headings")
    if not has_figure_marker(text):
        warnings.append("no_figure_markers")
    if len(text.splitlines()) < 20:
        warnings.append("note_too_short")
    if mixed_issues:
        warnings.append("mixed_language_lines_present")
    if mechanical_artifact_issues:
        warnings.append("mechanical_translation_artifacts_present")
    if linebreak_issues:
        warnings.append("suspicious_mid_sentence_linebreaks")
    if code_math_issues:
        warnings.append("suspicious_code_formatted_math")
    if math_issues:
        warnings.append("math_render_issues_present")

    payload = {
        "status": "ok",
        "script": "lint_note.py",
        "paper_id": args.paper_id,
        "input_path": str(path),
        "headers": headers,
        "missing_sections": missing_sections,
        "warnings": warnings,
        "mixed_language_issues": mixed_issues,
        "mechanical_translation_artifact_issues": mechanical_artifact_issues,
        "linebreak_issues": linebreak_issues,
        "code_math_issues": code_math_issues,
        "math_render_issues": math_issues,
        "figure_structure_issues": figure_issues,
        "core_info_structure_issues": core_info_issues,
        "substantive_content_issues": substantive_issues,
        "planning_artifact_found": planning_artifact_found,
        "planning_artifact_issues": planning_artifact_issues,
        "passes_basic_structure": (
            not missing_sections
            and not core_info_issues
            and not {
                "title_heading_missing",
                "no_level2_sections",
                "front_matter_order_invalid",
            }
            & set(warnings)
        ),
        "passes_style_gate": (
            not mixed_issues
            and not mechanical_artifact_issues
            and not linebreak_issues
            and not code_math_issues
        ),
        "passes_math_gate": not math_issues,
        "passes_figure_gate": not figure_issues,
        "passes_plan_gate": planning_artifact_found and not planning_artifact_issues,
        "passes_substantive_content": not any(
            str(issue.get("severity", "")) == "error" for issue in substantive_issues
        ),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
