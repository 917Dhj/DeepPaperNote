from __future__ import annotations

import json
import sys
from pathlib import Path

import collect_metadata
import build_identity_contract
import fetch_pdf
import pytest


def write_error_artifact(path: Path, script: str) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "error",
                "script": script,
                "paper_id": "paper:error",
                "error": "upstream failed",
            }
        ),
        encoding="utf-8",
    )


def test_build_identity_contract_emits_accepted_artifact_and_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_path = tmp_path / "paper_resolve.json"
    metadata_path = tmp_path / "paper_metadata.json"
    identity_path = tmp_path / "paper_identity.json"
    trace_path = tmp_path / "paper_identity_repair_trace.json"
    resolve_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "doi:10.1234/example",
                "title": "Original Resolve Title",
                "doi": "10.1234/example",
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "doi:10.1234/example",
                "title": "Canonical Metadata Title",
                "authors": ["A. Author", "B. Author"],
                "year": "2026",
                "venue": "Journal of Tests",
                "doi": "10.1234/example",
                "pdf_url": "https://example.test/paper.pdf",
                "source_url": "https://doi.org/10.1234/example",
                "identity_confidence": "high",
                "identity_confidence_reasons": ["doi_present"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_identity_contract.py",
            "--input",
            str(metadata_path),
            "--resolve",
            str(resolve_path),
            "--trace-output",
            str(trace_path),
            "--output",
            str(identity_path),
        ],
    )

    build_identity_contract.main()

    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert identity["status"] == "ok"
    assert identity["artifact_type"] == "canonical_identity"
    assert identity["identity_verdict"] == "accepted"
    assert identity["work_level_identity"]["title"] == "Canonical Metadata Title"
    assert identity["work_level_identity"]["doi"] == "10.1234/example"
    assert identity["source_manifestation"]["pdf_url"] == "https://example.test/paper.pdf"
    assert identity["warnings"] == []
    assert identity["repair_trace_path"] == str(trace_path.resolve())
    assert identity["provenance"]["resolve_artifact_path"] == str(resolve_path.resolve())
    assert identity["provenance"]["metadata_artifact_path"] == str(metadata_path.resolve())
    assert any(item["kind"] == "doi" for item in identity["selected_identity_evidence"])

    assert trace["status"] == "ok"
    assert trace["artifact_type"] == "identity_repair_trace"
    assert trace["identity_verdict"] == "accepted"
    assert trace["repair_attempts"] == []
    assert trace["provenance"]["resolve_artifact_path"] == str(resolve_path.resolve())
    assert trace["provenance"]["metadata_artifact_path"] == str(metadata_path.resolve())


def test_collect_metadata_refuses_non_ok_input_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "resolve.json"
    output = tmp_path / "metadata.json"
    write_error_artifact(artifact, "resolve_paper.py")

    def fail_enrich_metadata(record: dict) -> dict:
        raise AssertionError("non-ok acquisition artifacts must fail before enrichment")

    monkeypatch.setattr("collect_metadata.enrich_metadata", fail_enrich_metadata)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_metadata.py",
            "--input",
            str(artifact),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        collect_metadata.main()

    assert "non-ok input artifact" in str(exc_info.value)
    assert not output.exists()


def test_fetch_pdf_uses_accepted_identity_contract_for_source_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output = tmp_path / "fetch.json"
    canonical_pdf = tmp_path / "canonical.pdf"
    stale_pdf = tmp_path / "stale.pdf"
    canonical_pdf.write_bytes(b"%PDF-1.4 canonical")
    stale_pdf.write_bytes(b"%PDF-1.4 stale")
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "paper:stale",
                "title": "Stale Metadata Title",
                "local_pdf_path": str(stale_pdf),
            }
        ),
        encoding="utf-8",
    )
    identity_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "build_identity_contract.py",
                "artifact_type": "canonical_identity",
                "paper_id": "paper:canonical",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Canonical Identity Title",
                    "doi": "10.1234/canonical",
                },
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "local_pdf_path": str(canonical_pdf),
                    "source_url": str(canonical_pdf),
                    "title": "Canonical Identity Title",
                },
                "selected_identity_evidence": [],
                "warnings": [],
                "repair_trace_path": str(tmp_path / "trace.json"),
            }
        ),
        encoding="utf-8",
    )
    captured_records: list[dict] = []

    def fake_pdf_source_candidates(record: dict) -> list[tuple[str, str]]:
        captured_records.append(dict(record))
        return [("local_pdf", str(canonical_pdf))]

    monkeypatch.setattr("fetch_pdf.pdf_source_candidates", fake_pdf_source_candidates)

    fetch_pdf.main(
        [
            "--input",
            str(metadata_path),
            "--identity",
            str(identity_path),
            "--output",
            str(output),
        ]
    )

    assert captured_records
    assert captured_records[0]["paper_id"] == "paper:canonical"
    assert captured_records[0]["title"] == "Canonical Identity Title"
    assert captured_records[0]["local_pdf_path"] == str(canonical_pdf)
    assert captured_records[0]["local_pdf_path"] != str(stale_pdf)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["paper_id"] == "paper:canonical"
    assert payload["title"] == "Canonical Identity Title"
    assert payload["pdf_path"] == str(canonical_pdf)
    assert payload["identity_contract"]["identity_verdict"] == "accepted"
    assert payload["source_manifestation"]["local_pdf_path"] == str(canonical_pdf)


def test_fetch_pdf_refuses_unaccepted_identity_contract_before_candidate_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output = tmp_path / "fetch.json"
    metadata_path.write_text(
        json.dumps({"status": "ok", "script": "collect_metadata.py"}),
        encoding="utf-8",
    )
    identity_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "build_identity_contract.py",
                "artifact_type": "canonical_identity",
                "identity_verdict": "repairable",
            }
        ),
        encoding="utf-8",
    )

    def fail_pdf_source_candidates(record: dict) -> list[tuple[str, str]]:
        raise AssertionError("unaccepted identity must fail before PDF candidate selection")

    monkeypatch.setattr("fetch_pdf.pdf_source_candidates", fail_pdf_source_candidates)

    with pytest.raises(SystemExit) as exc_info:
        fetch_pdf.main(
            [
                "--input",
                str(metadata_path),
                "--identity",
                str(identity_path),
                "--output",
                str(output),
            ]
        )

    assert "refuses unaccepted canonical identity" in str(exc_info.value)
    assert not output.exists()


def test_fetch_pdf_refuses_non_ok_input_artifact_before_candidate_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "metadata.json"
    output = tmp_path / "fetch.json"
    write_error_artifact(artifact, "collect_metadata.py")

    def fail_pdf_source_candidates(record: dict) -> list[tuple[str, str]]:
        message = "non-ok acquisition artifacts must fail before PDF candidate selection"
        raise AssertionError(message)

    monkeypatch.setattr("fetch_pdf.pdf_source_candidates", fail_pdf_source_candidates)

    with pytest.raises(SystemExit) as exc_info:
        fetch_pdf.main(["--input", str(artifact), "--output", str(output)])

    assert "non-ok input artifact" in str(exc_info.value)
    assert not output.exists()
