#!/usr/bin/env python3
"""Language schemas shared by DeepPaperNote contracts and validators."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

DEFAULT_OUTPUT_LANGUAGE = "zh-CN"
SUPPORTED_OUTPUT_LANGUAGES = ("zh-CN", "en")
_ALIASES = {"zh": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN", "chinese": "zh-CN", "en": "en", "en-us": "en", "en_us": "en", "english": "en"}
_SCHEMAS: dict[str, dict[str, Any]] = {
    "zh-CN": {
        "sections": {"core_information": "核心信息", "abstract": "原文摘要翻译", "contributions": "创新点", "one_sentence_summary": "一句话总结", "research_questions": "研究问题", "data_and_task": "数据与任务定义", "method": "方法主线", "key_results": "关键结果", "deep_analysis": "深度分析", "limitations": "局限", "my_notes": "我的笔记", "references": "引用"},
        "core_info_fields": ("标题", "标题翻译", "作者", "机构", "发表时间", "发表渠道", "DOI", "arXiv", "论文链接", "代码 / 项目", "数据 / 资源", "论文类型"),
        "core_info_aliases": {},
        "figure_labels": {"location": "建议位置：", "reason": "放置原因：", "status": "当前状态：", "original_caption": "论文原图编号："},
        "mechanism_flow": "机制流程",
    },
    "en": {
        "sections": {"core_information": "Core Information", "abstract": "Abstract", "contributions": "Contributions", "one_sentence_summary": "One-Sentence Summary", "research_questions": "Research Questions", "data_and_task": "Data and Task Definition", "method": "Method", "key_results": "Key Results", "deep_analysis": "Deep Analysis", "limitations": "Limitations", "my_notes": "My Notes", "references": "References"},
        "core_info_fields": ("Title", "Translated title", "Authors", "Institutions", "Publication date", "Venue", "DOI", "arXiv", "Paper link", "Code / Project", "Data / Resources", "Paper type"),
        "core_info_aliases": {"Translated Title": "Translated title", "Author": "Authors", "Institution": "Institutions", "Publication Date": "Publication date", "Paper Link": "Paper link", "Code": "Code / Project", "Project": "Code / Project", "Data": "Data / Resources", "Resources": "Data / Resources", "Paper Type": "Paper type"},
        "figure_labels": {"location": "Suggested location:", "reason": "Why it matters:", "status": "Current status:", "original_caption": "Original paper item:"},
        "mechanism_flow": "Analytical Flow",
    },
}

def normalize_output_language(value: str | None = None) -> str:
    raw = (value if value is not None else os.environ.get("DEEPPAPERNOTE_OUTPUT_LANGUAGE", "")).strip()
    if not raw:
        return DEFAULT_OUTPUT_LANGUAGE
    normalized = _ALIASES.get(raw.lower(), raw)
    if normalized not in SUPPORTED_OUTPUT_LANGUAGES:
        raise ValueError(f"Unsupported DeepPaperNote output language: {raw}. Choose one of: {', '.join(SUPPORTED_OUTPUT_LANGUAGES)}.")
    return normalized

def note_schema(language: str | None = None) -> dict[str, Any]:
    return deepcopy(_SCHEMAS[normalize_output_language(language)])

def required_sections(language: str | None = None) -> tuple[str, ...]:
    return tuple(note_schema(language)["sections"].values())
