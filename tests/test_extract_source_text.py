from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_SOURCE_SCRIPT = PROJECT_ROOT / "scripts" / "extract_source_text.py"


def write_test_pdf(path: Path, pages: list[str]) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for PDF source extraction tests.")
    doc = fitz.open()
    try:
        for text in pages:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


def run_extract_source(input_path: Path, output_path: Path, *extra: str) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_SOURCE_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            *extra,
        ],
        check=True,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_extract_source_text_defaults_to_all_pages_and_jsonl(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pages = [
        "Abstract\nWe propose a raw-source extraction test.",
        "Introduction\nThis paper tests all-page extraction.",
        "Method\nThe method keeps full source text. L = -log p(y|x).",
        "Experiment\nFigure 1: System overview\nTable 1. Main results",
    ]
    pages.extend(f"Appendix page {index}" for index in range(5, 36))
    write_test_pdf(pdf_path, pages)

    input_path = tmp_path / "fetch.json"
    manifest_path = tmp_path / "paper_source_manifest.json"
    input_path.write_text(
        json.dumps({"paper_id": "paper:raw", "title": "Raw Paper", "pdf_path": str(pdf_path)}),
        encoding="utf-8",
    )

    manifest = run_extract_source(input_path, manifest_path)
    raw_sections_path = tmp_path / "paper_raw_sections.jsonl"

    assert manifest["coverage"]["total_pages"] == 35
    assert manifest["coverage"]["text_pages_extracted"] == 35
    assert manifest["coverage"]["text_truncated"] is False
    assert manifest["raw_sections_path"] == str(raw_sections_path.resolve())
    assert raw_sections_path.exists()
    raw_records = [
        json.loads(line)
        for line in raw_sections_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        record["kind"] == "method" and "full source text" in record["text"]
        for record in raw_records
    )
    assert manifest["captions"]["figures"][0]["id"] == "Figure 1"
    assert manifest["captions"]["tables"][0]["id"] == "Table 1"
    assert manifest["math_index"]


def test_extract_source_text_explicit_truncation_is_marked(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    write_test_pdf(pdf_path, [f"Method\nPage {index}" for index in range(1, 8)])

    input_path = tmp_path / "fetch.json"
    manifest_path = tmp_path / "run_source_manifest.json"
    input_path.write_text(
        json.dumps(
            {"paper_id": "paper:truncated", "title": "Truncated Paper", "pdf_path": str(pdf_path)}
        ),
        encoding="utf-8",
    )

    manifest = run_extract_source(input_path, manifest_path, "--max-pages", "3")

    assert manifest["coverage"]["total_pages"] == 7
    assert manifest["coverage"]["text_pages_extracted"] == 3
    assert manifest["coverage"]["text_truncated"] is True
    assert all(page["page"] <= 3 for page in manifest["pages"])


def test_extract_source_text_full_text_markdown_is_derived_from_jsonl(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    write_test_pdf(pdf_path, ["Abstract\nA source note.", "Conclusion\nDone."])

    input_path = tmp_path / "fetch.json"
    manifest_path = tmp_path / "paper_source_manifest.json"
    full_text_path = tmp_path / "paper_full_text.md"
    input_path.write_text(
        json.dumps(
            {"paper_id": "paper:markdown", "title": "Markdown Paper", "pdf_path": str(pdf_path)}
        ),
        encoding="utf-8",
    )

    manifest = run_extract_source(
        input_path,
        manifest_path,
        "--full-text-output",
        str(full_text_path),
    )
    raw_sections_path = Path(manifest["raw_sections_path"])
    raw_text = "\n".join(
        json.loads(line)["text"]
        for line in raw_sections_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    markdown = full_text_path.read_text(encoding="utf-8")

    assert manifest["full_text_md_path"] == str(full_text_path.resolve())
    assert "A source note." in raw_text
    assert "A source note." in markdown
