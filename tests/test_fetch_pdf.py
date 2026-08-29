from __future__ import annotations

import json
from pathlib import Path

import pytest

import fetch_pdf


def test_fetch_pdf_has_no_paper_id_override() -> None:
    assert "--paper-id" not in {
        option
        for action in fetch_pdf.parser()._actions
        for option in action.option_strings
    }


def test_fetch_pdf_rejects_html_and_falls_back_to_frontiers_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "fetch.json"
    metadata = tmp_path / "metadata.json"
    identity = tmp_path / "identity.json"
    metadata.write_text(
        json.dumps({"status": "ok", "script": "collect_metadata.py"}),
        encoding="utf-8",
    )
    identity.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "build_identity_contract.py",
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "doi:10.3389/fpubh.2019.00399",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Crisis Lines",
                    "doi": "10.3389/fpubh.2019.00399",
                },
                "source_manifestation": {"source_kind": "doi"},
                "bound_sources": [
                    {
                        "kind": "pdf_url",
                        "value": "https://doi.org/10.3389/fpubh.2019.00399",
                    },
                    {
                        "kind": "pdf_url",
                        "value": (
                            "https://www.frontiersin.org/articles/"
                            "10.3389/fpubh.2019.00399/pdf"
                        ),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    requested_urls: list[str] = []

    def fake_http_get_bytes(url: str) -> bytes:
        requested_urls.append(url)
        if url == "https://doi.org/10.3389/fpubh.2019.00399":
            return b"<html>not a pdf</html>"
        if url == "https://www.frontiersin.org/articles/10.3389/fpubh.2019.00399/pdf":
            return b"%PDF-1.7\nbody"
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("fetch_pdf.http_get_bytes", fake_http_get_bytes)

    fetch_pdf.main(
        [
            "--input",
            str(metadata),
            "--identity",
            str(identity),
            "--dest-dir",
            str(tmp_path),
            "--output",
            str(output),
        ]
    )

    assert requested_urls == [
        "https://doi.org/10.3389/fpubh.2019.00399",
        "https://www.frontiersin.org/articles/10.3389/fpubh.2019.00399/pdf",
    ]
    saved_pdf = next((tmp_path / "pdfs").glob("*.pdf"))
    assert saved_pdf.read_bytes().startswith(b"%PDF-")


def test_fetch_pdf_uses_only_identity_bound_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output_path = tmp_path / "fetch.json"
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "doi:10.9999/wrong",
                "title": "Wrong Candidate",
                "pdf_url": "https://example.test/wrong.pdf",
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
                "schema_version": 2,
                "paper_id": "doi:10.1234/trusted",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Trusted Paper",
                    "doi": "10.1234/trusted",
                },
                "source_manifestation": {"source_kind": "doi"},
                "bound_sources": [
                    {
                        "kind": "pdf_url",
                        "value": "https://example.test/trusted.pdf",
                        "provider": "crossref",
                        "binding_reason": "shared_identifier",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    requested_urls: list[str] = []

    def fake_http_get_bytes(url: str) -> bytes:
        requested_urls.append(url)
        return b"%PDF-1.7\ntrusted"

    monkeypatch.setattr(fetch_pdf, "http_get_bytes", fake_http_get_bytes)

    fetch_pdf.main(
        [
            "--input",
            str(metadata_path),
            "--identity",
            str(identity_path),
            "--dest-dir",
            str(tmp_path),
            "--output",
            str(output_path),
        ]
    )

    assert not hasattr(fetch_pdf, "enrich_metadata")
    assert requested_urls == ["https://example.test/trusted.pdf"]
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["paper_id"] == "doi:10.1234/trusted"
    assert payload["title"] == "Trusted Paper"
    assert payload["pdf_url"] == "https://example.test/trusted.pdf"
    assert payload["source_sha256"] == (
        "0cdae4135f26b10e67e6c4972b573c29913948373e8dc6210624b283b99c830d"
    )


def test_fetch_pdf_hashes_the_original_bound_local_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "original.pdf"
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output_path = tmp_path / "fetch.json"
    pdf_path.write_bytes(b"%PDF-1.7\nlocal-original")
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
                "schema_version": 2,
                "paper_id": "paper:local-original",
                "identity_verdict": "accepted",
                "work_level_identity": {"title": "Local Original"},
                "source_manifestation": {"source_kind": "local_pdf"},
                "bound_sources": [{"kind": "local_pdf", "value": str(pdf_path)}],
            }
        ),
        encoding="utf-8",
    )

    fetch_pdf.main(
        [
            "--input",
            str(metadata_path),
            "--identity",
            str(identity_path),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["pdf_path"] == str(pdf_path.resolve())
    assert payload["source_sha256"] == (
        "f131d003c562388dc22cf50d93c60ae52a598b4b2c72963adeb08d812aa92fca"
    )


def test_fetch_pdf_refuses_legacy_identity_without_bound_sources(
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "pdf_url": "https://example.test/raw-bypass.pdf",
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
                "schema_version": 1,
                "paper_id": "doi:10.1234/trusted",
                "identity_verdict": "accepted",
                "work_level_identity": {"doi": "10.1234/trusted"},
                "source_manifestation": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="schema v2"):
        fetch_pdf.main(
            [
                "--input",
                str(metadata_path),
                "--identity",
                str(identity_path),
            ]
        )


def test_fetch_pdf_skips_a_missing_bound_local_file_and_tries_the_next_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output_path = tmp_path / "fetch.json"
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
                "schema_version": 2,
                "paper_id": "doi:10.1234/trusted",
                "identity_verdict": "accepted",
                "work_level_identity": {
                    "title": "Trusted Paper",
                    "doi": "10.1234/trusted",
                },
                "source_manifestation": {},
                "bound_sources": [
                    {
                        "kind": "local_pdf",
                        "value": str(tmp_path / "missing.pdf"),
                    },
                    {
                        "kind": "pdf_url",
                        "value": "https://example.test/trusted.pdf",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fetch_pdf,
        "http_get_bytes",
        lambda url: b"%PDF-1.7\ntrusted",
    )

    fetch_pdf.main(
        [
            "--input",
            str(metadata_path),
            "--identity",
            str(identity_path),
            "--dest-dir",
            str(tmp_path),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["pdf_url"] == "https://example.test/trusted.pdf"
    assert payload["attempted_sources"] == [
        {
            "kind": "local_pdf",
            "path": str(tmp_path / "missing.pdf"),
            "status": "missing_file",
        }
    ]
