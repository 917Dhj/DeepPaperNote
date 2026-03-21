#!/usr/bin/env python3
"""Check whether a drafted note meets structure and quality expectations."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_SECTIONS = [
    "核心信息",
    "一句话总结",
    "研究问题",
    "数据与任务定义",
    "方法主线",
    "关键结果",
    "深度分析",
    "局限",
    "我的笔记",
    "引用",
]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "lint note")
    p.add_argument("--input", required=True, help="Markdown note path.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    return p


def extract_headers(text: str) -> list[str]:
    return [match.group(2).strip() for match in re.finditer(r"^(#{1,3})\s+(.+)$", text, flags=re.MULTILINE)]


def find_missing_sections(text: str) -> list[str]:
    missing = []
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            missing.append(section)
    return missing


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


def is_metadata_line(line: str) -> bool:
    stripped = line.strip()
    prefixes = [
        "- 标题:",
        "- 标题翻译:",
        "- 作者:",
        "- 机构:",
        "- 发表时间:",
        "- 会议 / 期刊:",
        "- DOI:",
        "- 论文链接:",
        "- 论文类型:",
        "- 链接:",
    ]
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
        stripped.startswith("> 建议位置：")
        or stripped.startswith("> 放置原因：")
        or stripped.startswith("> 当前状态：")
    ):
        return True
    if re.search(r"https?://", stripped):
        return True
    if re.search(r"`10\.\d{4,9}/", stripped):
        return True
    return False


def mixed_language_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if is_exempt_line(line):
            continue
        stripped = line.strip()
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


def main() -> None:
    from common import emit

    args = parser().parse_args()
    path = Path(args.input).expanduser().resolve()
    text = path.read_text(encoding="utf-8")
    headers = extract_headers(text)
    missing_sections = find_missing_sections(text)
    warnings: list[str] = []
    mixed_issues = mixed_language_issues(text)
    warnings.extend(inspect_figure_callouts(text))
    if not text.startswith("# "):
        warnings.append("title_heading_missing")
    if "## " not in text:
        warnings.append("no_level2_sections")
    if "### " not in text:
        warnings.append("no_level3_headings")
    if len(headers) < 5:
        warnings.append("too_few_headings")
    if "[!figure]" not in text and "[FIGURE_PLACEHOLDER]" not in text:
        warnings.append("no_figure_markers")
    if len(text.splitlines()) < 20:
        warnings.append("note_too_short")
    if mixed_issues:
        warnings.append("mixed_language_lines_present")

    payload = {
        "status": "ok",
        "script": "lint_note.py",
        "paper_id": args.paper_id,
        "input_path": str(path),
        "headers": headers,
        "missing_sections": missing_sections,
        "warnings": warnings,
        "mixed_language_issues": mixed_issues,
        "passes_basic_structure": not missing_sections and not {"title_heading_missing", "no_level2_sections"} & set(warnings),
        "passes_style_gate": not mixed_issues,
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
