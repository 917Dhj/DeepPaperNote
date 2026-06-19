from __future__ import annotations

import hashlib
import json
from pathlib import Path

from source_corpus import load_source_corpus, validate_source_corpus


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def valid_raw_sections() -> list[dict]:
    intro_text = "We introduce a source corpus loader."
    method_text = "The method computes L = -log p(y|x)."
    appendix_text = "Appendix details describe the implementation."
    return [
        {
            "record_type": "section",
            "section_id": "sec:introduction",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
            "text": intro_text,
            "char_count": len(intro_text),
            "text_hash_sha256": sha256_text(intro_text),
        },
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "page_start": 2,
            "page_end": 3,
            "text": method_text,
            "char_count": len(method_text),
            "text_hash_sha256": sha256_text(method_text),
        },
        {
            "record_type": "section",
            "section_id": "sec:appendix",
            "kind": "appendix",
            "title": "Appendix A",
            "page_start": 4,
            "page_end": 4,
            "text": appendix_text,
            "char_count": len(appendix_text),
            "text_hash_sha256": sha256_text(appendix_text),
        },
    ]


def valid_manifest(raw_sections_path: Path, *, truncated: bool = False) -> dict:
    raw_sections = valid_raw_sections()
    full_text = "\n\n".join(record["text"] for record in raw_sections)
    return {
        "status": "ok",
        "script": "extract_source_text.py",
        "schema_version": 1,
        "paper_id": "paper:source-corpus",
        "title": "Source Corpus Paper",
        "source_kind": "pdf_text",
        "raw_sections_path": str(raw_sections_path),
        "full_text_md_path": "",
        "pdf": {
            "path": "/tmp/source-corpus.pdf",
            "total_pages": 4,
            "text_pages_extracted": 4,
            "text_max_pages": 3 if truncated else None,
            "text_truncated": truncated,
        },
        "coverage": {
            "total_pages": 4,
            "text_max_pages": 3 if truncated else None,
            "text_pages_extracted": 3 if truncated else 4,
            "text_pages_scanned": 3 if truncated else 4,
            "text_truncated": truncated,
            "truncated_due_to_page_limit": truncated,
            "appendix_detected": True,
            "appendix_start_page": 4,
        },
        "sections": [
            {
                key: record[key]
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
            for record in raw_sections
        ],
        "pages": [
            {"page": 1, "char_count": 36, "section_ids": ["sec:introduction"]},
            {"page": 2, "char_count": 20, "section_ids": ["sec:method"]},
            {"page": 3, "char_count": 19, "section_ids": ["sec:method"]},
            {"page": 4, "char_count": 45, "section_ids": ["sec:appendix"]},
        ],
        "captions": {
            "figures": [
                {
                    "id": "Figure 1",
                    "caption": "System overview.",
                    "page": 2,
                    "pages": [2],
                    "section_id": "sec:method",
                }
            ],
            "tables": [
                {
                    "id": "Table 1",
                    "caption": "Main results.",
                    "page": 3,
                    "pages": [3],
                    "section_id": "sec:method",
                }
            ],
        },
        "math_index": [
            {
                "text": "The method computes L = -log p(y|x).",
                "section_id": "sec:method",
                "page_start": 2,
                "page_end": 3,
            }
        ],
        "appendix_index": {
            "appendix_detected": True,
            "start_page": 4,
            "sections": [{"title": "Appendix A", "page": 4}],
            "figure_captions": [],
            "table_captions": [],
        },
        "language_hint": "en",
        "text_hash_sha256": sha256_text(full_text),
    }


def write_valid_corpus(tmp_path: Path, *, truncated: bool = False) -> Path:
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"
    write_jsonl(raw_sections_path, valid_raw_sections())
    return write_json(
        tmp_path / "paper_source_manifest.json",
        valid_manifest(raw_sections_path, truncated=truncated),
    )


def issue_codes(issues: list[dict]) -> set[str]:
    return {str(issue.get("code", "")) for issue in issues}


def test_load_source_corpus_exposes_manifest_raw_records_and_views(tmp_path: Path) -> None:
    manifest_path = write_valid_corpus(tmp_path)

    corpus = load_source_corpus(manifest_path)

    assert corpus.manifest["paper_id"] == "paper:source-corpus"
    assert [record["section_id"] for record in corpus.raw_sections] == [
        "sec:introduction",
        "sec:method",
        "sec:appendix",
    ]
    assert corpus.full_text() == "\n\n".join(record["text"] for record in valid_raw_sections())
    assert corpus.section_map()["sec:method"]["text"] == "The method computes L = -log p(y|x)."
    assert corpus.caption_items() == [
        {
            "kind": "figure",
            "id": "Figure 1",
            "caption": "System overview.",
            "page": 2,
            "pages": [2],
            "section_id": "sec:method",
        },
        {
            "kind": "table",
            "id": "Table 1",
            "caption": "Main results.",
            "page": 3,
            "pages": [3],
            "section_id": "sec:method",
        },
    ]
    assert corpus.appendix_pages() == [
        {"page": 4, "char_count": 45, "section_ids": ["sec:appendix"]}
    ]
    assert corpus.appendix_text_pages() == [
        {
            "page": 4,
            "text": "Appendix details describe the implementation.",
            "section_id": "sec:appendix",
            "title": "Appendix A",
        }
    ]
    assert corpus.coverage()["text_pages_extracted"] == 4
    assert corpus.truncation()["text_truncated"] is False
    assert corpus.language_hint() == "en"
    assert corpus.math_index()[0]["section_id"] == "sec:method"
    assert corpus.text_hash_metadata()["manifest_text_hash_sha256"] == corpus.manifest[
        "text_hash_sha256"
    ]
    assert validate_source_corpus(corpus) == []


def test_truncation_is_reported_as_corpus_fact_not_partial_acceptance(tmp_path: Path) -> None:
    manifest_path = write_valid_corpus(tmp_path, truncated=True)

    truncation = load_source_corpus(manifest_path).truncation()

    assert truncation["text_truncated"] is True
    assert truncation["truncated_due_to_page_limit"] is True
    assert truncation["partial_reading_accepted"] is False


def test_validation_reports_missing_raw_sections_with_stable_issue_code(tmp_path: Path) -> None:
    raw_sections_path = tmp_path / "missing_raw_sections.jsonl"
    manifest_path = write_json(
        tmp_path / "paper_source_manifest.json",
        valid_manifest(raw_sections_path),
    )

    issues = validate_source_corpus(load_source_corpus(manifest_path))

    assert "source_corpus_raw_sections_missing" in issue_codes(issues)


def test_validation_reports_invalid_jsonl_with_stable_issue_code(tmp_path: Path) -> None:
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"
    raw_sections_path.write_text('{"section_id": "sec:introduction"}\nnot-json\n', encoding="utf-8")
    manifest_path = write_json(
        tmp_path / "paper_source_manifest.json",
        valid_manifest(raw_sections_path),
    )

    issues = validate_source_corpus(load_source_corpus(manifest_path))

    assert "source_corpus_raw_sections_invalid_jsonl" in issue_codes(issues)


def test_validation_reports_empty_source_text_with_stable_issue_code(tmp_path: Path) -> None:
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"
    empty_record = {
        "record_type": "section",
        "section_id": "sec:introduction",
        "kind": "introduction",
        "title": "Introduction",
        "page_start": 1,
        "page_end": 1,
        "text": "   ",
        "text_hash_sha256": sha256_text("   "),
    }
    write_jsonl(raw_sections_path, [empty_record])
    manifest = valid_manifest(raw_sections_path)
    manifest["sections"] = [
        {
            "section_id": "sec:introduction",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
            "char_count": 3,
            "text_hash_sha256": sha256_text("   "),
        }
    ]
    manifest_path = write_json(tmp_path / "paper_source_manifest.json", manifest)

    issues = validate_source_corpus(load_source_corpus(manifest_path))

    assert "source_corpus_empty_text" in issue_codes(issues)


def test_validation_reports_manifest_raw_hash_mismatch_with_stable_issue_code(
    tmp_path: Path,
) -> None:
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"
    write_jsonl(raw_sections_path, valid_raw_sections())
    manifest = valid_manifest(raw_sections_path)
    manifest["sections"][1]["text_hash_sha256"] = "wrong-hash"
    manifest_path = write_json(tmp_path / "paper_source_manifest.json", manifest)

    issues = validate_source_corpus(load_source_corpus(manifest_path))

    assert "source_corpus_section_hash_mismatch" in issue_codes(issues)


def test_validation_reports_invalid_locations_with_stable_issue_codes(tmp_path: Path) -> None:
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"
    raw_sections = valid_raw_sections()
    raw_sections[1]["page_start"] = 3
    raw_sections[1]["page_end"] = 2
    write_jsonl(raw_sections_path, raw_sections)
    manifest = valid_manifest(raw_sections_path)
    manifest["sections"][1]["page_start"] = 3
    manifest["sections"][1]["page_end"] = 2
    manifest["pages"][0]["page"] = 0
    manifest["captions"]["figures"][0]["pages"] = [0]
    manifest_path = write_json(tmp_path / "paper_source_manifest.json", manifest)

    issues = validate_source_corpus(load_source_corpus(manifest_path))
    codes = issue_codes(issues)

    assert "source_corpus_section_location_invalid" in codes
    assert "source_corpus_page_location_invalid" in codes
    assert "source_corpus_caption_location_invalid" in codes
