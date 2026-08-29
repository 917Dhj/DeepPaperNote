from __future__ import annotations

import hashlib
import json
import os
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
EXTRACT_SOURCE_SCRIPT = (
    PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "extract_source_text.py"
)
WRITE_NOTE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"


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
    figures_path = workdir / "paper_figures.json"
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
    figures = json.loads(figures_path.read_text(encoding="utf-8"))
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
    assert source_manifest["source_sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert source_manifest["identity_contract"]["identity_verdict"] == "accepted"
    assert any(section["section_id"] == "sec:method" for section in source_manifest["sections"])
    assert evidence["summary"]["source_corpus_used"] is True
    assert figures["output_language"] == "zh-CN"
    assert decisions["output_language"] == "zh-CN"
    assert bundle["output_language"] == "zh-CN"
    assert bundle["writing_contract"]["language"] == "zh-CN"
    assert {item["source_id"] for item in decisions["decisions"]} == {"Figure 1", "Table 1"}
    assert bundle["source_manifest"]["raw_sections_path"] == str(raw_sections_path.resolve())
    assert bundle["identity_contract"]["identity_verdict"] == "accepted"
    assert bundle["identity_contract"]["repair_trace_path"] == str(identity_trace_path.resolve())
    assert bundle["figure_table_manifest"]["decisions"]
    removed_bundle_keys = ("evidence", "candidate_chunks", "section_texts", "summary")
    assert not any(key in bundle for key in removed_bundle_keys)

    note_text = "# 本地 PDF 语言完整性\n\n本笔记验证工件链可安全保存。\n"
    lint_path = workdir / "paper_lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "note_sha256": hashlib.sha256(note_text.encode("utf-8")).hexdigest(),
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
            }
        ),
        encoding="utf-8",
    )
    save_cwd = tmp_path / "save-valid"
    save_cwd.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "saved"
    saved = subprocess.run(
        [
            sys.executable,
            str(WRITE_NOTE_SCRIPT),
            "--title",
            "本地 PDF 语言完整性",
            "--content",
            note_text,
            "--lint-json",
            str(lint_path),
            "--figure-decisions",
            str(decisions_path),
        ],
        cwd=save_cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    save_payload = json.loads(saved.stdout)
    assert save_payload["output_language"] == "zh-CN"
    assert Path(save_payload["note_path"]).read_text(encoding="utf-8") == note_text
    assert Path(save_payload["images_dir"]).is_dir()

    for artifact_language, expected_error in (
        (None, "requires output_language"),
        ("en", "does not match resolved output_language zh-CN"),
    ):
        invalid_decisions = dict(decisions)
        if artifact_language is None:
            invalid_decisions.pop("output_language")
        else:
            invalid_decisions["output_language"] = artifact_language
        invalid_path = workdir / f"invalid-{artifact_language or 'missing'}.json"
        invalid_path.write_text(json.dumps(invalid_decisions), encoding="utf-8")
        failure_cwd = tmp_path / f"save-{artifact_language or 'missing'}"
        failure_cwd.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                str(WRITE_NOTE_SCRIPT),
                "--title",
                "本地 PDF 语言失败",
                "--content",
                note_text,
                "--lint-json",
                str(lint_path),
                "--figure-decisions",
                str(invalid_path),
            ],
            cwd=failure_cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert expected_error in result.stderr
        assert not (failure_cwd / "saved").exists()


def test_extract_source_text_rejects_a_mismatched_acquired_pdf_hash(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    fetch_path = tmp_path / "fetch.json"
    manifest_path = tmp_path / "paper_source_manifest.json"
    write_test_pdf(pdf_path)
    fetch_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "fetch_pdf.py",
                "paper_id": "paper:hash-mismatch",
                "title": "Hash Mismatch",
                "pdf_path": str(pdf_path),
                "source_sha256": "0" * 64,
                "identity_contract": {
                    "artifact_type": "canonical_identity",
                    "schema_version": 2,
                    "paper_id": "paper:hash-mismatch",
                    "identity_verdict": "accepted",
                    "work_level_identity": {"title": "Hash Mismatch"},
                },
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT_SOURCE_SCRIPT),
            "--input",
            str(fetch_path),
            "--output",
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "source_sha256 does not match acquired PDF" in result.stderr
    assert not manifest_path.exists()


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
    assert resolve_call[resolve_call.index("--zotero-mode") + 1] == "auto"
    assert metadata_call[metadata_call.index("--input") + 1] == str(
        (workdir / "paper_resolve.json").resolve()
    )
    assert identity_call[identity_call.index("--input") + 1] == str(
        (workdir / "paper_metadata.json").resolve()
    )
    assert identity_call[identity_call.index("--resolve") + 1] == str(
        (workdir / "paper_resolve.json").resolve()
    )
    assert identity_call[identity_call.index("--trace-output") + 1] == str(
        (workdir / "paper_identity_repair_trace.json").resolve()
    )
    assert fetch_call[fetch_call.index("--input") + 1] == str(
        (workdir / "paper_metadata.json").resolve()
    )
    assert fetch_call[fetch_call.index("--identity") + 1] == str(
        (workdir / "paper_identity.json").resolve()
    )
    assert fetch_call[fetch_call.index("--dest-dir") + 1] == str(
        (workdir / "paper_pdfs").resolve()
    )

    evidence_call = calls[5]
    assert "--source-manifest" in evidence_call
    assert evidence_call[evidence_call.index("--source-manifest") + 1] == str(
        (workdir / "paper_source_manifest.json").resolve()
    )
    assets_call = calls[6]
    assert assets_call[assets_call.index("--assets-dir") + 1] == str(
        (workdir / "paper_assets").resolve()
    )


def test_run_pipeline_stops_at_configuration_before_identity(
    tmp_path: Path,
    monkeypatch,
    configured_user_home: Path,
) -> None:
    configured_user_home.unlink()
    workdir = tmp_path / "must-not-exist"
    calls: list[list[str]] = []
    monkeypatch.setattr(run_pipeline.subprocess, "run", lambda cmd, **kwargs: calls.append(cmd))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pipeline.py",
            "--input",
            "paper.pdf",
            "--workdir",
            str(workdir),
        ],
    )

    with pytest.raises(SystemExit, match="needs_input"):
        run_pipeline.main()

    assert calls == []
    assert not workdir.exists()


def test_run_pipeline_propagates_run_override_without_persisting_it(
    tmp_path: Path,
    monkeypatch,
    configured_user_home: Path,
) -> None:
    original = configured_user_home.read_bytes()
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(cmd: list[str], check: bool = True, **kwargs) -> object:
        calls.append((cmd, kwargs["env"]))
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
            str(tmp_path / "run"),
            "--language",
            "en",
        ],
    )

    run_pipeline.main()

    assert calls
    assert all(env["DEEPPAPERNOTE_OUTPUT_LANGUAGE"] == "en" for _, env in calls)
    assert configured_user_home.read_bytes() == original


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


def test_run_pipeline_forwards_required_zotero_mode_only_to_resolve(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
            "10.5555/local",
            "--workdir",
            str(tmp_path / "run"),
            "--zotero-mode",
            "required",
        ],
    )

    run_pipeline.main()

    assert calls[0][calls[0].index("--zotero-mode") + 1] == "required"
    assert all("--zotero-mode" not in call for call in calls[1:])
