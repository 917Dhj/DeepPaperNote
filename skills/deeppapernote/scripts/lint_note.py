#!/usr/bin/env python3
"""Check whether a drafted note meets structure and quality expectations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from contracts import (
    NOTE_PLAN_FIELD_TYPES,
    NOTE_PLAN_REQUIRED_FIELDS,
    PAPER_TYPE_VALUES,
    WRITING_CONTRACT_RULES,
    required_field_value_error,
    connection_plan_issues,
    note_required_sections,
    storyline_plan_issues,
    takeaway_plan_issues,
    type_plan_issues,
    weak_evidence_question_ids,
)
from type_profiles import (
    NOT_REPORTED_PHRASE,
    PROFILES,
    WEAK_EVIDENCE_CALLOUT,
    middle_sections,
    section_name,
    sections_with,
)
from _frontmatter import FrontmatterError, parse_frontmatter
from localization import (
    normalize_output_language,
    note_schema,
    require_artifact_output_language,
)

ACTIVE_LANGUAGE = "zh-CN"
SCHEMA: dict = {}
SECTIONS: dict[str, str] = {}
REQUIRED_SECTIONS: tuple[str, ...] = ()
PAPER_TYPE = ""
MIDDLE_SECTIONS: tuple[str, ...] = ()
RESULTS_SECTIONS: tuple[str, ...] = ()
NUMBER_SECTIONS: tuple[str, ...] = ()
CORE_INFO_FIELDS: list[str] = []
CORE_INFO_FIELD_INDEX: dict[str, int] = {}
CORE_INFO_FIELD_ALIASES: dict[str, str] = {}
FIGURE_TARGET_SECTIONS: set[str] = set()
FIGURE_LABELS: dict[str, str] = {}
TAKEAWAY_SUBSECTIONS: tuple[str, ...] = ()
TAKEAWAY_JUDGMENT_MARKER = ""
TAKEAWAY_MAX_ITEM_CHARS = 0
MY_NOTES_GUIDANCE = ""
CONNECTION_SUBSECTIONS: dict[str, str] = {}
CONNECTION_RELATION_LABELS: dict[str, str] = {}
CONNECTION_EMPTY_STATEMENTS: tuple[str, ...] = ()

def configure_output_language(language: str | None = None) -> str:
    global ACTIVE_LANGUAGE, SCHEMA, SECTIONS, REQUIRED_SECTIONS, CORE_INFO_FIELDS
    global CORE_INFO_FIELD_INDEX, CORE_INFO_FIELD_ALIASES, FIGURE_LABELS
    global TAKEAWAY_SUBSECTIONS, TAKEAWAY_JUDGMENT_MARKER, TAKEAWAY_MAX_ITEM_CHARS, MY_NOTES_GUIDANCE
    global CONNECTION_SUBSECTIONS, CONNECTION_RELATION_LABELS, CONNECTION_EMPTY_STATEMENTS
    ACTIVE_LANGUAGE = normalize_output_language(language)
    SCHEMA = note_schema(ACTIVE_LANGUAGE)
    SECTIONS = dict(SCHEMA["sections"])
    CORE_INFO_FIELDS = list(SCHEMA["core_info_fields"])
    CORE_INFO_FIELD_INDEX = {field: idx for idx, field in enumerate(CORE_INFO_FIELDS)}
    CORE_INFO_FIELD_ALIASES = dict(SCHEMA.get("core_info_aliases", {}))
    FIGURE_LABELS = dict(SCHEMA["figure_labels"])
    TAKEAWAY_SUBSECTIONS = tuple(SCHEMA["takeaways_subsections"].values())
    TAKEAWAY_JUDGMENT_MARKER = str(SCHEMA["takeaways_judgment_marker"])
    TAKEAWAY_MAX_ITEM_CHARS = int(SCHEMA["takeaways_max_item_chars"])
    MY_NOTES_GUIDANCE = str(SCHEMA["my_notes_guidance"])
    CONNECTION_SUBSECTIONS = dict(SCHEMA["connections_subsections"])
    CONNECTION_RELATION_LABELS = dict(SCHEMA["connections_relation_labels"])
    CONNECTION_EMPTY_STATEMENTS = tuple(SCHEMA["connections_empty_statements"].values())
    configure_paper_type(PAPER_TYPE)
    return ACTIVE_LANGUAGE


def configure_paper_type(paper_type: str) -> str:
    """Set the note's section list from its paper type; an unknown type leaves no middle."""
    global PAPER_TYPE, REQUIRED_SECTIONS, MIDDLE_SECTIONS, RESULTS_SECTIONS, NUMBER_SECTIONS, FIGURE_TARGET_SECTIONS
    PAPER_TYPE = paper_type if paper_type in PROFILES else ""
    MIDDLE_SECTIONS = middle_sections(PAPER_TYPE, ACTIVE_LANGUAGE)
    REQUIRED_SECTIONS = note_required_sections(ACTIVE_LANGUAGE, PAPER_TYPE)
    RESULTS_SECTIONS = sections_with(PAPER_TYPE, "results", ACTIVE_LANGUAGE)
    NUMBER_SECTIONS = sections_with(PAPER_TYPE, "expects_numbers", ACTIVE_LANGUAGE)
    FIGURE_TARGET_SECTIONS = {*MIDDLE_SECTIONS, SECTIONS["limitations"]} if SECTIONS else set()
    return PAPER_TYPE

def section(key: str) -> str:
    return SECTIONS[key]

def figure_prefix(key: str) -> str:
    return f"> {FIGURE_LABELS[key]}"

configure_output_language()

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
        (?<!no\s)(?<!not\s)high[-\s]*(?:confidence|match)
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
HTTP_URL_RE = re.compile(r"https?://\S+")
ENGLISH_METADATA_SOURCE_SPAN_PATTERNS = (
    re.compile(r"`[^`\n]+`"),
    re.compile(r"\[[^\]\n]+\]\([^)\n]+\)"),
)
# Body wikilinks are left to paper-glossary, so only an HTTP link can carry a CJK name.
ENGLISH_CJK_ENTITY_LINK_RE = re.compile(
    r"\[[^\]\n]*[\u4e00-\u9fff][^\]\n]*\]\(https?://[^)\n]+\)"
)
ENGLISH_CJK_MATH_LABEL_RE = re.compile(
    r"\\operatorname\{(?:输入|输出|损失|状态|动作|奖励|标签|样本|预测|目标)\}"
)
ENGLISH_MATH_SPAN_RE = re.compile(r"\$\$[^$\n]+\$\$|\$[^$\n]+\$")
CHINESE_PROSE_MATH_SPAN_RE = re.compile(r"\$\$[^$\n]+\$\$|\$[^$\n]+\$|\\\([^\n]+?\\\)")
CHINESE_PROSE_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
CHINESE_PROSE_WIKILINK_RE = re.compile(r"!?\[\[[^\]\n]+\]\]")
CHINESE_PROSE_CITATION_RE = re.compile(
    r"\[\d+(?:\s*[,–-]\s*\d+)*\]"
    r"|\([A-Z][^()\n]*?\bet al\.,?\s*\d{4}[a-z]?\)"
)
# A run is ASCII text that CJK characters and CJK punctuation do not interrupt.
ENGLISH_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 \t.,'’/%+-]*")
ENGLISH_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.-]*\b")
# An untranslated clause, as opposed to a list of names, joins words with function words.
MIXED_LANGUAGE_MIN_RUN_WORDS = 4
# Bare English words scattered through one line read as code-switching even without a clause.
MIXED_LANGUAGE_MIN_BARE_WORDS = 7
# Backticks keep proper nouns out of the count; a span this rich in function words is prose.
BACKTICKED_PROSE_MIN_FUNCTION_WORDS = 3

RUNTIME_ARTIFACT_REFERENCE_PATTERNS = [
    re.compile(
        r"\b[A-Za-z0-9][A-Za-z0-9._-]*_"
        r"(?:source_manifest|note_plan|raw_sections)\."
        r"(?:json|jsonl)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\b[A-Za-z0-9][A-Za-z0-9._-]*_(?:bundle|lint)\.json\b", flags=re.IGNORECASE),
    re.compile(r"(?:/private)?/tmp/[^\s)\]>\"']*"),
    re.compile(r"(?<![A-Za-z0-9:])/?artifacts/[^\s)\]>\"']*"),
    re.compile(r"\b(?:source_manifest|note_plan|raw_sections)\b", flags=re.IGNORECASE),
]

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
    p.add_argument("--language", default="", help="Run Override for output language: en or zh-CN.")
    return p


def resolve_note_plan_path(note_path: Path, plan_file: str) -> Path:
    if plan_file:
        return Path(plan_file).expanduser().resolve()
    return note_path.with_suffix(".plan.json")


def inspect_note_plan(
    plan_path: Path,
    output_language: str | None = None,
) -> tuple[bool, list[str]]:
    if not plan_path.exists():
        return False, ["planning_artifact_missing"]

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True, ["planning_artifact_invalid_json"]

    if not isinstance(plan, dict):
        return True, ["planning_artifact_not_object"]

    issues: list[str] = []
    try:
        require_artifact_output_language(
            plan,
            "Note Plan",
            output_language or ACTIVE_LANGUAGE,
        )
    except ValueError as exc:
        issues.append(f"planning_output_language_contract_failed: {exc}")
    missing_fields = [field for field in NOTE_PLAN_REQUIRED_FIELDS if field not in plan]
    if missing_fields:
        issues.append("planning_required_fields_missing")
        issues.extend(f"planning_{field}_missing" for field in missing_fields)

    required_checks = WRITING_CONTRACT_RULES["note_plan_required_field_checks"]
    invalid_fields: list[str] = []
    for field in NOTE_PLAN_REQUIRED_FIELDS:
        if field not in plan:
            continue
        validation_error = required_field_value_error(
            plan[field], NOTE_PLAN_FIELD_TYPES[field], required_checks
        )
        if validation_error == "invalid":
            invalid_fields.append(field)
        elif validation_error == "empty":
            issues.append(f"planning_{field}_empty")
    if isinstance(plan.get("paper_type"), str) and plan["paper_type"].strip():
        if plan["paper_type"].strip() not in PAPER_TYPE_VALUES:
            issues.append("planning_paper_type_invalid")
    if invalid_fields:
        issues.append("planning_required_fields_invalid")
        issues.extend(
            f"planning_{field}_invalid: expected {NOTE_PLAN_FIELD_TYPES[field]}"
            for field in invalid_fields
        )
    issues.extend(inspect_central_claims_plan(plan.get("central_claims")))
    plan_codes = {
        "note_plan_takeaway_item_count_invalid": "count_invalid",
        "note_plan_takeaway_item_invalid": "item_invalid",
        "note_plan_takeaway_item_too_thin": "item_too_thin",
        "note_plan_reader_research_direction_invalid": "invalid",
        "note_plan_key_prior_work_count_invalid": "count_invalid",
        "note_plan_key_prior_work_item_invalid": "item_invalid",
        "note_plan_connections_invalid": "invalid",
        "note_plan_connections_count_invalid": "count_invalid",
        "note_plan_connection_item_invalid": "item_invalid",
        "note_plan_connection_relation_invalid": "relation_invalid",
        "note_plan_connection_duplicate": "duplicate",
    }
    for item in [*takeaway_plan_issues(plan), *connection_plan_issues(plan)]:
        code = f"planning_{item['field']}_{plan_codes[item['code']]}"
        if code not in issues:
            issues.append(code)
    for item in [*type_plan_issues(plan, output_language), *storyline_plan_issues(plan)]:
        code = "planning_" + item["code"].removeprefix("note_plan_")
        if code not in issues:
            issues.append(code)

    return True, issues


def inspect_central_claims_plan(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return ["planning_central_claims_invalid"]

    issues: list[str] = []
    contract = WRITING_CONTRACT_RULES["analysis_coverage_contract"]
    required_fields = contract["central_claim_fields"]
    field_types = contract["central_claim_field_types"]
    required_checks = contract["central_claim_required_field_checks"]
    for item in value:
        if not isinstance(item, dict):
            if "planning_central_claims_invalid" not in issues:
                issues.append("planning_central_claims_invalid")
            continue
        for field in required_fields:
            field_value = item.get(field)
            field_type = field_types[field]
            if required_field_value_error(field_value, field_type, required_checks):
                code = (
                    "planning_central_claims_supporting_evidence_missing"
                    if field == "supporting_evidence"
                    else f"planning_central_claims_{field}_missing"
                )
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
    required_order = [f"## {section('abstract')}", f"## {section('contributions')}", f"## {section('one_sentence_summary')}"]
    positions = []
    for required_heading in required_order:
        idx = text.find(required_heading)
        if idx < 0:
            return warnings
        positions.append(idx)
    if positions != sorted(positions):
        warnings.append("front_matter_order_invalid")
    return warnings


def english_top_level_section_warnings(text: str) -> list[str]:
    if ACTIVE_LANGUAGE != "en":
        return []
    actual = re.findall(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE)
    return [] if actual == list(REQUIRED_SECTIONS) else ["top_level_section_profile_invalid"]


def _inside_any_span(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def inspect_reference_hygiene(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()
    for idx, line in enumerate(text.splitlines(), start=1):
        url_spans = [(match.start(), match.end()) for match in HTTP_URL_RE.finditer(line)]
        for pattern in RUNTIME_ARTIFACT_REFERENCE_PATTERNS:
            for match in pattern.finditer(line):
                matched_text = match.group(0)
                if _inside_any_span(match.start(), match.end(), url_spans):
                    continue
                key = (idx, matched_text)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    {
                        "line_number": idx,
                        "line": line.strip(),
                        "reason": "runtime_artifact_reference",
                        "match": matched_text,
                    }
                )
    return issues


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
    prefixes = [f"- {field}:" for field in (*CORE_INFO_FIELDS, *CORE_INFO_FIELD_ALIASES)]
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
        or stripped.startswith(figure_prefix("location"))
        or stripped.startswith(figure_prefix("reason"))
        or stripped.startswith(figure_prefix("status"))
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


def english_function_word_hits(words: list[str]) -> list[str]:
    return [word for word in words if word.lower() in ENGLISH_FUNCTION_WORDS]


def chinese_prose_without_exempt_spans(line: str) -> str:
    def code_span(match: re.Match[str]) -> str:
        content = match.group(1)
        hits = english_function_word_hits(ENGLISH_WORD_RE.findall(content))
        return content if len(hits) >= BACKTICKED_PROSE_MIN_FUNCTION_WORDS else " "

    checked = CHINESE_PROSE_CODE_SPAN_RE.sub(code_span, line)
    checked = CHINESE_PROSE_MATH_SPAN_RE.sub(" ", checked)
    checked = CHINESE_PROSE_WIKILINK_RE.sub(" ", checked)
    return CHINESE_PROSE_CITATION_RE.sub(" ", checked)


def chinese_prose_english_issue(line: str) -> dict[str, object] | None:
    checked = chinese_prose_without_exempt_spans(line)
    for match in ENGLISH_RUN_RE.finditer(checked):
        words = ENGLISH_WORD_RE.findall(match.group(0))
        hits = english_function_word_hits(words)
        if len(words) >= MIXED_LANGUAGE_MIN_RUN_WORDS and hits:
            return {
                "signal": "english_clause",
                "english_run": " ".join(match.group(0).split()).rstrip(".,"),
                "english_word_count": len(words),
                "function_word_hits": hits[:6],
            }
    words = ENGLISH_WORD_RE.findall(checked)
    if len(words) >= MIXED_LANGUAGE_MIN_BARE_WORDS:
        return {
            "signal": "scattered_english_words",
            "english_words": words[:12],
            "english_word_count": len(words),
        }
    return None


def mixed_language_issues(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    lines = text.splitlines()
    fenced_code_lines: set[int] = set()
    fence_start: int | None = None
    for line_index, line in enumerate(lines, start=1):
        if not line.strip().startswith("```"):
            continue
        if fence_start is None:
            fence_start = line_index
        else:
            fenced_code_lines.update(range(fence_start, line_index + 1))
            fence_start = None
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if idx in fenced_code_lines:
            continue
        if ACTIVE_LANGUAGE == "en":
            checked = stripped
            section_name = section_name_for_line(lines, idx - 1)
            if section_name in {section("core_information"), section("connections")}:
                for pattern in ENGLISH_METADATA_SOURCE_SPAN_PATTERNS:
                    checked = pattern.sub("", checked)
            if section_name == section("connections"):
                checked = WIKILINK_SPAN_RE.sub("", checked)
            if stripped.startswith(f"*{FIGURE_LABELS['original_caption']}"):
                checked = ENGLISH_METADATA_SOURCE_SPAN_PATTERNS[0].sub("", checked)
            checked = ENGLISH_CJK_ENTITY_LINK_RE.sub("", checked)
            checked = ENGLISH_MATH_SPAN_RE.sub(
                lambda match: ENGLISH_CJK_MATH_LABEL_RE.sub("", match.group(0)),
                checked,
            )
            checked = HTTP_URL_RE.sub("", checked)
            if re.search(r"[\u4e00-\u9fff]", checked):
                issues.append({"line_number": idx, "line": stripped, "reason": "non_english_text_present"})
            continue
        if is_exempt_line(line):
            continue
        section_name = section_name_for_line(lines, idx - 1)
        if section_name in {section("core_information"), section("connections")}:
            continue
        if not re.search(r"[\u4e00-\u9fff]", stripped):
            continue
        english_issue = chinese_prose_english_issue(stripped)
        if english_issue is not None:
            issues.append({"line_number": idx, "line": stripped, **english_issue})
    return issues


def mechanical_translation_artifact_issues(text: str) -> list[dict[str, object]]:
    if ACTIVE_LANGUAGE == "en":
        return []
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
            if nxt.startswith(figure_prefix("location")):
                has_location = True
            if nxt.startswith(figure_prefix("reason")):
                has_reason = True
            if nxt.startswith(figure_prefix("status")):
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
    prefix = figure_prefix("status")
    if not stripped.startswith(prefix):
        return ""
    return stripped.removeprefix(prefix).strip()


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
            prefix = figure_prefix("location")
            if nxt.startswith(prefix):
                location = nxt.removeprefix(prefix).strip()
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
        matched = [section for section in FIGURE_TARGET_SECTIONS if section in location]
        # "方法" is inside "现有方法的局限"; keep only the most specific names the location gives.
        target_sections = [name for name in matched if not any(name != other and name in other for other in matched)]
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
    core_heading = section("core_information")
    body = section_body(text, core_heading)
    if not body:
        return []

    issues: list[dict[str, object]] = []
    seen_fields: set[str] = set()
    last_known_index = -1
    base_line = _line_number_from_offset(text, text.find(f"## {core_heading}"))

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
        field = CORE_INFO_FIELD_ALIASES.get(field, field)
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
    if stripped.startswith(("#", "-", "*", "> ", "```", "![[", f"*{FIGURE_LABELS['original_caption']}")):
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
    if ACTIVE_LANGUAGE == "en":
        # Currency amounts such as "$25 billion" are prose, not LaTeX delimiters.
        sanitized = re.sub(
            r"\$(?=\d+(?:\.\d+)?\s+(?:thousand|million|billion|trillion|dollars?|usd)\b)",
            r"\$",
            sanitized,
            flags=re.IGNORECASE,
        )
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
            or stripped.startswith(figure_prefix("location"))
            or stripped.startswith(figure_prefix("reason"))
            or stripped.startswith(figure_prefix("status"))
        ):
            continue
        if stripped.startswith("!["):
            continue
        if stripped.startswith(f"*{FIGURE_LABELS['original_caption']}") and stripped.endswith("*"):
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


def inspect_substantive_content(text: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    my_notes_heading = section("my_notes")
    for section_heading in REQUIRED_SECTIONS:
        if section_heading == my_notes_heading:
            continue  # user-owned: generated drafts carry only the standard guidance
        body = section_body(text, section_heading)
        content = normalized_section_content(body)
        if is_placeholder_like(content):
            issues.append(issue(section_heading, "section_empty_shell", "error", content or section_heading))
        if section_heading not in {*RESULTS_SECTIONS, section("connections")} and is_honest_missing_declaration(content):
            issues.append(issue(section_heading, "section_honest_missing_not_allowed", "error", content))

    contributions_heading = section("contributions")
    innovation = section_body(text, contributions_heading)
    innovation_content = normalized_section_content(innovation)
    innovation_units = meaningful_units(innovation, GENERIC_INNOVATION_PATTERNS)
    if not innovation_units:
        issues.append(issue(contributions_heading, "innovation_empty_shell", "error", innovation_content))
    elif len(innovation_units) < 2:
        issues.append(issue(contributions_heading, "innovation_too_few_specific_points", "warning", innovation_content))

    for results_heading in RESULTS_SECTIONS:
        results_body = section_body(text, results_heading)
        results_content = normalized_section_content(results_body)
        if is_honest_missing_declaration(results_content):
            issues.append(issue(results_heading, "key_results_honest_missing_not_allowed", "error", results_content))
        elif not meaningful_units(results_body, GENERIC_KEY_RESULT_PATTERNS):
            issues.append(issue(results_heading, "key_results_empty_shell", "error", results_content))
        elif results_heading in NUMBER_SECTIONS and not has_number_token(results_content):
            issues.append(issue(results_heading, "key_results_quantitative_result_missing", "warning", results_content))

    limitations_heading = section("limitations")
    limitations = section_body(text, limitations_heading)
    limitations_content = normalized_section_content(limitations)
    if not meaningful_units(limitations, GENERIC_LIMITATION_PATTERNS):
        issues.append(issue(limitations_heading, "limitations_empty_shell", "error", limitations_content))

    for section_heading in MIDDLE_SECTIONS:
        if section_heading in RESULTS_SECTIONS:
            continue
        body = section_body(text, section_heading)
        content = normalized_section_content(body)
        if not meaningful_units(body):
            issues.append(issue(section_heading, "section_empty_shell", "error", content or section_heading))

    issues.extend(inspect_takeaways(text))
    issues.extend(body_wikilink_issues(text))
    issues.extend(inspect_my_notes(text))

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in issues:
        key = (str(item["section"]), str(item["reason"]), str(item["severity"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
LIST_ITEM_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def inspect_takeaways(text: str) -> list[dict[str, object]]:
    heading = section("takeaways")
    if not section_body(text, heading):
        return []
    contract = WRITING_CONTRACT_RULES["takeaways_contract"]
    issues: list[dict[str, object]] = []
    for subsection in TAKEAWAY_SUBSECTIONS:
        body = subsection_body(text, heading, subsection)
        if not re.search(rf"^###\s+{re.escape(subsection)}\s*$", section_body(text, heading), flags=re.MULTILINE):
            issues.append(issue(heading, "takeaways_subsection_missing", "error", subsection))
            continue
        items = takeaway_items(body)
        if not contract["min_items"] <= len(items) <= contract["max_items"]:
            issues.append(issue(heading, "takeaways_item_count_invalid", "error", f"{subsection}: {len(items)}"))
        for item in items:
            if sum(1 for ch in item if not ch.isspace()) > TAKEAWAY_MAX_ITEM_CHARS:
                issues.append(issue(heading, "takeaways_item_too_long", "warning", item))
    return issues


def takeaway_items(body: str) -> list[str]:
    return [LIST_ITEM_PREFIX_RE.sub("", line, count=1).strip() for line in body.splitlines() if LIST_ITEM_RE.match(line)]


def inspect_takeaway_judgment(text: str, reader_research_direction: str) -> list[dict[str, object]]:
    """With a stated research direction, at least one transferable idea must carry the judgment marker."""
    if not reader_research_direction.strip():
        return []
    heading = section("takeaways")
    transferable = TAKEAWAY_SUBSECTIONS[0]
    items = takeaway_items(subsection_body(text, heading, transferable))
    if any(item.lstrip("*_ ").startswith(TAKEAWAY_JUDGMENT_MARKER) for item in items):
        return []
    return [issue(heading, "takeaways_judgment_marker_missing", "error", transferable)]


ISO_DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def note_paper_type(text: str, plan: dict) -> str:
    """The plan's paper_type, else the note's frontmatter paper_type."""
    value = plan.get("paper_type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    try:
        fields = parse_frontmatter(text) or {}
    except FrontmatterError:
        return ""
    value = fields.get("paper_type")
    return value.strip() if isinstance(value, str) else ""


def frontmatter_issues(text: str, plan_paper_type: str) -> list[str]:
    """Check the Obsidian properties that research memory and connections rely on."""
    contract = WRITING_CONTRACT_RULES["frontmatter_contract"]
    try:
        fields = parse_frontmatter(text)
    except FrontmatterError:
        return ["frontmatter_unparseable"]
    if fields is None:
        return ["frontmatter_missing"]
    issues: list[str] = []
    if any(field not in fields for field in contract["required_fields"]):
        issues.append("frontmatter_field_missing")
    tags = fields.get("tags")
    tag_values = tags if isinstance(tags, list) else [tags] if isinstance(tags, str) else []
    prefix = contract["domain_tag_prefix"]
    domain_tags = [
        tag for tag in tag_values
        if isinstance(tag, str) and tag.startswith(prefix) and len(tag) > len(prefix)
    ]
    if not domain_tags:
        issues.append("frontmatter_domain_tag_missing")
    elif len(domain_tags) > 1:
        issues.append("frontmatter_domain_tag_multiple")
    paper_type = fields.get("paper_type")
    if "paper_type" in fields and plan_paper_type and paper_type != plan_paper_type:
        issues.append("frontmatter_paper_type_mismatch")
    for field in contract["list_fields"]:
        if field not in fields:
            continue
        value = fields[field]
        if (
            not isinstance(value, list)
            or len(value) > contract["max_list_items"]
            or any(not item.strip() for item in value)
        ):
            issues.append("frontmatter_list_field_invalid")
            break
    if "read_date" in fields and not valid_iso_day(fields["read_date"]):
        issues.append("frontmatter_read_date_invalid")
    return issues


def valid_iso_day(value: object) -> bool:
    if not isinstance(value, str) or not ISO_DAY_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def plan_paper_type(plan_path: Path | None) -> str:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = plan.get("paper_type", "") if isinstance(plan, dict) else ""
    return value.strip() if isinstance(value, str) else ""


def plan_reader_research_direction(plan_path: Path | None) -> str:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    value = plan.get("reader_research_direction", "") if isinstance(plan, dict) else ""
    return value if isinstance(value, str) else ""


WIKILINK_SPAN_RE = re.compile(r"\[\[[^\[\]\n]*\]\]")
CONNECTION_ENTRY_RES = {
    "zh-CN": re.compile(r"^-\s+\[\[([^\[\]|#\n]+)\|([^\[\]\n]+)\]\]（([^（）]+)）：\s*\S.*$"),
    "en": re.compile(r"^-\s+\[\[([^\[\]|#\n]+)\|([^\[\]\n]+)\]\]\s+\(([^()]+)\):\s+\S.*$"),
}


def load_plan(plan_path: Path | None) -> dict:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return plan if isinstance(plan, dict) else {}


def inspect_connections(text: str, plan: dict) -> list[dict[str, object]]:
    """The Connections section mirrors the plan: same link targets, same relations."""
    heading = section("connections")
    body = section_body(text, heading)
    if not body:
        return []
    contract = WRITING_CONTRACT_RULES["connections_contract"]
    issues: list[dict[str, object]] = []
    missing = [
        name for name in CONNECTION_SUBSECTIONS.values()
        if not re.search(rf"^###\s+{re.escape(name)}\s*$", body, flags=re.MULTILINE)
    ]
    for name in missing:
        issues.append(issue(heading, "connections_subsection_missing", "error", name))
    if missing:
        return issues

    planned = {
        item["target"]: item.get("relation", "")
        for item in plan.get("connections") or []
        if isinstance(item, dict) and isinstance(item.get("target"), str)
    }
    label_to_relation = {label: key for key, label in CONNECTION_RELATION_LABELS.items()}
    in_vault = subsection_body(text, heading, CONNECTION_SUBSECTIONS["in_vault"])
    lines = [line.strip() for line in in_vault.splitlines() if line.strip()]
    entries = [line for line in lines if LIST_ITEM_RE.match(line)]
    if not entries:
        if " ".join(lines) not in CONNECTION_EMPTY_STATEMENTS:
            issues.append(issue(heading, "connections_empty_statement_invalid", "error", " ".join(lines)))
    else:
        if len(entries) != len(lines):
            issues.append(issue(heading, "connections_entry_invalid", "error", in_vault.strip()))
        if len(entries) > contract["max_in_vault"]:
            issues.append(issue(heading, "connections_count_invalid", "error", str(len(entries))))
    written: dict[str, str] = {}
    for entry in entries:
        match = CONNECTION_ENTRY_RES[ACTIVE_LANGUAGE].match(entry)
        if match is None:
            issues.append(issue(heading, "connections_entry_invalid", "error", entry))
            continue
        target, _, label = match.groups()
        relation = label_to_relation.get(label.strip())
        if relation is None:
            issues.append(issue(heading, "connections_relation_invalid", "error", entry))
        elif target.strip() in planned and planned[target.strip()] != relation:
            issues.append(issue(heading, "connections_relation_mismatch", "error", entry))
        written[target.strip()] = label
    if set(written) != set(planned) and not any(
        item["reason"] == "connections_entry_invalid" for item in issues
    ):
        issues.append(
            issue(heading, "connections_targets_mismatch_plan", "error",
                  f"note: {sorted(written)}; plan: {sorted(planned)}")
        )

    prior = subsection_body(text, heading, CONNECTION_SUBSECTIONS["key_prior_work"])
    count = sum(1 for line in prior.splitlines() if LIST_ITEM_RE.match(line))
    limits = contract["key_prior_work_items"]
    if not limits["min"] <= count <= limits["max"]:
        issues.append(issue(heading, "key_prior_work_count_invalid", "error", str(count)))
    return issues


BODY_WIKILINK_RE = re.compile(r"(?<!!)\[\[[^\[\]\n]+\]\]")


def body_wikilink_issues(text: str) -> list[dict[str, object]]:
    """Only Connections links notes; term links in prose belong to paper-glossary."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        start = closing + 1 if closing is not None else len(lines)
    issues: list[dict[str, object]] = []
    in_fence = False
    current = ""
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        heading = re.match(r"^##\s+(.+)$", stripped)
        if heading and not in_fence:
            current = heading.group(1).strip()
            if current == section("my_notes"):
                break  # user-owned to the end of the file
            continue
        if in_fence or current == section("connections"):
            continue
        if BODY_WIKILINK_RE.search(line):
            issues.append(issue(current, "wikilink_outside_connections", "error", stripped))
    return issues


def inspect_my_notes(text: str) -> list[dict[str, object]]:
    heading = section("my_notes")
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return []
    issues: list[dict[str, object]] = []
    later_heading = re.search(r"^##\s+.+$", text[match.end():], flags=re.MULTILINE)
    if later_heading:
        issues.append(issue(heading, "my_notes_not_last", "error", later_heading.group(0)))
    body = section_body(text, heading).strip()
    if body != MY_NOTES_GUIDANCE:
        issues.append(issue(heading, "my_notes_guidance_mismatch", "error", body))
    return issues


def _subsection_under(text: str, section_heading: str, subsection_heading: str) -> bool:
    body = section_body(text, section_heading)
    return bool(re.search(rf"^###\s+{re.escape(subsection_heading)}\s*$", body, flags=re.MULTILINE))


def _table_blocks(body: str) -> list[list[list[str]]]:
    """Markdown tables in body, each as rows of stripped cells (separator rows dropped)."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in [*body.splitlines(), ""]:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    return tables


def inspect_workflow(text: str, plan: dict) -> list[dict[str, object]]:
    """The workflow subsection mirrors note_plan `workflow`: an overview chain and a step table per flow."""
    workflow = PROFILES.get(PAPER_TYPE, {}).get("workflow")
    if not workflow:
        return []
    host = section_name(PAPER_TYPE, workflow["section"], ACTIVE_LANGUAGE)
    heading = workflow["heading"][ACTIVE_LANGUAGE]
    if not _subsection_under(text, host, heading):
        return [issue(host, "workflow_subsection_missing", "error", heading)]
    body = subsection_body(text, host, heading)
    flows = plan.get("workflow") if isinstance(plan.get("workflow"), list) else []
    if not flows:
        if workflow["may_be_unreported"] and NOT_REPORTED_PHRASE[ACTIVE_LANGUAGE].casefold() in body.casefold():
            return []
        return [issue(heading, "workflow_unreported_statement_missing", "error", body.strip()[:120])]
    issues: list[dict[str, object]] = []
    tables = _table_blocks(body)
    if len(tables) != len(flows):
        issues.append(issue(heading, "workflow_table_count_mismatch", "error", f"{len(tables)} tables for {len(flows)} flows"))
    expected_header = list(workflow["table_headers"][ACTIVE_LANGUAGE])
    for flow, table in zip(flows, tables):
        steps = flow.get("steps") if isinstance(flow, dict) else None
        if table[0] != expected_header:
            issues.append(issue(heading, "workflow_table_header_invalid", "error", " | ".join(table[0])))
        if isinstance(steps, list) and len(table) - 1 != len(steps):
            issues.append(issue(heading, "workflow_step_count_mismatch", "error", f"{len(table) - 1} rows for {len(steps)} steps"))
    chains = [line for line in body.splitlines() if line.count("→") >= 2 and not line.strip().startswith("|")]
    if len(chains) < len(flows):
        issues.append(issue(heading, "workflow_overview_missing", "error", f"{len(chains)} overview lines for {len(flows)} flows"))
    return issues


def inspect_secondary_type(text: str, plan: dict) -> list[dict[str, object]]:
    secondary = plan.get("secondary_type")
    host = plan.get("secondary_host_section")
    if not isinstance(secondary, str) or secondary not in PROFILES or secondary == PAPER_TYPE:
        return []
    heading = PROFILES[secondary]["secondary_heading"][ACTIVE_LANGUAGE]
    if not isinstance(host, str) or not _subsection_under(text, host, heading):
        return [issue(str(host or ""), "secondary_subsection_missing", "error", heading)]
    return []


def inspect_weak_evidence_callout(text: str, plan: dict) -> list[dict[str, object]]:
    """The weak-evidence callout sits between the title and the first section, exactly when the plan calls for it."""
    body = strip_frontmatter(text)
    first_section = re.search(r"^##\s", body, flags=re.MULTILINE)
    preamble = body[: first_section.start()] if first_section else body
    callout = WEAK_EVIDENCE_CALLOUT[ACTIVE_LANGUAGE]
    present = any(line.strip() == callout for line in preamble.splitlines())
    unreported = weak_evidence_question_ids(plan) if PAPER_TYPE else []
    if unreported and not present:
        return [issue(SECTIONS.get("core_information", ""), "weak_evidence_callout_missing", "error", ", ".join(unreported))]
    if present and not unreported:
        return [issue(SECTIONS.get("core_information", ""), "weak_evidence_callout_unexpected", "error", callout)]
    return []


def strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block (---...---) if present.

    Tolerates CRLF (\\r\\n) line endings so notes written on Windows are
    stripped the same way as LF notes.
    """
    return re.sub(r"^---\r?\n.*?\r?\n---\r?\n?", "", text, count=1, flags=re.DOTALL)


def main() -> None:
    from common import emit, json_input_sha256, runtime_config

    args = parser().parse_args()
    config = runtime_config(cli_overrides={"output_language": args.language})
    output_language = configure_output_language(str(config["output_language"]))
    path = Path(args.input).expanduser().resolve()
    # utf-8-sig strips a leading BOM and the replace() normalizes CRLF so
    # Windows-authored notes are linted identically to LF/BOM-less notes;
    # otherwise the BOM/`\r` cause spurious title/frontmatter/style failures.
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    body_text = strip_frontmatter(text)
    headers = extract_headers(text)
    warnings: list[str] = []
    mixed_issues = mixed_language_issues(text)
    mechanical_artifact_issues = mechanical_translation_artifact_issues(text)
    linebreak_issues = suspicious_mid_sentence_linebreaks(body_text)
    code_math_issues = suspicious_code_formatted_math(text)
    math_issues = math_render_issues(text)
    figure_issues = figure_structure_issues(text)
    core_info_issues = core_info_structure_issues(text)
    reference_hygiene_issues = inspect_reference_hygiene(text)
    plan_path = resolve_note_plan_path(path, args.plan_file)
    plan = load_plan(plan_path)
    configure_paper_type(note_paper_type(text, plan))
    missing_sections = find_missing_sections(text)
    substantive_issues = inspect_substantive_content(text)
    note_plan_sha256 = json_input_sha256(plan_path)
    planning_artifact_found, planning_artifact_issues = inspect_note_plan(plan_path, output_language)
    substantive_issues.extend(inspect_connections(text, plan))
    substantive_issues.extend(inspect_workflow(text, plan))
    substantive_issues.extend(inspect_secondary_type(text, plan))
    substantive_issues.extend(inspect_weak_evidence_callout(text, plan))
    substantive_issues.extend(
        inspect_takeaway_judgment(text, plan_reader_research_direction(plan_path))
    )
    frontmatter_problems = frontmatter_issues(text, plan_paper_type(plan_path))
    warnings.extend(frontmatter_problems)
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
    warnings.extend(english_top_level_section_warnings(text))
    if not PAPER_TYPE:
        warnings.append("paper_type_unknown")
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
    if reference_hygiene_issues:
        warnings.append("runtime_artifact_references_present")

    payload = {
        "status": "ok",
        "script": "lint_note.py",
        "output_language": output_language,
        "paper_id": args.paper_id,
        "input_path": str(path),
        "note_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "note_plan_sha256": note_plan_sha256,
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
        "frontmatter_issues": frontmatter_problems,
        "reference_hygiene_issues": reference_hygiene_issues,
        "substantive_content_issues": substantive_issues,
        "planning_artifact_found": planning_artifact_found,
        "planning_artifact_issues": planning_artifact_issues,
        "passes_basic_structure": (
            not missing_sections
            and not core_info_issues
            and not frontmatter_problems
            and not {
                "title_heading_missing",
                "no_level2_sections",
                "front_matter_order_invalid",
                "top_level_section_profile_invalid",
                "paper_type_unknown",
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
        "passes_reference_hygiene_gate": not reference_hygiene_issues,
        "passes_plan_gate": planning_artifact_found and not planning_artifact_issues,
        "passes_substantive_content": not any(
            str(issue.get("severity", "")) == "error" for issue in substantive_issues
        ),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
