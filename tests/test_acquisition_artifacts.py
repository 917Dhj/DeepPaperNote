from __future__ import annotations

import json
import sys
from pathlib import Path

import build_identity_contract
import collect_metadata
import common
import extract_evidence
import extract_pdf_assets
import extract_source_text
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


def build_identity_from_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolve_payload: dict,
    metadata_payload: dict,
    expect_failure: bool = False,
) -> tuple[dict, dict]:
    metadata_payload = dict(metadata_payload)
    metadata_payload.setdefault("identity_observations", [])
    resolve_path = tmp_path / "paper_resolve.json"
    metadata_path = tmp_path / "paper_metadata.json"
    identity_path = tmp_path / "paper_identity.json"
    trace_path = tmp_path / "paper_identity_repair_trace.json"
    resolve_path.write_text(json.dumps(resolve_payload), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata_payload), encoding="utf-8")
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

    if expect_failure:
        with pytest.raises(SystemExit) as exc_info:
            build_identity_contract.main()
        assert exc_info.value.code == 1
    else:
        build_identity_contract.main()

    return (
        json.loads(identity_path.read_text(encoding="utf-8")),
        json.loads(trace_path.read_text(encoding="utf-8")),
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
                "identity_observations": [
                    {
                        "provider": "crossref",
                        "retrieved_by": {
                            "kind": "doi",
                            "value": "10.1234/example",
                        },
                        "record": {
                            "title": "Canonical Metadata Title",
                            "authors": ["A. Author", "B. Author"],
                            "year": "2026",
                            "venue": "Journal of Tests",
                            "doi": "10.1234/example",
                            "pdf_url": "https://example.test/paper.pdf",
                        },
                    }
                ],
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
    assert identity["work_level_identity"]["title"] == "Original Resolve Title"
    assert identity["work_level_identity"]["doi"] == "10.1234/example"
    assert identity["accepted_metadata"]["authors"] == ["A. Author", "B. Author"]
    assert identity["bound_sources"][0]["value"] == "https://example.test/paper.pdf"
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


def test_build_identity_contract_repairs_noisy_first_page_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "noisy.pdf"
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:weak",
            "source_type": "local_pdf",
            "source_url": str(pdf_path),
            "local_pdf_path": str(pdf_path),
            "title": "A Noisy Cover Sheet Title For Testing",
            "local_pdf_title_source": "first_page_title_used",
            "metadata_sources": ["local_pdf"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.1234/canonical",
            "source_type": "local_pdf",
            "source_url": str(pdf_path),
            "local_pdf_path": str(pdf_path),
            "title": "Canonical DOI Title For Testing",
            "authors": ["Alice Example"],
            "doi": "10.1234/canonical",
            "metadata_sources": ["local_pdf", "crossref"],
            "title_corrected_from_external_metadata": True,
            "local_pdf_title_source": "first_page_title_used",
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present"],
        },
    )

    assert identity["identity_verdict"] == "accepted"
    assert identity["work_level_identity"]["title"] == (
        "A Noisy Cover Sheet Title For Testing"
    )
    assert identity["work_level_identity"]["doi"] == ""
    assert identity["source_manifestation"]["local_pdf_path"] == str(pdf_path.resolve())
    assert trace["repair_attempts"] == []


def test_build_identity_contract_repairs_filename_only_title_with_arxiv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "Smith 等 - 2024 - Noisy Local Filename-123456.pdf"
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:weak",
            "source_type": "local_pdf",
            "source_url": str(pdf_path),
            "local_pdf_path": str(pdf_path),
            "title": "Smith 等 - 2024 - Noisy Local Filename-123456",
            "local_pdf_title_source": "local_pdf_stem_used",
            "local_pdf_artifact_title": True,
            "metadata_sources": ["local_pdf"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "arxiv:2401.00001",
            "source_type": "local_pdf",
            "source_url": str(pdf_path),
            "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf",
            "local_pdf_path": str(pdf_path),
            "title": "Authoritative arXiv Repair Title",
            "authors": ["Bob Example"],
            "arxiv_id": "2401.00001",
            "metadata_sources": ["local_pdf", "arxiv"],
            "title_corrected_from_external_metadata": True,
            "local_pdf_title_source": "local_pdf_stem_used",
            "local_pdf_artifact_title": True,
            "identity_confidence": "high",
            "identity_confidence_reasons": ["arxiv_id_present"],
        },
    )

    assert identity["work_level_identity"]["title"] == (
        "Smith 等 - 2024 - Noisy Local Filename-123456"
    )
    assert identity["work_level_identity"]["arxiv_id"] == ""
    assert trace["repair_attempts"] == []


def test_build_identity_contract_repairs_blank_challengeable_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "paper:blank",
            "source_type": "title_query",
            "title": "",
            "metadata_sources": ["title_query"],
            "identity_confidence": "low",
            "identity_confidence_reasons": ["title_query_unmatched"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.5555/blank",
            "source_type": "title_query",
            "title": "Authoritative Metadata Filled Title",
            "doi": "10.5555/blank",
            "metadata_sources": ["title_query", "crossref"],
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present"],
        },
        expect_failure=True,
    )

    assert identity["identity_failure_class"] == "insufficient_evidence"
    assert trace["repair_attempts"][-1]["action"] == "repair_exhausted_fail_closed"


def test_build_identity_contract_protects_strong_anchor_from_unrelated_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.1234/original",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/original",
            "title": "User Intended Strong DOI Paper",
            "doi": "10.1234/original",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.9999/unrelated",
            "source_type": "crossref",
            "source_url": "https://doi.org/10.9999/unrelated",
            "pdf_url": "https://example.test/unrelated.pdf",
            "title": "Unrelated Provider Paper",
            "doi": "10.9999/unrelated",
            "metadata_sources": ["doi", "crossref"],
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {"kind": "doi", "value": "10.1234/original"},
                    "record": {
                        "source_type": "crossref",
                        "source_url": "https://doi.org/10.9999/unrelated",
                        "pdf_url": "https://example.test/unrelated.pdf",
                        "title": "Unrelated Provider Paper",
                        "doi": "10.9999/unrelated",
                    },
                }
            ],
        },
    )

    assert identity["work_level_identity"]["title"] == "User Intended Strong DOI Paper"
    assert identity["work_level_identity"]["doi"] == "10.1234/original"
    assert identity["source_manifestation"]["source_url"] == "https://doi.org/10.1234/original"
    assert identity["source_manifestation"]["pdf_url"] == ""
    assert len(trace["repair_attempts"]) == 1
    attempt = trace["repair_attempts"][0]
    assert attempt["action"] == "reject_conflicting_provider_observation"
    assert attempt["rejected_candidate_identity"]["doi"] == "10.9999/unrelated"
    assert attempt["accepted_correction"]["doi"] == "10.1234/original"


def test_build_identity_contract_rejects_conflicting_same_title_provider_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/trusted",
            "title": "A Same Title Paper",
            "doi": "10.1234/trusted",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/trusted",
            "title": "A Same Title Paper",
            "doi": "10.1234/trusted",
            "metadata_sources": ["doi", "crossref"],
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "title": "A Same Title Paper",
                    "doi": "10.9999/conflicting",
                    "pdf_url": "https://example.test/conflicting.pdf",
                }
            ],
        },
    )

    assert identity["identity_verdict"] == "accepted"
    assert identity["work_level_identity"]["doi"] == "10.1234/trusted"
    assert identity["source_manifestation"]["pdf_url"] == ""
    assert len(trace["repair_attempts"]) == 1
    attempt = trace["repair_attempts"][0]
    assert attempt["action"] == "reject_conflicting_provider_observation"
    assert attempt["status"] == "rejected"
    assert attempt["rejected_candidate_identity"]["doi"] == "10.9999/conflicting"
    assert attempt["accepted_correction"]["doi"] == "10.1234/trusted"
    downstream_summary = common.canonical_identity_summary(identity)
    assert downstream_summary["schema_version"] == 2
    assert "accepted_observations" not in downstream_summary
    assert "rejected_observations" not in downstream_summary


def test_build_identity_contract_accepts_shared_identifier_observation_and_binds_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/trusted",
            "title": "A Shared Identifier Paper",
            "doi": "10.1234/trusted",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/trusted",
            "title": "A Shared Identifier Paper",
            "doi": "10.1234/trusted",
            "metadata_sources": ["doi"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {"kind": "doi", "value": "10.1234/trusted"},
                    "title": "A Shared Identifier Paper",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.1234/trusted",
                    "abstract": "Accepted provider abstract.",
                    "pdf_url": "https://example.test/accepted.pdf",
                }
            ],
        },
    )

    assert identity["schema_version"] == 2
    assert identity["accepted_metadata"]["abstract"] == "Accepted provider abstract."
    assert identity["accepted_metadata"]["authors"] == ["Alice Example"]
    assert identity["field_provenance"]["abstract"] == {
        "provider": "crossref",
        "retrieved_by": {"kind": "doi", "value": "10.1234/trusted"},
    }
    assert identity["field_provenance"]["doi"]["provider"] == "doi"
    assert identity["bound_sources"] == [
        {
            "kind": "pdf_url",
            "value": "https://example.test/accepted.pdf",
            "provider": "crossref",
            "binding_reason": "shared_identifier",
        }
    ]
    assert identity["accepted_observations"][0]["provider"] == "crossref"
    assert identity["rejected_observations"] == []
    assert trace["schema_version"] == 2
    assert trace["accepted_observations"] == identity["accepted_observations"]
    assert trace["rejected_observations"] == []
    assert trace["field_provenance"] == identity["field_provenance"]


def test_build_identity_contract_uses_symbol_preserving_title_author_year_equivalence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "zotero:PARENT01",
            "source_type": "zotero",
            "zotero_key": "PARENT01",
            "title": "Reliable C++ Agents",
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["zotero"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "zotero:PARENT01",
            "source_type": "zotero",
            "zotero_key": "PARENT01",
            "title": "Reliable C++ Agents",
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["zotero"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {"kind": "title", "value": "Reliable C++ Agents"},
                    "title": "Reliable C Agents",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.9999/wrong",
                    "pdf_url": "https://example.test/wrong.pdf",
                },
                {
                    "provider": "openalex",
                    "retrieved_by": {"kind": "title", "value": "Reliable C++ Agents"},
                    "title": "Reliable C++ Agents",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.1234/correct",
                    "pdf_url": "https://example.test/correct.pdf",
                },
            ],
        },
    )

    assert identity["accepted_metadata"]["doi"] == "10.1234/correct"
    assert [item["provider"] for item in identity["accepted_observations"]] == ["openalex"]
    assert [item["provider"] for item in identity["rejected_observations"]] == ["crossref"]
    assert identity["bound_sources"] == [
        {
            "kind": "pdf_url",
            "value": "https://example.test/correct.pdf",
            "provider": "openalex",
            "binding_reason": "title_author_year",
        }
    ]
    assert any(
        attempt["action"] == "accept_identity_promotion"
        and attempt["accepted_correction"]["doi"] == "10.1234/correct"
        for attempt in trace["repair_attempts"]
    )


@pytest.mark.parametrize(
    ("anchor_title", "candidate_title", "candidate_author", "candidate_year"),
    [
        ("Reliable C# Agents", "Reliable C Agents", "Alice Example", "2026"),
        ("Na+ Transport Models", "Na Transport Models", "Alice Example", "2026"),
        ("Reliable A/B Tests", "Reliable A B Tests", "Alice Example", "2026"),
        ("Reliable Agents", "Reliable Agents", "Bob Example", "2026"),
        ("Reliable Agents", "Reliable Agents", "Andrew Example", "2026"),
        ("Reliable Agents", "Reliable Agents", "A Example", "2026"),
        ("Reliable Agents", "Reliable Agents", "Example", "2026"),
        ("Reliable Agents", "Reliable Agents", "Alice Example", "2025"),
    ],
)
def test_build_identity_contract_rejects_symbol_author_or_year_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    anchor_title: str,
    candidate_title: str,
    candidate_author: str,
    candidate_year: str,
) -> None:
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "zotero:PARENT01",
            "source_type": "zotero",
            "zotero_key": "PARENT01",
            "title": anchor_title,
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["zotero"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "zotero:PARENT01",
            "source_type": "zotero",
            "zotero_key": "PARENT01",
            "title": anchor_title,
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["zotero"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {"kind": "title", "value": anchor_title},
                    "title": candidate_title,
                    "authors": [candidate_author],
                    "year": candidate_year,
                    "doi": "10.9999/rejected",
                    "pdf_url": "https://example.test/rejected.pdf",
                }
            ],
        },
    )

    assert "doi" not in identity["accepted_metadata"]
    assert identity["bound_sources"] == []
    assert identity["rejected_observations"][0]["reason"] == (
        "insufficient_equivalence_evidence"
    )


def test_build_identity_contract_rejects_a_later_conflicting_identity_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:trusted",
            "source_type": "title_query",
            "title": "Reliable Identity Admission",
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["title_query"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "title:trusted",
            "source_type": "title_query",
            "title": "Reliable Identity Admission",
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["title_query"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {
                        "kind": "title",
                        "value": "Reliable Identity Admission",
                    },
                    "title": "Reliable Identity Admission",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.1234/accepted",
                    "abstract": "Accepted first observation.",
                },
                {
                    "provider": "openalex",
                    "retrieved_by": {
                        "kind": "title",
                        "value": "Reliable Identity Admission",
                    },
                    "title": "Reliable Identity Admission",
                    "authors": ["Alice Example"],
                    "year": "2026",
                    "doi": "10.9999/conflicting",
                    "abstract": "Must not overwrite accepted metadata.",
                    "pdf_url": "https://example.test/conflicting.pdf",
                },
            ],
        },
    )

    assert identity["paper_id"] == "doi:10.1234/accepted"
    assert identity["accepted_metadata"]["doi"] == "10.1234/accepted"
    assert identity["accepted_metadata"]["abstract"] == "Accepted first observation."
    assert [item["provider"] for item in identity["accepted_observations"]] == [
        "crossref"
    ]
    assert [item["provider"] for item in identity["rejected_observations"]] == [
        "openalex"
    ]
    assert identity["bound_sources"] == []


def test_build_identity_contract_accepts_two_independent_title_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = [
        {
            "provider": provider,
            "retrieved_by": {"kind": "title", "value": "Consensus Paper"},
            "record": {
                "title": "Consensus Paper",
                "authors": ["Alice Example"],
                "year": "2026",
                "doi": "10.1234/consensus",
            },
        }
        for provider in ("crossref", "openalex")
    ]
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:consensus",
            "source_type": "title_query",
            "title": "Consensus Paper",
            "metadata_sources": ["title_query"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "title:consensus",
            "identity_observations": observations,
        },
    )

    assert identity["paper_id"] == "doi:10.1234/consensus"
    assert identity["accepted_metadata"]["authors"] == ["Alice Example"]
    assert [item["provider"] for item in identity["accepted_observations"]] == [
        "crossref",
        "openalex",
    ]


def test_build_identity_contract_rejects_provider_consensus_without_titles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = [
        {
            "provider": provider,
            "retrieved_by": {"kind": "title", "value": ""},
            "record": {
                "authors": ["Alice Example"],
                "year": "2026",
                "doi": "10.1234/missing-title",
            },
        }
        for provider in ("crossref", "openalex")
    ]
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:missing",
            "source_type": "title_query",
            "title": "",
            "metadata_sources": ["title_query"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "title:missing",
            "identity_observations": observations,
        },
        expect_failure=True,
    )

    assert identity["status"] == "error"
    assert not identity["paper_id"].startswith("doi:")
    assert identity["accepted_observations"] == []
    assert [item["provider"] for item in identity["rejected_observations"]] == [
        "crossref",
        "openalex",
    ]


def test_build_identity_contract_accepts_unique_exact_zotero_title_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_pdf = tmp_path / "zotero.pdf"
    local_pdf.write_bytes(b"%PDF-1.7\n")
    zotero_observation = {
        "provider": "zotero",
        "retrieved_by": {
            "kind": "title_query",
            "value": "Local Canonical Title",
        },
        "relation": {
            "kind": "zotero_lookup",
            "match_kind": "title",
            "match_resolution": "unique_exact",
        },
        "record": {
            "title": "Local Canonical Title",
            "authors": ["Local Author"],
            "year": "2024",
            "doi": "10.5555/local",
            "zotero_key": "PARENT01",
            "local_pdf_path": str(local_pdf),
        },
    }
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:local-canonical-title",
            "source_type": "title_query",
            "title": "Local Canonical Title",
            "metadata_sources": ["title_query"],
            "identity_observations": [zotero_observation],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "title:local-canonical-title",
            "identity_observations": [zotero_observation],
        },
    )

    assert identity["paper_id"] == "doi:10.5555/local"
    assert identity["accepted_observations"][0]["reason"] == (
        "unique_exact_zotero_title"
    )
    assert identity["bound_sources"] == [
        {
            "kind": "local_pdf",
            "value": str(local_pdf),
            "provider": "zotero",
            "binding_reason": "unique_exact_zotero_title",
        }
    ]


def test_fetch_consumers_have_no_paper_id_override() -> None:
    for parser in (extract_source_text.parser(), extract_evidence.parser()):
        assert "--paper-id" not in {
            option
            for action in parser._actions
            for option in action.option_strings
        }


@pytest.mark.parametrize(
    ("resolve_script", "metadata_script"),
    [
        ("raw_metadata", "collect_metadata.py"),
        ("resolve_paper.py", "raw_metadata"),
    ],
)
def test_build_identity_contract_rejects_nonproducer_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolve_script: str,
    metadata_script: str,
) -> None:
    with pytest.raises(SystemExit, match="producer"):
        build_identity_from_payloads(
            tmp_path,
            monkeypatch,
            resolve_payload={
                "status": "ok",
                "script": resolve_script,
                "paper_id": "doi:10.1234/raw",
                "doi": "10.1234/raw",
            },
            metadata_payload={
                "status": "ok",
                "script": metadata_script,
                "identity_observations": [],
            },
        )


def test_build_identity_contract_records_zotero_key_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "title:zotero",
            "source_type": "title_query",
            "title": "Zotero Promotion Paper",
            "authors": ["Alice Example"],
            "year": "2026",
            "metadata_sources": ["title_query"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "title:zotero",
            "identity_observations": [
                {
                    "provider": "zotero",
                    "retrieved_by": {
                        "kind": "title",
                        "value": "Zotero Promotion Paper",
                    },
                    "record": {
                        "title": "Zotero Promotion Paper",
                        "authors": ["Alice Example"],
                        "year": "2026",
                        "zotero_key": "PARENT01",
                    },
                }
            ],
        },
    )

    assert identity["paper_id"] == "zotero:PARENT01"
    promotion = trace["repair_attempts"][0]
    assert promotion["promoted_identifiers"] == {"zotero_key": "PARENT01"}
    assert promotion["previous_paper_id"] == "title:zotero"
    assert promotion["accepted_paper_id"] == "zotero:PARENT01"


def test_build_identity_contract_recomputes_a_stale_anchor_paper_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.9999/stale",
            "source_type": "doi",
            "doi": "10.1234/actual",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "identity_observations": [],
        },
    )

    assert identity["paper_id"] == "doi:10.1234/actual"
    assert identity["accepted_metadata"]["paper_id"] == "doi:10.1234/actual"


def test_build_identity_contract_derives_a_bound_source_from_accepted_frontiers_doi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.3389/fpubh.2019.00399",
            "source_type": "doi",
            "source_url": "https://doi.org/10.3389/fpubh.2019.00399",
            "doi": "10.3389/fpubh.2019.00399",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.3389/fpubh.2019.00399",
            "source_type": "doi",
            "source_url": "https://doi.org/10.3389/fpubh.2019.00399",
            "doi": "10.3389/fpubh.2019.00399",
            "metadata_sources": ["doi"],
            "identity_observations": [],
        },
    )

    assert identity["bound_sources"] == [
        {
            "kind": "pdf_url",
            "value": (
                "https://www.frontiersin.org/articles/"
                "10.3389/fpubh.2019.00399/pdf"
            ),
            "provider": "doi",
            "binding_reason": "accepted_identifier_derived",
        }
    ]


def test_build_identity_contract_ignores_unadjudicated_top_level_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "doi": "10.1234/trusted",
            "metadata_sources": ["doi"],
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.1234/trusted",
            "source_type": "doi",
            "doi": "10.1234/trusted",
            "abstract": "Unadjudicated legacy field.",
            "pdf_url": "https://example.test/unadjudicated.pdf",
            "metadata_sources": ["doi", "legacy_merge"],
        },
    )

    assert "abstract" not in identity["accepted_metadata"]
    assert all(
        source["value"] != "https://example.test/unadjudicated.pdf"
        for source in identity["bound_sources"]
    )


def test_build_identity_contract_requires_the_observation_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_path = tmp_path / "resolve.json"
    metadata_path = tmp_path / "metadata.json"
    resolve_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "doi:10.1234/trusted",
                "source_type": "doi",
                "doi": "10.1234/trusted",
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "doi": "10.9999/raw",
                "pdf_url": "https://example.test/raw.pdf",
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
            str(tmp_path / "trace.json"),
            "--output",
            str(tmp_path / "identity.json"),
        ],
    )

    with pytest.raises(SystemExit, match="requires metadata identity_observations"):
        build_identity_contract.main()


def test_build_identity_contract_accepts_equivalent_arxiv_and_published_manifestations(
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
                "paper_id": "arxiv:2401.00001",
                "source_type": "arxiv_id",
                "source_url": "https://arxiv.org/abs/2401.00001",
                "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf",
                "title": "DeepPaperNote: Evidence First Reading",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "We introduce an evidence first reading workflow for one paper.",
                "arxiv_id": "2401.00001",
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "doi:10.1234/published",
                "source_type": "doi",
                "source_url": "https://doi.org/10.1234/published",
                "title": "DeepPaperNote: Evidence-First Reading",
                "authors": ["Alice Smith", "Bob Jones"],
                "abstract": "We introduce an evidence-first reading workflow for a single paper.",
                "year": "2026",
                "venue": "Journal of Paper Systems",
                "doi": "10.1234/published",
                "arxiv_id": "2401.00001",
                "identity_confidence": "high",
                "identity_confidence_reasons": ["doi_present", "arxiv_id_present"],
                "identity_observations": [
                    {
                        "provider": "crossref",
                        "retrieved_by": {
                            "kind": "arxiv_id",
                            "value": "2401.00001",
                        },
                        "record": {
                            "source_type": "doi",
                            "source_url": "https://doi.org/10.1234/published",
                            "title": "DeepPaperNote: Evidence-First Reading",
                            "authors": ["Alice Smith", "Bob Jones"],
                            "abstract": (
                                "We introduce an evidence-first reading workflow "
                                "for a single paper."
                            ),
                            "year": "2026",
                            "venue": "Journal of Paper Systems",
                            "doi": "10.1234/published",
                            "arxiv_id": "2401.00001",
                        },
                    }
                ],
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
    assert identity["identity_verdict"] == "accepted"
    assert identity["work_level_identity"]["title"] == (
        "DeepPaperNote: Evidence First Reading"
    )
    assert identity["work_level_identity"]["doi"] == "10.1234/published"
    assert identity["source_manifestation"]["source_kind"] == "arxiv_id"
    assert identity["source_manifestation"]["title"] == "DeepPaperNote: Evidence First Reading"
    assert identity["source_manifestation"]["source_url"] == "https://arxiv.org/abs/2401.00001"
    assert identity["source_manifestation"]["pdf_url"] == "https://arxiv.org/pdf/2401.00001.pdf"
    assert identity["equivalence_decision"]["status"] == "equivalent"
    assert identity["equivalence_decision"]["location_binding"] == "source_manifestation"
    assert any(
        item["kind"] == "shared_identifier" and item["value"] == "arxiv_id:2401.00001"
        for item in identity["equivalence_decision"]["evidence"]
    )
    assert trace["identity_verdict"] == "accepted"
    assert trace["equivalence_decision"] == identity["equivalence_decision"]


def test_build_identity_contract_marks_safe_metadata_uncertainty_as_warning_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload={
            "status": "ok",
            "script": "resolve_paper.py",
            "paper_id": "arxiv:2401.00001",
            "source_type": "arxiv_id",
            "source_url": "https://arxiv.org/abs/2401.00001",
            "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf",
            "title": "DeepPaperNote: Evidence First Reading",
            "authors": ["Alice Smith", "Bob Jones"],
            "abstract": "We introduce an evidence first reading workflow for one paper.",
            "year": "2024",
            "venue": "arXiv",
            "arxiv_id": "2401.00001",
        },
        metadata_payload={
            "status": "ok",
            "script": "collect_metadata.py",
            "paper_id": "doi:10.1234/published",
            "source_type": "doi",
            "source_url": "https://doi.org/10.1234/published",
            "title": "DeepPaperNote: Evidence-First Reading",
            "authors": ["Alice Smith", "Bob Jones"],
            "abstract": "We introduce an evidence-first reading workflow for a single paper.",
            "year": "2026",
            "venue": "Journal of Paper Systems",
            "doi": "10.1234/published",
            "arxiv_id": "2401.00001",
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present", "arxiv_id_present"],
            "identity_observations": [
                {
                    "provider": "crossref",
                    "retrieved_by": {
                        "kind": "arxiv_id",
                        "value": "2401.00001",
                    },
                    "record": {
                        "title": "DeepPaperNote: Evidence-First Reading",
                        "authors": ["Alice Smith", "Bob Jones"],
                        "year": "2026",
                        "venue": "Journal of Paper Systems",
                        "doi": "10.1234/published",
                        "arxiv_id": "2401.00001",
                    },
                }
            ],
        },
    )

    assert identity["identity_verdict"] == "accepted"
    assert identity["equivalence_decision"]["status"] == "equivalent"
    assert identity["work_level_identity"]["year"] == "2024"
    assert identity["work_level_identity"]["venue"] == "arXiv"
    assert identity["work_level_identity"]["doi"] == "10.1234/published"
    assert identity["source_manifestation"]["year"] == "2024"
    assert identity["source_manifestation"]["venue"] == "arXiv"
    assert identity["warnings"] == []
    assert trace["identity_verdict"] == "accepted"


def test_build_identity_contract_fails_closed_for_competing_manifestations_after_repair(
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
                "paper_id": "title:vision",
                "source_type": "title_query",
                "title": "Efficient Vision Transformers for Medical Images",
                "authors": ["Alice Vision"],
                "abstract": "We classify medical images with compact vision transformers.",
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "title:language",
                "source_type": "title_query",
                "title": "Efficient Language Models for Legal Reasoning",
                "authors": ["Mallory Text"],
                "abstract": "We improve legal reasoning with efficient language models.",
                "identity_confidence": "medium",
                "identity_confidence_reasons": ["external_metadata_title_match"],
                "identity_observations": [
                    {
                        "provider": "semantic_scholar",
                        "retrieved_by": {
                            "kind": "title",
                            "value": "Efficient Vision Transformers for Medical Images",
                        },
                        "record": {
                            "title": "Efficient Language Models for Legal Reasoning",
                            "authors": ["Mallory Text"],
                            "abstract": (
                                "We improve legal reasoning with efficient language models."
                            ),
                        },
                    }
                ],
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

    with pytest.raises(SystemExit) as exc_info:
        build_identity_contract.main()
    assert exc_info.value.code == 1

    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert identity["status"] == "error"
    assert identity["run_status"] == "failed"
    assert identity["identity_verdict"] == "failed"
    assert identity["identity_failure_class"] == "insufficient_evidence"
    assert "stronger identifier" in identity["failure_summary"]
    assert "Efficient Vision Transformers" not in identity["failure_summary"]
    assert "Efficient Language Models" not in identity["failure_summary"]
    assert identity["rejected_observations"][0]["reason"] == (
        "insufficient_equivalence_evidence"
    )
    assert trace["status"] == "error"
    assert trace["run_status"] == "failed"
    assert trace["identity_verdict"] == "failed"
    assert trace["identity_failure_class"] == "insufficient_evidence"
    assert trace["repair_attempts"][-1]["action"] == "repair_exhausted_fail_closed"
    assert trace["repair_attempts"][-1]["status"] == "failed"
    assert trace["equivalence_decision"] == identity["equivalence_decision"]


@pytest.mark.parametrize(
    ("resolve_payload", "metadata_payload", "failure_class"),
    [
        (
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "title:weak",
                "source_type": "title_query",
                "title": "Weak Title Only Paper",
                "metadata_sources": ["title_query"],
                "identity_confidence": "low",
                "identity_confidence_reasons": ["title_query_unmatched"],
            },
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "title:weak",
                "source_type": "title_query",
                "title": "Weak Title Only Paper",
                "metadata_sources": ["title_query"],
                "identity_confidence": "low",
                "identity_confidence_reasons": ["title_query_unmatched"],
            },
            "insufficient_evidence",
        ),
        (
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "title:provider-down",
                "source_type": "title_query",
                "title": "Provider Down Paper",
                "metadata_sources": ["title_query"],
            },
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "title:provider-down",
                "source_type": "title_query",
                "title": "Provider Down Paper",
                "metadata_sources": ["title_query"],
                "provider_unavailable": True,
            },
            "provider_unavailable",
        ),
    ],
)
def test_build_identity_contract_classifies_repair_exhausted_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolve_payload: dict,
    metadata_payload: dict,
    failure_class: str,
) -> None:
    identity, trace = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload=resolve_payload,
        metadata_payload=metadata_payload,
        expect_failure=True,
    )

    assert identity["status"] == "error"
    assert identity["run_status"] == "failed"
    assert identity["identity_failure_class"] == failure_class
    assert identity["failure_summary"]
    assert "provider_unavailable" not in identity["failure_summary"]
    assert trace["status"] == "error"
    assert trace["identity_failure_class"] == failure_class
    assert trace["repair_attempts"][-1]["action"] == "repair_exhausted_fail_closed"
    assert trace["repair_attempts"][-1]["failure_class"] == failure_class


def test_collect_metadata_refuses_non_ok_input_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "resolve.json"
    output = tmp_path / "metadata.json"
    write_error_artifact(artifact, "resolve_paper.py")

    def fail_collect_metadata_observations(record: dict) -> list[dict]:
        raise AssertionError("non-ok acquisition artifacts must fail before enrichment")

    monkeypatch.setattr(
        "collect_metadata.collect_metadata_observations",
        fail_collect_metadata_observations,
    )
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


def test_collect_metadata_preserves_provider_result_as_identity_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_path = tmp_path / "paper_resolve.json"
    metadata_path = tmp_path / "paper_metadata.json"
    resolve_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "doi:10.1234/trusted",
                "source_type": "doi",
                "source_url": "https://doi.org/10.1234/trusted",
                "title": "Trusted Input Paper",
                "doi": "10.1234/trusted",
                "metadata_sources": ["doi"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        common,
        "fetch_crossref_by_doi",
        lambda doi: {
            "source_type": "crossref",
            "title": "Trusted Input Paper",
            "doi": doi,
            "abstract": "Provider abstract.",
            "pdf_url": "https://example.test/provider.pdf",
            "metadata_sources": ["crossref"],
        },
    )
    monkeypatch.setattr(common, "fetch_openalex_by_doi", lambda doi: None)
    monkeypatch.setattr(common, "search_semantic_scholar", lambda query, limit=5: [])
    monkeypatch.setattr(common, "search_crossref_by_title", lambda title, limit=5: [])
    monkeypatch.setattr(common, "search_openalex_by_title", lambda title, limit=5: [])
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", lambda **kwargs: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_metadata.py",
            "--input",
            str(resolve_path),
            "--output",
            str(metadata_path),
        ],
    )

    collect_metadata.main()

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["doi"] == "10.1234/trusted"
    assert "abstract" not in metadata
    assert "pdf_url" not in metadata
    assert metadata["identity_observations"] == [
        {
            "provider": "crossref",
            "retrieved_by": {"kind": "doi", "value": "10.1234/trusted"},
            "record": {
                "source_type": "crossref",
                "title": "Trusted Input Paper",
                "doi": "10.1234/trusted",
                "abstract": "Provider abstract.",
                "pdf_url": "https://example.test/provider.pdf",
                "metadata_sources": ["crossref"],
            },
        }
    ]


def test_exact_swe_bench_title_admits_one_unique_arxiv_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    title = "SWE-bench: Can Language Models Resolve Real-world Github Issues?"
    resolve_payload = {
        "status": "ok",
        "script": "resolve_paper.py",
        "paper_id": "title:2156776fbf55",
        "source_type": "title_query",
        "title": title,
        "metadata_sources": ["title_query"],
    }
    monkeypatch.setattr(common, "search_semantic_scholar", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        common,
        "safe_fetch_arxiv_entries",
        lambda **kwargs: [
            {
                "source": "arxiv",
                "source_type": "arxiv",
                "title": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
                "authors": ["Carlos E. Jimenez"],
                "published": "2023-10-10T16:47:29Z",
                "arxiv_id": "2310.06770",
                "pdf_url": "https://arxiv.org/pdf/2310.06770v3",
            }
        ],
    )

    observations = common.collect_metadata_observations(resolve_payload)
    identity, _ = build_identity_from_payloads(
        tmp_path,
        monkeypatch,
        resolve_payload=resolve_payload,
        metadata_payload={
            **resolve_payload,
            "script": "collect_metadata.py",
            "identity_observations": observations,
        },
    )

    assert identity["identity_verdict"] == "accepted"
    assert identity["accepted_metadata"]["arxiv_id"] == "2310.06770"
    assert identity["accepted_observations"][0]["reason"] == (
        "unique_exact_arxiv_title"
    )


@pytest.mark.parametrize(
    "module",
    [extract_source_text, extract_evidence, extract_pdf_assets],
)
def test_downstream_extractors_reject_scalar_identity_bypasses(module: object) -> None:
    assert not hasattr(module, "enrich_metadata")
    with pytest.raises(SystemExit, match="JSON acquisition artifact"):
        module.ensure_record("Reliable C++ Agents")


@pytest.mark.parametrize(
    "module",
    [extract_source_text, extract_evidence, extract_pdf_assets],
)
def test_downstream_extractors_reject_non_fetch_json_bypasses(
    module: object,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "metadata.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "pdf_path": str(tmp_path / "bypass.pdf"),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="requires a fetch_pdf.py artifact"):
        module.ensure_record(str(artifact))


def test_fetch_pdf_uses_accepted_identity_contract_for_source_selection(
    tmp_path: Path,
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
                "schema_version": 2,
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
                "bound_sources": [
                    {
                        "kind": "local_pdf",
                        "value": str(canonical_pdf),
                        "provider": "local_pdf",
                        "binding_reason": "trusted_input",
                    }
                ],
                "selected_identity_evidence": [],
                "warnings": [],
                "repair_trace_path": str(tmp_path / "trace.json"),
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
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["paper_id"] == "paper:canonical"
    assert payload["title"] == "Canonical Identity Title"
    assert payload["pdf_path"] == str(canonical_pdf)
    assert payload["identity_contract"]["identity_verdict"] == "accepted"
    assert payload["source_manifestation"]["local_pdf_path"] == str(canonical_pdf)


def test_fetch_pdf_refuses_unaccepted_identity_contract_before_candidate_selection(
    tmp_path: Path,
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
                "schema_version": 2,
                "identity_verdict": "repairable",
                "bound_sources": [],
            }
        ),
        encoding="utf-8",
    )

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


def test_fetch_pdf_allows_accepted_with_warnings_identity_contract(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    identity_path = tmp_path / "identity.json"
    output = tmp_path / "fetch.json"
    canonical_pdf = tmp_path / "canonical.pdf"
    canonical_pdf.write_bytes(b"%PDF-1.4 canonical")
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
                "paper_id": "paper:warning",
                "identity_verdict": "accepted_with_warnings",
                "work_level_identity": {"title": "Warning Scoped Paper"},
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "local_pdf_path": str(canonical_pdf),
                    "source_url": str(canonical_pdf),
                    "title": "Warning Scoped Paper",
                },
                "bound_sources": [
                    {
                        "kind": "local_pdf",
                        "value": str(canonical_pdf),
                        "provider": "local_pdf",
                        "binding_reason": "trusted_input",
                    }
                ],
                "selected_identity_evidence": [],
                "warnings": ["metadata_year_missing"],
                "repair_trace_path": str(tmp_path / "trace.json"),
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
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["identity_contract"]["identity_verdict"] == "accepted_with_warnings"
    assert payload["source_manifestation"]["local_pdf_path"] == str(canonical_pdf)


def test_fetch_pdf_refuses_non_ok_input_artifact_before_candidate_selection(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "metadata.json"
    identity = tmp_path / "identity.json"
    output = tmp_path / "fetch.json"
    write_error_artifact(artifact, "collect_metadata.py")
    identity.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "build_identity_contract.py",
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "doi:10.1234/example",
                "identity_verdict": "accepted",
                "work_level_identity": {"doi": "10.1234/example"},
                "source_manifestation": {},
                "bound_sources": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc_info:
        fetch_pdf.main(
            [
                "--input",
                str(artifact),
                "--identity",
                str(identity),
                "--output",
                str(output),
            ]
        )

    assert "non-ok input artifact" in str(exc_info.value)
    assert not output.exists()
