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

import run_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_PIPELINE_SCRIPT = PROJECT_ROOT / "scripts" / "run_pipeline.py"


def write_test_pdf(path: Path) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for pipeline integration tests.")
    doc = fitz.open()
    try:
        for text in [
            "Abstract\nWe propose a manifest pipeline test.\n"
            "Introduction\nThis paper checks source artifacts.",
            "Method\nThe method keeps raw source text. L = -log p(y|x).\n"
            "Figure 1: Pipeline overview",
            "Experiment\nTable 1. Main results\nThe result improves accuracy to 91.2.",
            "Conclusion\nThe pipeline works.",
        ]:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


def test_run_pipeline_emits_manifest_raw_decisions_and_lightweight_bundle(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    workdir = tmp_path / "run"
    write_test_pdf(pdf_path)

    subprocess.run(
        [
            sys.executable,
            str(RUN_PIPELINE_SCRIPT),
            "--input",
            str(pdf_path),
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
        ],
        check=True,
    )

    source_manifest_path = workdir / "paper_source_manifest.json"
    raw_sections_path = workdir / "paper_raw_sections.jsonl"
    decisions_path = workdir / "paper_figure_table_decisions.json"
    bundle_path = workdir / "paper_bundle.json"
    assert source_manifest_path.exists()
    assert raw_sections_path.exists()
    assert decisions_path.exists()
    assert bundle_path.exists()

    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert source_manifest["coverage"]["text_pages_extracted"] == 4
    assert source_manifest["coverage"]["text_truncated"] is False
    assert any(section["section_id"] == "sec:method" for section in source_manifest["sections"])
    assert {item["source_id"] for item in decisions["decisions"]} == {"Figure 1", "Table 1"}
    assert bundle["source_manifest"]["raw_sections_path"] == str(raw_sections_path.resolve())
    assert bundle["figure_table_manifest"]["decisions"]
    removed_bundle_keys = ("evidence", "candidate_chunks", "section_texts", "summary")
    assert not any(key in bundle for key in removed_bundle_keys)


def test_run_pipeline_does_not_materialize_before_final_save(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workdir = tmp_path / "run"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool = True, **kwargs) -> object:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pipeline.py",
            "--input",
            "paper.pdf",
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
        ],
    )

    run_pipeline.main()

    assert not any("materialize_figure_asset.py" in cmd[1] for cmd in calls)
