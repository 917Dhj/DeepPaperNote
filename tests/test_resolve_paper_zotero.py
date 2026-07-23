from __future__ import annotations

import json
from pathlib import Path

import common
import pytest
import resolve_paper


def local_record() -> dict:
    return {
        "status": "ok",
        "source_type": "zotero",
        "metadata_sources": ["zotero"],
        "zotero_key": "PARENT01",
        "title": "Local Canonical Title",
        "authors": ["Local Author"],
        "year": "2024",
        "venue": "Local Venue",
        "doi": "10.5555/local",
        "local_pdf_path": "C:/Zotero/storage/ATTACH01/paper.pdf",
        "paper_id": "doi:10.5555/local",
        "identity_confidence": "high",
        "identity_confidence_reasons": ["doi_present", "zotero_key_present"],
    }


def test_resolve_title_keeps_input_as_anchor_without_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_provider(*args: object, **kwargs: object) -> object:
        raise AssertionError("resolve stage must not query metadata providers")

    monkeypatch.setattr(common, "search_semantic_scholar", fail_provider)
    monkeypatch.setattr(common, "search_crossref_by_title", fail_provider)
    monkeypatch.setattr(common, "search_openalex_by_title", fail_provider)
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", fail_provider)

    resolved = resolve_paper.resolve_scalar_reference(
        "Reliable C++ Agents",
        zotero_mode="off",
    )

    assert resolved["source_type"] == "title_query"
    assert resolved["title"] == "Reliable C++ Agents"
    assert resolved["metadata_sources"] == ["title_query"]
    assert "doi" not in resolved
    assert "pdf_url" not in resolved


@pytest.mark.parametrize(
    ("reference", "expected_source_type", "expected_field", "expected_value"),
    [
        ("10.1234/trusted", "doi", "doi", "10.1234/trusted"),
        ("2401.00001", "arxiv_id", "arxiv_id", "2401.00001"),
    ],
)
def test_resolve_strong_reference_keeps_input_as_anchor_without_provider_selection(
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
    expected_source_type: str,
    expected_field: str,
    expected_value: str,
) -> None:
    def fail_provider(*args: object, **kwargs: object) -> object:
        raise AssertionError("resolve stage must not query metadata providers")

    monkeypatch.setattr(common, "fetch_crossref_by_doi", fail_provider)
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", fail_provider)

    resolved = resolve_paper.resolve_scalar_reference(reference, zotero_mode="off")

    assert resolved["source_type"] == expected_source_type
    assert resolved[expected_field] == expected_value
    assert resolved["paper_id"].endswith(expected_value)


def test_auto_mode_preserves_input_anchor_and_emits_zotero_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "match",
            "match_kind": "doi",
            "record": local_record(),
            "probe": {
                "status": "available",
                "api_version": "3",
                "schema_version": "37",
            },
        },
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: {
            "status": "ok",
            "source_type": "doi",
            "doi": reference,
            "paper_id": f"doi:{reference}",
            "metadata_sources": ["doi"],
        },
    )

    resolved = resolve_paper.resolve_scalar_reference("10.5555/local")

    assert resolved["source_type"] == "doi"
    assert resolved["doi"] == "10.5555/local"
    assert "title" not in resolved
    assert resolved["identity_observations"] == [
        {
            "provider": "zotero",
            "retrieved_by": {"kind": "doi", "value": "10.5555/local"},
            "relation": {
                "kind": "zotero_lookup",
                "match_kind": "doi",
                "match_resolution": "unique_exact",
            },
            "record": local_record(),
        }
    ]
    assert resolved["zotero_lookup"] == {
        "mode": "auto",
        "status": "match",
        "match_kind": "doi",
        "api_status": "available",
        "api_version": "3",
        "schema_version": "37",
    }


def test_required_title_lookup_still_emits_an_observation_for_adjudication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "match",
            "match_kind": "title",
            "record": local_record(),
        },
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: {
            "status": "ok",
            "source_type": "title_query",
            "title": reference,
            "paper_id": "title:query",
            "metadata_sources": ["title_query"],
        },
    )

    resolved = resolve_paper.resolve_scalar_reference(
        "Local Canonical Title",
        zotero_mode="required",
    )

    assert resolved["source_type"] == "title_query"
    assert resolved["identity_observations"][0]["provider"] == "zotero"
    assert resolved["identity_observations"][0]["relation"] == {
        "kind": "zotero_lookup",
        "match_kind": "title",
        "match_resolution": "unique_exact",
    }


@pytest.mark.parametrize("lookup_status", ["not_found", "error"])
def test_auto_mode_falls_back_when_local_api_has_no_unique_match(
    lookup_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = {
        "status": lookup_status,
        "match_kind": "doi",
        "error": {
            "code": "zotero_not_running",
            "message": "not running",
            "retryable": True,
        },
    }
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: lookup,
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: {
            "status": "ok",
            "source_type": "doi",
            "doi": reference,
            "paper_id": f"doi:{reference}",
        },
    )

    resolved = resolve_paper.resolve_scalar_reference("10.5555/fallback")

    assert resolved["doi"] == "10.5555/fallback"
    assert resolved["zotero_lookup"]["status"] == lookup_status
    assert resolved["zotero_lookup"]["error"]["code"] == "zotero_not_running"


def test_auto_mode_fails_closed_on_ambiguous_local_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "ambiguous",
            "match_kind": "title",
            "candidate_count": 2,
        },
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: pytest.fail("an ambiguous local identity must not fall through"),
    )

    with pytest.raises(resolve_paper.ZoteroResolutionError) as exc_info:
        resolve_paper.resolve_scalar_reference("Ambiguous Paper")

    assert exc_info.value.failure_class == "zotero_ambiguous_match"
    assert exc_info.value.lookup["candidate_count"] == 2


def test_required_mode_fails_when_zotero_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "error",
            "match_kind": "zotero_key",
            "error": {
                "code": "zotero_not_running",
                "message": "not running",
                "retryable": True,
            },
        },
    )

    with pytest.raises(resolve_paper.ZoteroResolutionError) as exc_info:
        resolve_paper.resolve_scalar_reference("PARENT01", zotero_mode="required")

    assert exc_info.value.failure_class == "zotero_not_running"


def test_auto_mode_fails_when_an_explicit_zotero_key_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "error",
            "match_kind": "zotero_key",
            "error": {
                "code": "zotero_not_running",
                "message": "not running",
                "retryable": True,
            },
        },
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: pytest.fail("an unresolved explicit key has no safe web fallback"),
    )

    with pytest.raises(resolve_paper.ZoteroResolutionError) as exc_info:
        resolve_paper.resolve_scalar_reference("PARENT01", zotero_mode="auto")

    assert exc_info.value.failure_class == "zotero_not_running"


def test_off_mode_preserves_old_path_without_local_api_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: pytest.fail("off mode must not query Zotero"),
    )
    expected = {"status": "ok", "source_type": "zotero_key", "zotero_key": "PARENT01"}
    monkeypatch.setattr(resolve_paper, "resolve_reference", lambda reference: dict(expected))

    assert resolve_paper.resolve_scalar_reference("PARENT01", zotero_mode="off") == expected


def test_required_mode_bypasses_an_explicit_local_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: pytest.fail("local PDFs must bypass Zotero lookup"),
    )
    monkeypatch.setattr(
        resolve_paper,
        "resolve_reference",
        lambda reference: {"status": "ok", "local_pdf_path": reference},
    )

    resolved = resolve_paper.resolve_scalar_reference(str(pdf_path), zotero_mode="required")

    assert resolved["local_pdf_path"] == str(pdf_path)


def test_required_mode_rejects_a_generic_non_pdf_url() -> None:
    with pytest.raises(resolve_paper.ZoteroResolutionError) as exc_info:
        resolve_paper.resolve_scalar_reference(
            "https://example.test/papers/landing-page",
            zotero_mode="required",
        )
    assert exc_info.value.failure_class == "zotero_unsupported_reference"
    assert exc_info.value.lookup["match_kind"] == "unsupported_reference"


def test_required_mode_rejects_a_direct_pdf_url_without_querying_zotero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: pytest.fail(
            "a PDF URL has no strong Zotero query identifier"
        ),
    )

    with pytest.raises(resolve_paper.ZoteroResolutionError) as exc_info:
        resolve_paper.resolve_scalar_reference(
            "https://example.test/paper.pdf",
            zotero_mode="required",
        )

    assert exc_info.value.failure_class == "zotero_unsupported_reference"


def test_main_passes_through_trusted_json_without_querying_zotero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "input.json"
    output = tmp_path / "resolved.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "ok",
                "title": "Trusted Record",
                "doi": "10.5555/trusted",
                "paper_id": "doi:10.5555/trusted",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: pytest.fail("trusted artifacts must pass through"),
    )

    resolve_paper.main(
        [
            "--input",
            str(artifact),
            "--output",
            str(output),
            "--zotero-mode",
            "required",
            "--paper-id",
            "manual:override",
        ]
    )

    resolved = json.loads(output.read_text(encoding="utf-8"))
    assert resolved["title"] == "Trusted Record"
    assert resolved["paper_id"] == "manual:override"
    assert resolved["script"] == "resolve_paper.py"


def test_main_emits_failure_artifact_for_required_lookup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "resolved.json"
    monkeypatch.setattr(
        resolve_paper,
        "lookup_zotero_local",
        lambda reference, reference_type: {
            "status": "not_found",
            "match_kind": "doi",
        },
    )

    with pytest.raises(SystemExit, match="could not uniquely resolve"):
        resolve_paper.main(
            [
                "--input",
                "10.5555/missing",
                "--output",
                str(output),
                "--zotero-mode",
                "required",
            ]
        )

    failure = json.loads(output.read_text(encoding="utf-8"))
    assert failure["status"] == "error"
    assert failure["run_status"] == "failed"
    assert failure["failure_class"] == "zotero_item_not_found"
    assert failure["zotero_lookup"]["mode"] == "required"


def test_web_enrichment_does_not_override_zotero_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = local_record()
    monkeypatch.setattr(
        common,
        "fetch_crossref_by_doi",
        lambda doi: {
            "title": "Conflicting Web Title",
            "authors": ["Other Author"],
            "doi": "10.5555/conflict",
            "venue": "Conflicting Venue",
            "abstract": "Useful missing abstract.",
            "metadata_sources": ["crossref"],
        },
    )
    monkeypatch.setattr(common, "fetch_openalex_by_doi", lambda doi: None)
    monkeypatch.setattr(common, "search_semantic_scholar", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", lambda *args, **kwargs: [])

    enriched = common.enrich_metadata(record)

    assert enriched["title"] == "Local Canonical Title"
    assert enriched["authors"] == ["Local Author"]
    assert enriched["doi"] == "10.5555/local"
    assert enriched["venue"] == "Local Venue"
    assert enriched["local_pdf_path"] == record["local_pdf_path"]
    assert "abstract" not in enriched
    assert enriched["metadata_sources"] == ["zotero"]


def test_title_enrichment_rejects_an_unvalidated_doi_for_a_zotero_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = local_record()
    record.pop("doi")
    record["paper_id"] = "zotero:PARENT01"
    candidate = {
        "title": "Local Canonical Title",
        "authors": ["Different Author"],
        "year": "2023",
        "doi": "10.5555/different-paper",
        "abstract": "Abstract from the wrong same-title paper.",
        "metadata_sources": ["semantic_scholar"],
    }
    monkeypatch.setattr(common, "search_semantic_scholar", lambda *args, **kwargs: [candidate])
    monkeypatch.setattr(common, "search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", lambda *args, **kwargs: [])

    enriched = common.enrich_metadata(record)

    assert "doi" not in enriched
    assert enriched["paper_id"] == "zotero:PARENT01"
    assert "abstract" not in enriched


def test_title_enrichment_accepts_a_doi_after_zotero_author_and_year_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = local_record()
    record.pop("doi")
    record.pop("paper_id")
    candidate = {
        "title": "Local Canonical Title",
        "authors": ["Local Author", "Second Author"],
        "year": "2024",
        "doi": "10.5555/validated",
        "abstract": "Validated enrichment.",
        "metadata_sources": ["semantic_scholar"],
    }
    monkeypatch.setattr(common, "search_semantic_scholar", lambda *args, **kwargs: [candidate])
    monkeypatch.setattr(common, "search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr(common, "safe_fetch_arxiv_entries", lambda *args, **kwargs: [])

    enriched = common.enrich_metadata(record)

    assert enriched["doi"] == "10.5555/validated"
    assert enriched["paper_id"] == "doi:10.5555/validated"
    assert enriched["abstract"] == "Validated enrichment."
