"""Extract sections, appendix pages, and caption lines from PDF text."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from common import fitz, normalize_title, normalize_whitespace

PDF_LIGATURE_MAP = {
    "\u00df": "ss",
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}


def normalize_pdf_text_artifacts(text: str) -> str:
    normalized = text or ""
    for original, replacement in PDF_LIGATURE_MAP.items():
        normalized = normalized.replace(original, replacement)
    return normalized


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def clean_pdf_line(line: str) -> str:
    line = re.sub(r"\s+", " ", normalize_pdf_text_artifacts(line or "")).strip()
    if not line:
        return ""
    if re.fullmatch(r"\d+", line):
        return ""
    if re.fullmatch(r"page \d+", line.lower()):
        return ""
    if len(line) <= 2 and not re.search(r"[\u3400-\u9fff]", line):
        return ""
    return line


def normalize_heading(line: str) -> str:
    line = normalize_pdf_text_artifacts(line or "").strip().lower()
    line = re.sub(r"^\s*(?:section\s*)?\d+(\.\d+)*[\s.、．:：-]*", "", line)
    line = re.sub(r"^\s*[一二三四五六七八九十百千]+[、．.:\s-]*", "", line)
    line = re.sub(r"^\s*[ivxlcdm]+[.)\s]+", "", line)
    line = re.sub(r"[^a-z0-9\u3400-\u9fff\s]", " ", line)
    line = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", line)
    return re.sub(r"\s+", " ", line).strip()


SECTION_ALIASES = {
    "abstract": {"abstract", "摘要"},
    "introduction": {
        "introduction",
        "background",
        "preliminaries",
        "preliminary",
        "related work",
        "literature review",
        "引言",
        "绪论",
        "背景",
        "相关工作",
        "文献综述",
    },
    "method": {
        "method",
        "methods",
        "approach",
        "approaches",
        "methodology",
        "framework",
        "model",
        "models",
        "materials",
        "materials and methods",
        "study design",
        "方法",
        "方法学",
        "研究方法",
        "材料与方法",
        "实验方法",
        "研究设计",
        "模型",
        "框架",
        "系统设计",
    },
    "data": {
        "data",
        "dataset",
        "datasets",
        "corpus",
        "data and materials",
        "数据",
        "数据集",
        "语料库",
    },
    "experiment": {
        "experiment",
        "experiments",
        "evaluation",
        "evaluations",
        "results",
        "experimental results",
        "evaluation results",
        "analysis",
        "findings",
        "ablations",
        "ablation",
        "实验",
        "实验结果",
        "结果",
        "研究结果",
        "评价",
        "评估",
        "分析",
        "发现",
        "消融",
    },
    "conclusion": {
        "conclusion",
        "conclusions",
        "discussion",
        "discussions",
        "future work",
        "limitations",
        "limitation",
        "结论",
        "总结",
        "讨论",
        "局限",
        "不足",
        "未来工作",
    },
}

STOP_SECTION_ALIASES = {
    "references",
    "bibliography",
    "appendix",
    "appendices",
    "supplementary material",
    "acknowledgments",
    "acknowledgements",
    "参考文献",
    "附录",
    "补充材料",
    "致谢",
}

STOP_SECTION_REASONS = {
    "references": "references",
    "bibliography": "references",
    "参考文献": "references",
    "appendix": "appendix",
    "appendices": "appendix",
    "supplementary material": "appendix",
    "附录": "appendix",
    "补充材料": "appendix",
    "acknowledgments": "acknowledgments",
    "acknowledgements": "acknowledgments",
    "致谢": "acknowledgments",
}


def match_section_heading(line: str) -> str | None:
    normalized = normalize_heading(line)
    if not normalized:
        return None
    if normalized in STOP_SECTION_ALIASES:
        return "stop"
    for section, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section
    return None


def stop_section_reason(line: str, *, allow_prefix: bool = False) -> str:
    normalized = normalize_heading(line)
    if not normalized:
        return ""
    reason = STOP_SECTION_REASONS.get(normalized, "")
    if reason or not allow_prefix:
        return reason
    if normalized.startswith(("references ", "bibliography ")):
        return "references"
    if normalized.startswith(("appendix ", "appendices ", "supplementary material ")):
        return "appendix"
    if normalized.startswith(("acknowledgments ", "acknowledgements ")):
        return "acknowledgments"
    return ""


def pdf_coverage_summary(pdf_path: Path, max_pages: int | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total_pages": None,
        "text_max_pages": max_pages,
        "text_pages_scanned": 0,
        "truncated_due_to_page_limit": False,
        "appendix_detected": False,
        "appendix_start_page": None,
        "references_start_page": None,
        "section_stop_reason": "",
        "section_stop_page": None,
    }
    if fitz is None or not pdf_path.is_file():
        return summary

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return summary

    try:
        total_pages = len(doc)
        page_limit = total_pages if max_pages is None else min(total_pages, max_pages)
        summary["total_pages"] = total_pages
        summary["text_pages_scanned"] = page_limit
        summary["truncated_due_to_page_limit"] = max_pages is not None and total_pages > max_pages

        for page_index in range(total_pages):
            page_number = page_index + 1
            text = doc[page_index].get_text("text")
            for raw_line in text.splitlines():
                line = clean_pdf_line(raw_line)
                if not line:
                    continue
                exact_reason = stop_section_reason(line)
                detected_reason = exact_reason or stop_section_reason(line, allow_prefix=True)
                if not detected_reason:
                    continue
                if detected_reason == "references" and summary["references_start_page"] is None:
                    summary["references_start_page"] = page_number
                if detected_reason == "appendix" and summary["appendix_start_page"] is None:
                    summary["appendix_start_page"] = page_number
                    summary["appendix_detected"] = True
                if exact_reason and not summary["section_stop_reason"]:
                    summary["section_stop_reason"] = exact_reason
                    summary["section_stop_page"] = page_number
                break
    finally:
        doc.close()
    return summary


def extract_appendix_page_texts(
    pdf_path: Path,
    appendix_start_page: int | None,
) -> list[dict[str, Any]]:
    if fitz is None or not pdf_path.is_file() or not appendix_start_page:
        return []

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    pages: list[dict[str, Any]] = []
    try:
        start_index = max(int(appendix_start_page) - 1, 0)
        for page_index in range(start_index, len(doc)):
            text = doc[page_index].get_text("text")
            cleaned = normalize_whitespace(text)
            if cleaned:
                pages.append({"page": page_index + 1, "text": text})
    finally:
        doc.close()
    return pages


def appendix_section_title(line: str) -> str:
    cleaned = clean_pdf_line(line)
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower in {"appendix", "appendices", "supplementary material"}:
        return ""
    if re.match(r"^fig(?:ure)?\.?\s*\d+", cleaned, re.IGNORECASE):
        return ""
    if re.match(r"^table\.?\s*\d+", cleaned, re.IGNORECASE):
        return ""
    if len(cleaned) > 120:
        return ""
    if re.match(r"^(?:appendix\s+)?[A-Z]\.?\s+.{3,}$", cleaned, re.IGNORECASE):
        return cleaned
    return ""


def extract_appendix_index(
    pdf_path: Path,
    pdf_coverage: dict[str, Any] | None = None,
    *,
    max_sections: int = 20,
    max_captions: int = 24,
) -> dict[str, Any]:
    pdf_coverage = pdf_coverage or {}
    start_page = pdf_coverage.get("appendix_start_page")
    index: dict[str, Any] = {
        "appendix_detected": bool(pdf_coverage.get("appendix_detected")),
        "start_page": start_page,
        "sections": [],
        "figure_captions": [],
        "table_captions": [],
    }
    if not index["appendix_detected"] or not start_page:
        return index

    seen_sections = set()
    seen_figure_captions = set()
    seen_table_captions = set()
    for page in extract_appendix_page_texts(pdf_path, int(start_page)):
        page_number = int(page.get("page", 0) or 0)
        text = str(page.get("text", ""))
        for raw_line in text.splitlines():
            title = appendix_section_title(raw_line)
            marker = normalize_title(title)
            if title and marker not in seen_sections and len(index["sections"]) < max_sections:
                seen_sections.add(marker)
                index["sections"].append({"title": title, "page": page_number})

        for caption in extract_caption_lines(text, "figure"):
            marker = f"{caption.get('id', '').lower()}::{caption.get('caption', '').lower()}"
            if marker in seen_figure_captions or len(index["figure_captions"]) >= max_captions:
                continue
            seen_figure_captions.add(marker)
            index["figure_captions"].append({**caption, "page_hint": f"p.{page_number}"})

        for caption in extract_caption_lines(text, "table"):
            marker = f"{caption.get('id', '').lower()}::{caption.get('caption', '').lower()}"
            if marker in seen_table_captions or len(index["table_captions"]) >= max_captions:
                continue
            seen_table_captions.add(marker)
            index["table_captions"].append({**caption, "page_hint": f"p.{page_number}"})
    return index


def extract_pdf_sections(pdf_path: Path, max_pages: int | None = None) -> dict[str, str]:
    if fitz is None:
        return {}
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    doc = fitz.open(pdf_path)
    try:
        page_limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        for page_index in range(page_limit):
            text = doc[page_index].get_text("text")
            reached_stop = False
            for raw_line in text.splitlines():
                line = clean_pdf_line(raw_line)
                if not line:
                    continue
                heading = match_section_heading(line)
                if heading == "stop":
                    reached_stop = True
                    break
                if heading:
                    current = heading
                    sections.setdefault(current, [])
                    continue
                sections.setdefault(current, []).append(line)
            if reached_stop:
                break
    finally:
        doc.close()

    collapsed = {}
    for key, value in sections.items():
        if not value:
            continue
        text = re.sub(r"\s+", " ", " ".join(value)).strip()
        if text:
            collapsed[key] = text
    return collapsed


def extract_pdf_text(pdf_path: Path, max_pages: int | None = None) -> str:
    if fitz is None:
        return ""
    doc = fitz.open(pdf_path)
    try:
        page_limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        texts = [doc[i].get_text("text") for i in range(page_limit)]
    finally:
        doc.close()
    return "\n".join(texts)


def normalize_caption_label(label: str) -> str:
    label = normalize_whitespace(unicodedata.normalize("NFKC", label))
    chinese_match = re.match(r"^(图|表)\s*([A-Z]?\d+[a-z]?)$", label, re.IGNORECASE)
    if chinese_match:
        return f"{chinese_match.group(1)} {chinese_match.group(2)}"
    extended_figure_match = re.match(
        r"^extended\s+data\s+fig(?:ure)?\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if extended_figure_match:
        return f"Extended Data Fig {extended_figure_match.group(1)}"
    extended_table_match = re.match(
        r"^extended\s+data\s+table\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if extended_table_match:
        return f"Extended Data Table {extended_table_match.group(1)}"
    scheme_match = re.match(r"^(scheme|algorithm)\.?\s*(\d+[a-z]?)$", label, re.IGNORECASE)
    if scheme_match:
        return f"{scheme_match.group(1).capitalize()} {scheme_match.group(2)}"
    supplementary_match = re.match(
        r"^(supplementary)\s+(fig(?:ure)?|table)\.?\s*(\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if supplementary_match:
        return f"{supplementary_match.group(1)} {supplementary_match.group(2)} {supplementary_match.group(3)}"
    english_match = re.match(
        r"^(fig(?:ure)?|table)\.?\s*([AS]?\d+[a-z]?)$",
        label,
        re.IGNORECASE,
    )
    if english_match:
        return f"{english_match.group(1)} {english_match.group(2)}"
    return label


CAPTION_REFERENCE_VERBS = {
    "show",
    "shows",
    "illustrate",
    "illustrates",
    "plot",
    "plots",
    "present",
    "presents",
    "report",
    "reports",
    "depict",
    "depicts",
    "compare",
    "compares",
    "summarize",
    "summarizes",
    "demonstrate",
    "demonstrates",
}


def caption_label_key(label: str) -> str:
    normalized = normalize_caption_label(label).lower()
    normalized = re.sub(r"\bfigure\b", "fig", normalized)
    normalized = re.sub(r"\bfig\.\s*", "fig ", normalized)
    normalized = re.sub(r"\btable\.\s*", "table ", normalized)
    return normalize_whitespace(normalized)


def caption_preference_score(label: str, caption: str) -> int:
    cleaned_caption = normalize_whitespace(caption)
    lowered_label = normalize_whitespace(label).lower()
    first_word_match = re.match(r"^([A-Za-z][A-Za-z-]*)\b", cleaned_caption)
    first_word = first_word_match.group(1).lower() if first_word_match else ""
    score = len(cleaned_caption)
    if lowered_label.startswith(("figure", "table")):
        score += 25
    if first_word in CAPTION_REFERENCE_VERBS or cleaned_caption[:1].islower():
        score -= 80
    if len(cleaned_caption) < 12:
        score -= 20
    return score


def extract_caption_lines(pdf_text: str, kind: str) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    scores: dict[str, int] = {}
    order: list[str] = []
    lines = [clean_pdf_line(line) for line in pdf_text.splitlines()]
    if kind == "figure":
        pattern = re.compile(
            r"^((?:"
            r"supplementary\s+fig(?:ure)?\.?\s*\d+[a-z]?"
            r"|extended\s+data\s+fig(?:ure)?\.?\s*\d+[a-z]?"
            r"|scheme\.?\s*\d+[a-z]?"
            r"|algorithm\.?\s*\d+[a-z]?"
            r"|fig(?:ure)?\.?\s*[AS]?\d+[a-z]?"
            r"|图\.?\s*[A-Z]?\d+[a-z]?"
            r"))(?!\.\d)(?:[:：.。,\s、|—–-]+|$)(.*)$",
            re.IGNORECASE,
        )
    else:
        pattern = re.compile(
            r"^((?:"
            r"supplementary\s+table\.?\s*\d+[a-z]?"
            r"|extended\s+data\s+table\.?\s*\d+[a-z]?"
            r"|table\.?\s*[AS]?\d+[a-z]?"
            r"|表\.?\s*[A-Z]?\d+[a-z]?"
            r"))(?!\.\d)(?:[:：.。,\s、|—–-]+|$)(.*)$",
            re.IGNORECASE,
        )
    for idx, line in enumerate(lines):
        if not line:
            continue
        match = pattern.match(line)
        if not match:
            continue
        label = normalize_caption_label(match.group(1))
        caption = normalize_whitespace(match.group(2))
        if not caption and idx + 1 < len(lines):
            caption = normalize_whitespace(lines[idx + 1])
        key = caption_label_key(label)
        if not key:
            continue
        candidate = {"id": label, "caption": caption}
        score = caption_preference_score(label, caption)
        if key not in grouped:
            grouped[key] = candidate
            scores[key] = score
            order.append(key)
            continue
        if score > scores[key]:
            grouped[key] = candidate
            scores[key] = score
    return [grouped[key] for key in order]
