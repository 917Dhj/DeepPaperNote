from __future__ import annotations

import json
import sys
from pathlib import Path

import collect_metadata
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
