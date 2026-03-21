#!/usr/bin/env python3
"""Extract an evidence pack from PDF or full text, including figure and table captions."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    emit,
    enrich_metadata,
    extract_caption_lines,
    extract_dataset_candidates,
    extract_metric_claims,
    extract_pdf_sections,
    extract_pdf_text,
    maybe_load_json_record,
    paper_id_for_record,
    pick_sentences_by_keywords,
    resolve_reference,
    split_sentences,
)
from contracts import empty_evidence_pack


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract evidence")
    p.add_argument("--input", required=True, help="Metadata JSON path, fetch_pdf JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id if already known.")
    p.add_argument("--max-pages", type=int, default=18, help="Maximum number of PDF pages to scan.")
    return p


def ensure_record(input_value: str) -> dict:
    record = maybe_load_json_record(input_value)
    if record is not None:
        return dict(record)
    return enrich_metadata(resolve_reference(input_value))


def build_items(sentences: list[str], section: str) -> list[dict]:
    items = []
    for sentence in sentences:
        cleaned = " ".join(sentence.split())
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


def evidence_quality(pack: dict) -> str:
    score = 0
    if pack.get("method_evidence"):
        score += 1
    if pack.get("results_evidence"):
        score += 1
    if pack.get("task_evidence"):
        score += 1
    if pack.get("figure_captions"):
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def main() -> None:
    args = parser().parse_args()
    record = ensure_record(args.input)
    pdf_path = Path(str(record.get("pdf_path", "")).strip()).expanduser()

    if not pdf_path.exists():
        # Support fetch_pdf output or metadata record without embedded path.
        from_fetch = maybe_load_json_record(args.input) or {}
        pdf_candidate = str(from_fetch.get("pdf_path", "")).strip()
        if pdf_candidate:
            pdf_path = Path(pdf_candidate).expanduser()

    section_map = {}
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

    abstract = str(record.get("abstract", "")).strip()
    intro_text = section_map.get("introduction", "") or abstract
    method_text = section_map.get("method", "") or abstract
    experiment_text = section_map.get("experiment", "") or section_map.get("conclusion", "") or abstract
    conclusion_text = section_map.get("conclusion", "") or abstract
    data_text = " ".join(
        part for part in [section_map.get("abstract", ""), section_map.get("introduction", ""), section_map.get("method", ""), section_map.get("experiment", "")]
        if part
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
    )
    data_sentences = pick_sentences_by_keywords(
        data_text,
        ["dataset", "datasets", "participants", "patients", "outpatients", "interviews", "corpus", "recordings", "collected"],
        limit=5,
    )
    method_sentences = pick_sentences_by_keywords(
        method_text,
        ["we propose", "we present", "we introduce", "framework", "pipeline", "model", "method", "feature", "classifier", "fine-tun", "zero-shot"],
        limit=6,
    ) or pick_sentences_by_keywords(
        " ".join([intro_text, abstract]),
        ["we present", "we introduce", "model", "architecture", "training", "infrastructure"],
        limit=5,
    ) or split_sentences(method_text)[:5]
    result_sentences = extract_metric_claims(experiment_text) or pick_sentences_by_keywords(
        experiment_text,
        ["outperform", "improve", "accuracy", "f1", "auc", "auprc", "score", "results show", "achieved"],
        limit=6,
    ) or pick_sentences_by_keywords(
        " ".join([intro_text, abstract]),
        ["outperform", "improve", "accuracy", "score", "recall", "achieve", "%"],
        limit=5,
    )
    limitation_sentences = pick_sentences_by_keywords(
        conclusion_text,
        ["limitation", "future work", "however", "remain", "generaliz", "need", "further"],
        limit=4,
    )

    pack = empty_evidence_pack()
    pack["paper_id"] = args.paper_id or record.get("paper_id") or paper_id_for_record(record)
    pack["problem_evidence"] = build_items(problem_sentences, "introduction")
    pack["task_evidence"] = build_items(task_sentences, "task")
    pack["data_evidence"] = build_items(data_sentences, "data")
    pack["method_evidence"] = build_items(method_sentences, "method")
    pack["results_evidence"] = build_items(result_sentences, "experiment")
    pack["limitations_evidence"] = build_items(limitation_sentences, "conclusion")
    pack["figure_captions"] = extract_caption_lines(full_text, "figure")[:12] if full_text else []
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
            "datasets": extract_dataset_candidates(data_text)[:6],
            "metrics": extract_metric_claims(experiment_text)[:6],
            "section_keys": list(section_map.keys()),
            "pdf_used": bool(pdf_path.exists()),
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
