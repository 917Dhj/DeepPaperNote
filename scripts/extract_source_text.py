#!/usr/bin/env python3
"""Extract canonical raw source text and a compact source manifest from a PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common import (
    clean_pdf_line,
    emit,
    enrich_metadata,
    ensure_parent,
    extract_appendix_index,
    extract_caption_lines,
    fitz,
    match_section_heading,
    maybe_load_json_record,
    normalize_heading,
    normalize_whitespace,
    paper_id_for_record,
    pdf_coverage_summary,
    resolve_reference,
    stop_section_reason,
)

MATH_SIGNAL_RE = re.compile(
    r"(?:\\(?:frac|sum|log|exp|argmax|argmin|mathbb|mathbf)|[$=]|[<>]=?|[∑∏≤≥≈∈]|O\([^)]+\))"
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract source text")
    p.add_argument(
        "--input",
        required=True,
        help="Fetch JSON path, metadata JSON path, local PDF path, JSON string, or reference.",
    )
    p.add_argument("--output", default="", help="Source manifest JSON output path.")
    p.add_argument(
        "--raw-sections-output",
        default="",
        help="Canonical raw sections JSONL output path.",
    )
    p.add_argument("--full-text-output", default="", help="Optional derived Markdown output path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id if already known.")
    p.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional page limit. Omit for all pages.",
    )
    return p


def ensure_record(input_value: str) -> dict[str, Any]:
    record = maybe_load_json_record(input_value)
    if record is not None:
        return dict(record)
    path = Path(input_value).expanduser()
    if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
        return {
            "paper_id": f"local:{path.stem}",
            "title": path.stem,
            "pdf_path": str(path.resolve()),
            "source_type": "local_pdf",
        }
    return enrich_metadata(resolve_reference(input_value))


def resolve_pdf_path(record: dict[str, Any]) -> Path | None:
    for key in ("pdf_path", "local_pdf_path"):
        value = normalize_whitespace(str(record.get(key, "")))
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def section_id(base: str, seen: dict[str, int]) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", normalize_heading(base)).strip("-") or "section"
    seen[safe] = seen.get(safe, 0) + 1
    suffix = "" if seen[safe] == 1 else f"-{seen[safe]}"
    return f"sec:{safe}{suffix}"


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def language_hint_for_text(text: str) -> str:
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", text or ""))
    latin_chars = len(re.findall(r"[A-Za-z]", text or ""))
    total = cjk_chars + latin_chars
    if total == 0:
        return "unknown"
    if cjk_chars / total >= 0.6:
        return "zh"
    if latin_chars / total >= 0.6:
        return "en"
    return "mixed"


def new_record(kind: str, title: str, page_number: int, seen: dict[str, int]) -> dict[str, Any]:
    sid = section_id(title or kind, seen)
    return {
        "record_type": "section",
        "section_id": sid,
        "kind": kind,
        "title": normalize_whitespace(title) or kind,
        "page_start": page_number,
        "page_end": page_number,
        "_lines": [],
    }


def finalize_section(record: dict[str, Any]) -> dict[str, Any] | None:
    lines = [line for line in record.pop("_lines", []) if normalize_whitespace(str(line))]
    text = "\n".join(lines).strip()
    if not text:
        return None
    record["text"] = text
    record["char_count"] = len(text)
    record["text_hash_sha256"] = text_hash(text)
    return record


def extract_page_texts(pdf_path: Path, max_pages: int | None) -> list[dict[str, Any]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for source text extraction.")
    doc = fitz.open(pdf_path)
    try:
        page_limit = len(doc) if max_pages is None else min(len(doc), max_pages)
        return [
            {"page": page_index + 1, "text": doc[page_index].get_text("text")}
            for page_index in range(page_limit)
        ]
    finally:
        doc.close()


def extract_raw_sections(page_texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for page in page_texts:
        page_number = int(page["page"])
        if current is None:
            current = new_record("preamble", "preamble", page_number, seen)
        current["page_end"] = page_number

        for raw_line in str(page.get("text", "")).splitlines():
            line = clean_pdf_line(raw_line)
            if not line:
                continue
            stop_reason = stop_section_reason(line, allow_prefix=True)
            heading = match_section_heading(line)
            if stop_reason or (heading and heading != "stop"):
                finalized = finalize_section(current)
                if finalized is not None:
                    sections.append(finalized)
                kind = stop_reason or str(heading)
                current = new_record(kind, line, page_number, seen)
                continue
            current.setdefault("_lines", []).append(line)

    if current is not None:
        finalized = finalize_section(current)
        if finalized is not None:
            sections.append(finalized)
    return sections


def section_ids_for_page(sections: list[dict[str, Any]], page_number: int) -> list[str]:
    ids = [
        str(section.get("section_id", ""))
        for section in sections
        if int(section.get("page_start", 0) or 0)
        <= page_number
        <= int(section.get("page_end", 0) or 0)
    ]
    return [sid for sid in ids if sid]


def build_pages(
    page_texts: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in page_texts:
        page_number = int(page["page"])
        text = str(page.get("text", ""))
        pages.append(
            {
                "page": page_number,
                "char_count": len(normalize_whitespace(text)),
                "section_ids": section_ids_for_page(sections, page_number),
            }
        )
    return pages


def primary_section_for_page(sections: list[dict[str, Any]], page_number: int) -> str:
    ids = section_ids_for_page(sections, page_number)
    return ids[0] if ids else ""


def caption_manifest(
    page_texts: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    captions = {"figures": [], "tables": []}
    for page in page_texts:
        page_number = int(page["page"])
        section = primary_section_for_page(sections, page_number)
        for key, kind in (("figures", "figure"), ("tables", "table")):
            for item in extract_caption_lines(str(page.get("text", "")), kind):
                captions[key].append(
                    {
                        **item,
                        "page": page_number,
                        "pages": [page_number],
                        "section_id": section,
                    }
                )
    return captions


def math_index(sections: list[dict[str, Any]], *, max_items: int = 200) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in sections:
        for line in str(section.get("text", "")).splitlines():
            cleaned = normalize_whitespace(line)
            if not cleaned or len(cleaned) > 240 or not MATH_SIGNAL_RE.search(cleaned):
                continue
            items.append(
                {
                    "text": cleaned,
                    "section_id": section.get("section_id", ""),
                    "page_start": section.get("page_start"),
                    "page_end": section.get("page_end"),
                }
            )
            if len(items) >= max_items:
                return items
    return items


def write_jsonl(records: list[dict[str, Any]], output_path: str) -> None:
    ensure_parent(output_path)
    path = Path(output_path).expanduser().resolve()
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def write_full_text_markdown(records: list[dict[str, Any]], output_path: str, title: str) -> None:
    ensure_parent(output_path)
    lines = [f"# {title or 'Full Source Text'}", ""]
    for record in records:
        lines.extend(
            [
                f"## {record.get('section_id', '')} {record.get('title', '')}".strip(),
                f"_Pages {record.get('page_start')}-{record.get('page_end')}_",
                "",
                str(record.get("text", "")).strip(),
                "",
            ]
        )
    Path(output_path).expanduser().resolve().write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def build_manifest(
    *,
    record: dict[str, Any],
    pdf_path: Path,
    page_texts: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    raw_sections_output: str,
    full_text_output: str,
    max_pages: int | None,
) -> dict[str, Any]:
    coverage = pdf_coverage_summary(pdf_path, max_pages=max_pages)
    total_pages = coverage.get("total_pages")
    extracted_pages = len(page_texts)
    full_text = "\n".join(str(page.get("text", "")) for page in page_texts)
    source_coverage = {
        "total_pages": total_pages,
        "text_max_pages": max_pages,
        "text_pages_extracted": extracted_pages,
        "text_pages_scanned": extracted_pages,
        "text_truncated": bool(coverage.get("truncated_due_to_page_limit")),
        "truncated_due_to_page_limit": bool(coverage.get("truncated_due_to_page_limit")),
        "appendix_detected": bool(coverage.get("appendix_detected")),
        "appendix_start_page": coverage.get("appendix_start_page"),
        "references_start_page": coverage.get("references_start_page"),
    }
    return {
        "status": "ok",
        "script": "extract_source_text.py",
        "schema_version": 1,
        "paper_id": record.get("paper_id") or paper_id_for_record(record),
        "title": record.get("title", ""),
        "source_kind": "pdf_text",
        "raw_sections_path": (
            str(Path(raw_sections_output).expanduser().resolve()) if raw_sections_output else ""
        ),
        "full_text_md_path": (
            str(Path(full_text_output).expanduser().resolve()) if full_text_output else ""
        ),
        "pdf": {
            "path": str(pdf_path),
            "total_pages": total_pages,
            "text_pages_extracted": extracted_pages,
            "text_max_pages": max_pages,
            "text_truncated": bool(coverage.get("truncated_due_to_page_limit")),
        },
        "coverage": source_coverage,
        "sections": [
            {
                key: section.get(key)
                for key in (
                    "section_id",
                    "kind",
                    "title",
                    "page_start",
                    "page_end",
                    "char_count",
                    "text_hash_sha256",
                )
            }
            for section in sections
        ],
        "pages": build_pages(page_texts, sections),
        "captions": caption_manifest(page_texts, sections),
        "math_index": math_index(sections),
        "appendix_index": extract_appendix_index(pdf_path, coverage),
        "language_hint": language_hint_for_text(full_text),
        "text_hash_sha256": text_hash(full_text),
    }


def main() -> None:
    args = parser().parse_args()
    record = ensure_record(args.input)
    record["paper_id"] = args.paper_id or record.get("paper_id") or paper_id_for_record(record)
    pdf_path = resolve_pdf_path(record)
    if pdf_path is None:
        raise SystemExit("extract_source_text.py requires a resolvable local PDF path.")

    raw_sections_output = args.raw_sections_output
    if not raw_sections_output and args.output:
        raw_sections_output = str(
            Path(args.output).with_name(
                Path(args.output).stem.replace("_source_manifest", "") + "_raw_sections.jsonl"
            )
        )

    page_texts = extract_page_texts(pdf_path, args.max_pages)
    sections = extract_raw_sections(page_texts)
    if raw_sections_output:
        write_jsonl(sections, raw_sections_output)
    if args.full_text_output:
        write_full_text_markdown(sections, args.full_text_output, str(record.get("title", "")))

    manifest = build_manifest(
        record=record,
        pdf_path=pdf_path,
        page_texts=page_texts,
        sections=sections,
        raw_sections_output=raw_sections_output,
        full_text_output=args.full_text_output,
        max_pages=args.max_pages,
    )
    emit(manifest, args.output)


if __name__ == "__main__":
    main()
