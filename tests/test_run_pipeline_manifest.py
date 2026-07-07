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
RUN_PIPELINE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "run_pipeline.py"


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
    identity_path = workdir / "paper_identity.json"
    identity_trace_path = workdir / "paper_identity_repair_trace.json"
    raw_sections_path = workdir / "paper_raw_sections.jsonl"
    evidence_path = workdir / "paper_evidence.json"
    decisions_path = workdir / "paper_figure_table_decisions.json"
    bundle_path = workdir / "paper_bundle.json"
    assert identity_path.exists()
    assert identity_trace_path.exists()
    assert source_manifest_path.exists()
    assert raw_sections_path.exists()
    assert evidence_path.exists()
    assert decisions_path.exists()
    assert bundle_path.exists()

    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity_trace = json.loads(identity_trace_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert identity["artifact_type"] == "canonical_identity"
    assert identity["identity_verdict"] == "accepted"
    assert identity["source_manifestation"]["source_kind"] == "local_pdf"
    assert identity["repair_trace_path"] == str(identity_trace_path.resolve())
    assert identity_trace["artifact_type"] == "identity_repair_trace"
    assert identity_trace["repair_attempts"] == []
    assert source_manifest["coverage"]["text_pages_extracted"] == 4
    assert source_manifest["coverage"]["text_truncated"] is False
    assert source_manifest["identity_contract"]["identity_verdict"] == "accepted"
    assert any(section["section_id"] == "sec:method" for section in source_manifest["sections"])
    assert evidence["summary"]["source_corpus_used"] is True
    assert {item["source_id"] for item in decisions["decisions"]} == {"Figure 1", "Table 1"}
    assert bundle["source_manifest"]["raw_sections_path"] == str(raw_sections_path.resolve())
    assert bundle["identity_contract"]["identity_verdict"] == "accepted"
    assert bundle["identity_contract"]["repair_trace_path"] == str(identity_trace_path.resolve())
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
    assert [Path(cmd[1]).name for cmd in calls] == [
        "resolve_paper.py",
        "collect_metadata.py",
        "build_identity_contract.py",
        "fetch_pdf.py",
        "extract_source_text.py",
        "extract_evidence.py",
        "extract_pdf_assets.py",
        "plan_figures.py",
        "plan_figure_table_decisions.py",
        "build_synthesis_bundle.py",
    ]

    resolve_call = calls[0]
    metadata_call = calls[1]
    identity_call = calls[2]
    fetch_call = calls[3]
    assert resolve_call[resolve_call.index("--input") + 1] == "paper.pdf"
    assert (
        metadata_call[metadata_call.index("--input") + 1]
        == str((workdir / "paper_resolve.json").resolve())
    )
    assert (
        identity_call[identity_call.index("--input") + 1]
        == str((workdir / "paper_metadata.json").resolve())
    )
    assert (
        identity_call[identity_call.index("--resolve") + 1]
        == str((workdir / "paper_resolve.json").resolve())
    )
    assert (
        identity_call[identity_call.index("--trace-output") + 1]
        == str((workdir / "paper_identity_repair_trace.json").resolve())
    )
    assert (
        fetch_call[fetch_call.index("--input") + 1]
        == str((workdir / "paper_metadata.json").resolve())
    )
    assert (
        fetch_call[fetch_call.index("--identity") + 1]
        == str((workdir / "paper_identity.json").resolve())
    )

    evidence_call = calls[5]
    assert "--source-manifest" in evidence_call
    assert (
        evidence_call[evidence_call.index("--source-manifest") + 1]
        == str((workdir / "paper_source_manifest.json").resolve())
    )


def test_run_pipeline_stops_before_fetch_when_identity_repair_is_exhausted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workdir = tmp_path / "run"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool = True, **kwargs) -> object:
        calls.append(cmd)
        if Path(cmd[1]).name == "build_identity_contract.py":
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_pipeline.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pipeline.py",
            "--input",
            "ambiguous-title",
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
        ],
    )

    with pytest.raises(subprocess.CalledProcessError):
        run_pipeline.main()

    assert [Path(cmd[1]).name for cmd in calls] == [
        "resolve_paper.py",
        "collect_metadata.py",
        "build_identity_contract.py",
    ]
