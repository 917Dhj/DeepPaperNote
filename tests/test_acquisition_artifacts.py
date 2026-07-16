from __future__ import annotations

import json
import sys
from pathlib import Path

import build_identity_contract
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


def build_identity_from_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolve_payload: dict,
    metadata_payload: dict,
    expect_failure: bool = False,
) -> tuple[dict, dict]:
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
    assert identity["work_level_identity"]["title"] == "Canonical DOI Title For Testing"
    assert identity["work_level_identity"]["doi"] == "10.1234/canonical"
    assert identity["source_manifestation"]["local_pdf_path"] == str(pdf_path.resolve())
    assert len(trace["repair_attempts"]) == 1
    attempt = trace["repair_attempts"][0]
    assert attempt["action"] == "replace_challengeable_identity_anchor"
    assert (
        attempt["replacement_reason"]
        == "challengeable_first_page_title_replaced_by_stronger_identity_evidence"
    )
    assert (
        attempt["rejected_candidate_identity"]["title"]
        == "A Noisy Cover Sheet Title For Testing"
    )
    assert attempt["accepted_correction"]["title"] == "Canonical DOI Title For Testing"
    assert any(
        item["kind"] == "doi" and item["value"] == "10.1234/canonical"
        for item in attempt["evidence_used"]
    )


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

    assert identity["work_level_identity"]["title"] == "Authoritative arXiv Repair Title"
    assert identity["work_level_identity"]["arxiv_id"] == "2401.00001"
    attempt = trace["repair_attempts"][0]
    assert (
        attempt["replacement_reason"]
        == "challengeable_filename_title_replaced_by_stronger_identity_evidence"
    )
    assert (
        attempt["rejected_candidate_identity"]["title"]
        == "Smith 等 - 2024 - Noisy Local Filename-123456"
    )
    assert any(
        item["kind"] == "arxiv_id" and item["value"] == "2401.00001"
        for item in attempt["evidence_used"]
    )


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
    )

    assert identity["work_level_identity"]["title"] == "Authoritative Metadata Filled Title"
    assert identity["work_level_identity"]["doi"] == "10.5555/blank"
    attempt = trace["repair_attempts"][0]
    assert (
        attempt["replacement_reason"]
        == "blank_challengeable_title_filled_by_stronger_identity_evidence"
    )
    assert attempt["rejected_candidate_identity"]["title"] == ""
    assert attempt["accepted_correction"]["title"] == "Authoritative Metadata Filled Title"


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
        },
    )

    assert identity["work_level_identity"]["title"] == "User Intended Strong DOI Paper"
    assert identity["work_level_identity"]["doi"] == "10.1234/original"
    assert identity["source_manifestation"]["source_url"] == "https://doi.org/10.1234/original"
    assert identity["source_manifestation"]["pdf_url"] == ""
    assert len(trace["repair_attempts"]) == 1
    attempt = trace["repair_attempts"][0]
    assert attempt["action"] == "protect_strong_identity_anchor"
    assert (
        attempt["replacement_reason"]
        == "strong_identity_anchor_protected_from_unrelated_provider_evidence"
    )
    assert attempt["rejected_candidate_identity"]["doi"] == "10.9999/unrelated"
    assert attempt["accepted_correction"]["doi"] == "10.1234/original"


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
    assert identity["work_level_identity"]["title"] == "DeepPaperNote: Evidence-First Reading"
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
        },
    )

    assert identity["identity_verdict"] == "accepted_with_warnings"
    assert identity["equivalence_decision"]["status"] == "equivalent"
    assert identity["work_level_identity"]["year"] == "2026"
    assert identity["work_level_identity"]["venue"] == "Journal of Paper Systems"
    assert identity["source_manifestation"]["year"] == "2024"
    assert identity["source_manifestation"]["venue"] == "arXiv"
    assert {
        item["reason"]: (item["scope"], item["impact"])
        for item in identity["warnings"]
    } == {
        "source_manifestation_year_differs_from_work_identity": (
            "metadata",
            "avoid_over_specific_year_claims",
        ),
        "source_manifestation_venue_differs_from_work_identity": (
            "metadata",
            "avoid_over_specific_venue_claims",
        ),
    }
    assert trace["identity_verdict"] == "accepted_with_warnings"
    assert trace["warnings"] == identity["warnings"]


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
    assert identity["identity_verdict"] == "ambiguous"
    assert identity["identity_failure_class"] == "ambiguous_competing_identities"
    assert "stronger identifier" in identity["failure_summary"]
    assert "Efficient Vision Transformers" not in identity["failure_summary"]
    assert "Efficient Language Models" not in identity["failure_summary"]
    assert identity["equivalence_decision"]["status"] == "ambiguous"
    assert identity["equivalence_decision"]["reason"] == "competing_identity_evidence"
    assert any(
        item["kind"] == "leading_author" and item["status"] == "conflict"
        for item in identity["equivalence_decision"]["evidence"]
    )
    assert trace["status"] == "error"
    assert trace["run_status"] == "failed"
    assert trace["identity_verdict"] == "ambiguous"
    assert trace["identity_failure_class"] == "ambiguous_competing_identities"
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
        (
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "doi:10.1234/original",
                "source_type": "doi",
                "title": "Original DOI Paper",
                "doi": "10.1234/original",
                "metadata_sources": ["doi"],
            },
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "doi:10.1234/original",
                "source_type": "doi",
                "title": "Original DOI Paper",
                "doi": "10.1234/original",
                "metadata_sources": ["doi", "crossref"],
                "identity_contradictions": ["crossref_title_author_conflict"],
            },
            "metadata_contradiction",
        ),
        (
            {
                "status": "ok",
                "script": "resolve_paper.py",
                "paper_id": "title:local-pdf",
                "source_type": "local_pdf",
                "source_url": "/tmp/mismatched.pdf",
                "local_pdf_path": "/tmp/mismatched.pdf",
                "title": "Local PDF About Vision Models",
                "authors": ["Alice Vision"],
                "abstract": "We classify images with compact vision transformers.",
                "metadata_sources": ["local_pdf"],
            },
            {
                "status": "ok",
                "script": "collect_metadata.py",
                "paper_id": "doi:10.9999/legal-language",
                "source_type": "local_pdf",
                "source_url": "/tmp/mismatched.pdf",
                "local_pdf_path": "/tmp/mismatched.pdf",
                "title": "Legal Language Models For Contract Review",
                "authors": ["Mallory Text"],
                "abstract": "We improve contract review with legal language models.",
                "doi": "10.9999/legal-language",
                "metadata_sources": ["local_pdf", "crossref"],
            },
            "source_pdf_mismatch",
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
                "paper_id": "paper:warning",
                "identity_verdict": "accepted_with_warnings",
                "work_level_identity": {"title": "Warning Scoped Paper"},
                "source_manifestation": {
                    "source_kind": "local_pdf",
                    "local_pdf_path": str(canonical_pdf),
                    "source_url": str(canonical_pdf),
                    "title": "Warning Scoped Paper",
                },
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
