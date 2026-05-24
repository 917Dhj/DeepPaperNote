from __future__ import annotations

from pathlib import Path

import pytest

import fetch_pdf


def test_pdf_source_candidates_add_frontiers_pdf_from_doi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fetch_pdf.enrich_metadata", lambda record: {"pdf_url": ""})

    candidates = fetch_pdf.pdf_source_candidates(
        {
            "doi": "10.3389/fpubh.2019.00399",
            "title": "The Effectiveness of Crisis Line Services: A Systematic Review",
        }
    )

    assert ("pdf_url", "https://www.frontiersin.org/articles/10.3389/fpubh.2019.00399/pdf") in candidates


def test_fetch_pdf_rejects_html_and_falls_back_to_frontiers_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "fetch.json"
    monkeypatch.setattr("fetch_pdf.enrich_metadata", lambda record: {"pdf_url": ""})
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
            '{"doi":"10.3389/fpubh.2019.00399","title":"Crisis Lines","pdf_url":"https://doi.org/10.3389/fpubh.2019.00399"}',
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
