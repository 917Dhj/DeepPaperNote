from __future__ import annotations

import json
from pathlib import Path

import pytest

from plan_glossary import (
    find_occurrences,
    load_manifest_and_sections,
    load_terms,
    propose_candidates,
    read_raw_sections,
    triage_terms,
)


def _records() -> list[dict]:
    return [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "page_start": 3,
            "page_end": 5,
            "text": (
                "We use a sparse MoE student trained with knowledge distillation. "
                "MoE routing and SSDG. F10 and F1 score. EEG signals."
            ),
        },
        {
            "record_type": "section",
            "section_id": "sec:references",
            "kind": "references",
            "title": "References",
            "page_start": 9,
            "page_end": 10,
            "text": "Smith et al. Diffusion models for generation. 2020.",
        },
    ]


def test_loads_deeppapernote_manifest_raw_sections_contract(tmp_path: Path) -> None:
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in _records()))
    manifest = tmp_path / "paper_source_manifest.json"
    manifest.write_text(
        json.dumps({"paper_id": "paper-1", "raw_sections_path": str(raw)}, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded_manifest, records = load_manifest_and_sections(str(manifest), "")

    assert loaded_manifest["paper_id"] == "paper-1"
    assert [record["section_id"] for record in records] == ["sec:method", "sec:references"]


def test_loads_relative_raw_sections_path_from_manifest_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in _records()))
    manifest = tmp_path / "paper_source_manifest.json"
    manifest.write_text(
        json.dumps({"paper_id": "paper-1", "raw_sections_path": raw.name}, ensure_ascii=False),
        encoding="utf-8",
    )
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    loaded_manifest, records = load_manifest_and_sections(str(manifest), "")

    assert loaded_manifest["paper_id"] == "paper-1"
    assert [record["section_id"] for record in records] == ["sec:method", "sec:references"]


def test_read_raw_sections_rejects_malformed_jsonl(tmp_path: Path) -> None:
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text(json.dumps(_records()[0], ensure_ascii=False) + "\n{not-json}\n")

    with pytest.raises(SystemExit) as exc:
        read_raw_sections(raw)

    assert "Invalid raw sections JSONL" in str(exc.value)


def test_term_found_in_paper_routes_to_anchor_only() -> None:
    result = triage_terms(["MoE"], _records())[0]
    assert result["routing"] == "anchor_only"
    assert result["found_in_paper"] is True
    assert result["occurrences"] == 2
    assert result["paper_anchors"][0]["section_id"] == "sec:method"
    assert result["paper_anchors"][0]["page_start"] == 3


def test_references_only_occurrence_does_not_count_as_found() -> None:
    occurrences, anchors = find_occurrences("Diffusion", _records())
    assert occurrences == 0
    assert anchors == []


def test_alias_bridges_language_gap() -> None:
    result = triage_terms(["知识蒸馏|knowledge distillation|KD"], _records())[0]
    assert result["routing"] == "anchor_only"
    assert result["term"] == "知识蒸馏"
    assert result["surface_forms"] == ["知识蒸馏", "knowledge distillation", "KD"]


def test_ascii_term_matches_whole_word_only() -> None:
    occurrences, _ = find_occurrences("F1", _records())
    assert occurrences == 1


def test_load_terms_accepts_json_list_and_delimited_string() -> None:
    assert load_terms('["MoE", "SSDG"]') == ["MoE", "SSDG"]
    assert load_terms("MoE, SSDG\nKD") == ["MoE", "SSDG", "KD"]
    assert load_terms('["MoE", "moe"]') == ["MoE"]


def test_load_terms_rejects_malformed_json_list(tmp_path: Path) -> None:
    terms = tmp_path / "terms.json"
    terms.write_text('["MoE",', encoding="utf-8")

    with pytest.raises(SystemExit) as inline_exc:
        load_terms('["MoE",')
    with pytest.raises(SystemExit) as file_exc:
        load_terms(str(terms))

    assert "Invalid terms JSON list" in str(inline_exc.value)
    assert "Invalid terms JSON list" in str(file_exc.value)


def test_propose_ranks_acronyms_model_names_and_keywords() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:intro",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 2,
            "text": (
                "Interictal Epileptiform Discharges (IEDs) are key. "
                "IED detection is hard.\n"
                "Keywords: Domain Generalization, Mixture-of-Experts, Knowledge Distillation\n"
                "Knowledge Distillation helps. Knowledge Distillation again. "
                "Interictal Epileptiform Discharges matter. The Method works. The Method again."
            ),
        }
    ]
    candidates = {
        candidate["term"]: candidate["category"]
        for candidate in propose_candidates(records)
    }

    assert candidates["Domain Generalization"] == "keyword"
    assert candidates["Mixture-of-Experts"] == "keyword"
    assert candidates["Interictal Epileptiform Discharges"] == "full-name"
    assert candidates["IED"] == "acronym-or-model"
    assert candidates["Knowledge Distillation"] == "keyword"
    assert "The Method" not in candidates
