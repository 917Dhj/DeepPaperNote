#!/usr/bin/env python3
"""Extract a richer evidence pack from PDF or full text, including candidate chunks and captions."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import (
    emit,
    enrich_metadata,
    extract_caption_lines,
    extract_dataset_candidates,
    extract_mechanism_flow_sentences,
    extract_metric_claims,
    extract_negative_claims,
    extract_pdf_sections,
    extract_pdf_text,
    infer_paper_type,
    maybe_load_json_record,
    normalize_whitespace,
    paper_id_for_record,
    pick_sentences_by_keywords,
    resolve_reference,
    split_sentences,
)
from contracts import empty_evidence_pack


CORE_SECTIONS = ("introduction", "method", "experiment")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract evidence")
    p.add_argument("--input", required=True, help="Metadata JSON path, fetch_pdf JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id if already known.")
    p.add_argument("--max-pages", type=int, default=18, help="Maximum number of PDF pages to scan.")
    p.add_argument("--max-chunks-per-section", type=int, default=12, help="Maximum number of candidate chunks to keep per section.")
    return p


def ensure_record(input_value: str) -> dict:
    record = maybe_load_json_record(input_value)
    if record is not None:
        return dict(record)
    return enrich_metadata(resolve_reference(input_value))


def build_items(sentences: list[str], section: str) -> list[dict]:
    items = []
    for sentence in sentences:
        cleaned = normalize_whitespace(sentence)
        if not cleaned:
            continue
        items.append(
            {
                "claim": cleaned,
                "evidence": cleaned,
                "source_section": section,
                "page_hint": "",
            }
        )
    return items


def language_hint_for_text(text: str) -> str:
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", text or ""))
    latin_chars = len(re.findall(r"[A-Za-z]", text or ""))
    total = cjk_chars + latin_chars
    if total == 0:
        return "unknown"
    cjk_ratio = cjk_chars / total
    latin_ratio = latin_chars / total
    if cjk_ratio >= 0.6:
        return "zh"
    if latin_ratio >= 0.6:
        return "en"
    return "mixed"


def section_text_with_source(
    section_map: dict[str, str],
    section: str,
    fallback: str = "",
) -> tuple[str, str]:
    text = section_map.get(section, "")
    if text:
        return text, section
    if fallback:
        return fallback, "abstract"
    return "", ""


def build_section_extraction_coverage(
    section_map: dict[str, str],
    section_sources: dict[str, str],
) -> dict:
    core_sections_found = [section for section in CORE_SECTIONS if section_map.get(section)]
    missing_core_sections = [section for section in CORE_SECTIONS if section not in core_sections_found]
    fallback_sections = [
        section
        for section, source in section_sources.items()
        if section != "abstract" and source == "abstract"
    ]
    if len(core_sections_found) >= len(CORE_SECTIONS):
        coverage_status = "good"
    elif core_sections_found:
        coverage_status = "partial"
    else:
        coverage_status = "poor"
    return {
        "coverage_status": coverage_status,
        "recognized_sections": list(section_map.keys()),
        "core_sections_found": core_sections_found,
        "missing_core_sections": missing_core_sections,
        "section_text_chars": {
            section: len(normalize_whitespace(text))
            for section, text in section_map.items()
            if normalize_whitespace(text)
        },
        "fallback_sections": fallback_sections,
    }


def text_chunks(
    text: str,
    *,
    section: str,
    kind_hint: str = "",
    actual_source_section: str = "",
    is_abstract_fallback: bool = False,
    max_chunks: int = 12,
    sentences_per_chunk: int = 2,
    max_chars: int = 520,
) -> list[dict]:
    sentences = split_sentences(text)
    chunks: list[dict] = []
    seen = set()
    for idx in range(0, len(sentences), sentences_per_chunk):
        group = sentences[idx : idx + sentences_per_chunk]
        if not group:
            continue
        chunk = normalize_whitespace(" ".join(group))
        if not chunk:
            continue
        if len(chunk) > max_chars:
            chunk = chunk[: max_chars - 3].rstrip(" ,;:") + "..."
        marker = chunk.lower()
        if marker in seen:
            continue
        seen.add(marker)
        item = {
            "text": chunk,
            "source_section": section,
            "page_hint": "",
            "kind_hint": kind_hint,
            "actual_source_section": actual_source_section or section,
        }
        if is_abstract_fallback:
            item["is_abstract_fallback"] = True
        chunks.append(item)
        if len(chunks) >= max_chunks:
            break
    return chunks


def first_chunks(chunks: list[dict], limit: int) -> list[dict]:
    return [
        {
            "claim": normalize_whitespace(str(item.get("text", ""))),
            "evidence": normalize_whitespace(str(item.get("text", ""))),
            "source_section": normalize_whitespace(str(item.get("source_section", ""))),
            "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
        }
        for item in chunks[:limit]
        if normalize_whitespace(str(item.get("text", "")))
    ]


def keyword_chunks(
    text: str,
    keywords: list[str],
    *,
    section: str,
    max_chunks: int = 6,
) -> list[dict]:
    picked = pick_sentences_by_keywords(text, keywords, limit=max_chunks)
    return text_chunks(
        " ".join(picked),
        section=section,
        kind_hint=section,
        max_chunks=max_chunks,
        sentences_per_chunk=1,
    )


def candidate_map(
    *,
    abstract: str,
    intro_text: str,
    method_text: str,
    experiment_text: str,
    conclusion_text: str,
    data_text: str,
    section_sources: dict[str, str],
    max_chunks_per_section: int,
) -> dict[str, list[dict]]:
    combined_general = " ".join(
        part
        for part in [abstract, intro_text, method_text, experiment_text, conclusion_text]
        if part
    )
    return {
        "abstract": text_chunks(
            abstract,
            section="abstract",
            kind_hint="abstract",
            actual_source_section="abstract",
            max_chunks=max_chunks_per_section,
        ),
        "introduction": text_chunks(
            intro_text,
            section="introduction",
            kind_hint="problem",
            actual_source_section=section_sources.get("introduction", "introduction"),
            is_abstract_fallback=section_sources.get("introduction") == "abstract",
            max_chunks=max_chunks_per_section,
        ),
        "method": text_chunks(
            method_text,
            section="method",
            kind_hint="method",
            actual_source_section=section_sources.get("method", "method"),
            is_abstract_fallback=section_sources.get("method") == "abstract",
            max_chunks=max_chunks_per_section,
        ),
        "experiment": text_chunks(
            experiment_text,
            section="experiment",
            kind_hint="results",
            actual_source_section=section_sources.get("experiment", "experiment"),
            is_abstract_fallback=section_sources.get("experiment") == "abstract",
            max_chunks=max_chunks_per_section,
        ),
        "conclusion": text_chunks(
            conclusion_text,
            section="conclusion",
            kind_hint="limitations",
            actual_source_section=section_sources.get("conclusion", "conclusion"),
            is_abstract_fallback=section_sources.get("conclusion") == "abstract",
            max_chunks=max_chunks_per_section,
        ),
        "data": text_chunks(
            data_text,
            section="data",
            kind_hint="data",
            actual_source_section=section_sources.get("data", "mixed"),
            max_chunks=max_chunks_per_section,
        ),
        "general": text_chunks(
            combined_general,
            section="general",
            kind_hint="general",
            actual_source_section="mixed",
            max_chunks=max_chunks_per_section,
        ),
    }


def extract_equation_candidates(*, full_text: str, method_text: str, experiment_text: str, conclusion_text: str, limit: int = 8) -> list[dict]:
    candidates: list[dict] = []
    seen = set()

    def add_candidate(text: str, section: str, kind_hint: str) -> None:
        cleaned = normalize_whitespace(text)
        if not cleaned or len(cleaned) < 6:
            return
        marker = cleaned.lower()
        if marker in seen:
            return
        seen.add(marker)
        candidates.append(
            {
                "equation": cleaned,
                "source_section": section,
                "kind_hint": kind_hint,
            }
        )

    math_like_patterns = [
        (r"O\([^)]*\)", "method", "complexity"),
        (r"\bp\([^)]*\)\s*=\s*[^.]{1,120}", "method", "objective"),
        (r"\b(?:L|Loss|Err|ELBO|FID|IS|NLL)[A-Za-z0-9_]*\s*=\s*[^.]{1,120}", "experiment", "metric_equation"),
        (r"[A-Za-z][A-Za-z0-9_]*\s*=\s*\([^)]*\)\s*\^[^\s,.;]+", "experiment", "scaling_law"),
        (r"[A-Za-z][A-Za-z0-9_]*\s*=\s*[^.]{1,100}", "method", "equation"),
    ]

    for pattern, section, kind_hint in math_like_patterns:
        for match in re.finditer(pattern, full_text or ""):
            add_candidate(match.group(0), section, kind_hint)
            if len(candidates) >= limit:
                return candidates

    equation_sentences = pick_sentences_by_keywords(
        " ".join(part for part in [method_text, experiment_text, conclusion_text] if part),
        [
            "objective",
            "loss",
            "likelihood",
            "probability",
            "optimiz",
            "maximize",
            "minimize",
            "complexity",
            "scaling law",
            "equation",
        ],
        limit=limit,
    )
    for sentence in equation_sentences:
        section = "method"
        lower = sentence.lower()
        if "scaling" in lower or "loss" in lower or "err" in lower:
            section = "experiment"
        add_candidate(sentence, section, "formula_context")
        if len(candidates) >= limit:
            break

    return candidates[:limit]


def evidence_quality(pack: dict) -> str:
    score = 0
    core_score = 0
    candidate_chunks = pack.get("candidate_chunks", {}) or {}
    coverage = pack.get("section_extraction_coverage", {}) or {}
    core_sections_found = coverage.get("core_sections_found", []) if isinstance(coverage, dict) else []
    if core_sections_found:
        core_score = len([section for section in CORE_SECTIONS if section in core_sections_found])
    else:
        for section in CORE_SECTIONS:
            chunks = candidate_chunks.get(section, []) or []
            if any(
                isinstance(chunk, dict)
                and not chunk.get("is_abstract_fallback")
                and chunk.get("actual_source_section", section) != "abstract"
                for chunk in chunks
            ):
                core_score += 1
    score += core_score
    if pack.get("equation_candidates"):
        score += 1
    if pack.get("figure_captions"):
        score += 1
    if pack.get("table_captions"):
        score += 1
    if core_score == 0:
        return "low"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def main() -> None:
    args = parser().parse_args()
    record = ensure_record(args.input)
    pdf_path = Path(str(record.get("pdf_path", "")).strip()).expanduser()

    if not pdf_path.exists():
        from_fetch = maybe_load_json_record(args.input) or {}
        pdf_candidate = str(from_fetch.get("pdf_path", "")).strip()
        if pdf_candidate:
            pdf_path = Path(pdf_candidate).expanduser()

    section_map: dict[str, str] = {}
    full_text = ""
    extraction_failures: list[str] = []
    if pdf_path.exists():
        try:
            section_map = extract_pdf_sections(pdf_path.resolve(), max_pages=args.max_pages)
            full_text = extract_pdf_text(pdf_path.resolve(), max_pages=args.max_pages)
        except Exception as exc:
            extraction_failures.append(f"pdf_parse_failed: {exc}")
    else:
        extraction_failures.append("pdf_missing")

    paper_type, paper_type_rationale = infer_paper_type(record.get("title", ""), record.get("abstract", ""))

    metadata_abstract = normalize_whitespace(str(record.get("abstract", "")).strip())
    abstract = metadata_abstract or normalize_whitespace(section_map.get("abstract", ""))
    intro_text, intro_source = section_text_with_source(section_map, "introduction", abstract)
    method_text, method_source = section_text_with_source(section_map, "method", abstract)
    if section_map.get("experiment"):
        experiment_text = section_map["experiment"]
        experiment_source = "experiment"
    elif section_map.get("conclusion"):
        experiment_text = section_map["conclusion"]
        experiment_source = "conclusion"
    else:
        experiment_text = abstract
        experiment_source = "abstract" if abstract else ""
    conclusion_text, conclusion_source = section_text_with_source(section_map, "conclusion", abstract)
    figure_captions = extract_caption_lines(full_text, "figure")[:12] if full_text else []
    mechanism_caption_text = " ".join(
        item.get("caption", "")
        for item in figure_captions
        if isinstance(item, dict)
        and any(token in str(item.get("caption", "")).lower() for token in ["pipeline", "framework", "overview", "architecture", "system", "workflow", "stage"])
    )
    data_text = " ".join(
        part
        for part in [
            section_map.get("abstract", ""),
            section_map.get("introduction", ""),
            section_map.get("method", ""),
            section_map.get("data", ""),
            section_map.get("experiment", ""),
        ]
        if part
    )
    section_sources = {
        "abstract": "abstract",
        "introduction": intro_source,
        "method": method_source,
        "experiment": experiment_source,
        "conclusion": conclusion_source,
        "data": "data" if section_map.get("data") else "mixed",
    }
    section_extraction_coverage = build_section_extraction_coverage(section_map, section_sources)
    if (
        section_extraction_coverage["coverage_status"] == "poor"
        and "section_coverage_poor" not in extraction_failures
    ):
        extraction_failures.append("section_coverage_poor")

    candidates = candidate_map(
        abstract=abstract,
        intro_text=intro_text,
        method_text=method_text,
        experiment_text=experiment_text,
        conclusion_text=conclusion_text,
        data_text=data_text,
        section_sources=section_sources,
        max_chunks_per_section=args.max_chunks_per_section,
    )

    problem_sentences = pick_sentences_by_keywords(
        intro_text or abstract,
        ["we address", "we investigate", "we study", "challenge", "problem", "aim", "objective", "however"],
        limit=4,
    ) or split_sentences(intro_text or abstract)[:3]
    task_sentences = pick_sentences_by_keywords(
        " ".join([abstract, intro_text, method_text]),
        ["task", "predict", "classification", "identify", "detect", "estimate", "evaluate", "diagnos", "screen"],
        limit=5,
    ) or [chunk["text"] for chunk in candidates.get("introduction", [])[:3]]
    data_sentences = pick_sentences_by_keywords(
        data_text,
        ["dataset", "datasets", "participants", "patients", "outpatients", "interviews", "corpus", "recordings", "collected"],
        limit=5,
    ) or [chunk["text"] for chunk in candidates.get("data", [])[:3]]
    method_sentences = pick_sentences_by_keywords(
        method_text,
        ["we propose", "we present", "we introduce", "framework", "pipeline", "model", "method", "feature", "classifier", "fine-tun", "zero-shot"],
        limit=6,
    ) or [chunk["text"] for chunk in candidates.get("method", [])[:4]]
    mechanism_sentences = extract_mechanism_flow_sentences(
        " ".join(part for part in [method_text, mechanism_caption_text] if part),
        limit=6,
    ) or method_sentences[:4]
    result_sentences = extract_metric_claims(experiment_text) or pick_sentences_by_keywords(
        experiment_text,
        ["outperform", "improve", "accuracy", "f1", "auc", "auprc", "score", "results show", "achieved"],
        limit=6,
    ) or [chunk["text"] for chunk in candidates.get("experiment", [])[:4]]
    ablation_sentences = extract_negative_claims(" ".join(part for part in [experiment_text, conclusion_text] if part), limit=6)
    limitation_sentences = pick_sentences_by_keywords(
        conclusion_text,
        ["limitation", "future work", "however", "remain", "generaliz", "need", "further"],
        limit=4,
    ) or [chunk["text"] for chunk in candidates.get("conclusion", [])[:3]]

    pack = empty_evidence_pack()
    pack["paper_id"] = args.paper_id or record.get("paper_id") or paper_id_for_record(record)
    pack["problem_evidence"] = build_items(problem_sentences, "introduction")
    pack["task_evidence"] = build_items(task_sentences, "task")
    pack["data_evidence"] = build_items(data_sentences, "data")
    pack["method_evidence"] = build_items(method_sentences, "method")
    pack["mechanism_evidence"] = build_items(mechanism_sentences, "method")
    pack["results_evidence"] = build_items(result_sentences, "experiment")
    pack["ablation_evidence"] = build_items(ablation_sentences, "experiment")
    pack["limitations_evidence"] = build_items(limitation_sentences, "conclusion")
    pack["equation_candidates"] = extract_equation_candidates(
        full_text=full_text,
        method_text=method_text,
        experiment_text=experiment_text,
        conclusion_text=conclusion_text,
    )
    pack["candidate_chunks"] = candidates
    pack["language_hint"] = language_hint_for_text(
        " ".join(part for part in [full_text, abstract] if part)
    )
    pack["section_sources"] = section_sources
    pack["section_extraction_coverage"] = section_extraction_coverage
    pack["section_texts"] = {
        key: normalize_whitespace(value)
        for key, value in section_map.items()
        if normalize_whitespace(value)
    }
    pack["figure_captions"] = figure_captions
    pack["table_captions"] = extract_caption_lines(full_text, "table")[:12] if full_text else []
    pack["sections"] = [
        {"name": key, "length": len(value), "preview": value[:240]}
        for key, value in section_map.items()
    ]
    pack["quotes"] = []
    pack["extraction_failures"] = extraction_failures
    pack["evidence_quality"] = evidence_quality(pack)

    payload = {
        "status": "ok",
        "script": "extract_evidence.py",
        "paper_id": pack["paper_id"],
        "title": record.get("title", ""),
        "evidence_pack": pack,
        "summary": {
            "paper_type": paper_type,
            "paper_type_rationale": paper_type_rationale,
            "datasets": extract_dataset_candidates(data_text)[:8],
            "metrics": extract_metric_claims(experiment_text)[:8],
            "mechanism_signals": mechanism_sentences[:6],
            "ablation_signals": ablation_sentences[:6],
            "equation_candidates": pack["equation_candidates"][:6],
            "section_keys": list(section_map.keys()),
            "language_hint": pack["language_hint"],
            "section_coverage_status": section_extraction_coverage["coverage_status"],
            "fallback_sections": section_extraction_coverage["fallback_sections"],
            "pdf_used": bool(pdf_path.exists()),
            "candidate_chunk_sections": sorted([key for key, value in candidates.items() if value]),
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
