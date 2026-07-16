from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import pytest

import plan_glossary
from plan_glossary import (
    find_occurrences,
    load_manifest_and_sections,
    load_terms,
    main,
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


def _run_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, records: list[dict]
) -> dict:
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    manifest = tmp_path / "paper_source_manifest.json"
    manifest.write_text(
        json.dumps({"paper_id": "paper-1", "raw_sections_path": str(raw)}),
        encoding="utf-8",
    )
    output = tmp_path / "glossary_candidates.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_glossary.py",
            "--propose",
            "--source-manifest",
            str(manifest),
            "--output",
            str(output),
        ],
    )
    main()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    return payload


def _run_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reviewed_terms: list[str],
) -> dict:
    output = tmp_path / "glossary_reviewed.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_glossary.py",
            "--review-proposal",
            str(tmp_path / "glossary_candidates.json"),
            "--reviewed-terms",
            json.dumps(reviewed_terms, ensure_ascii=False),
            "--source-manifest",
            str(tmp_path / "paper_source_manifest.json"),
            "--output",
            str(output),
        ],
    )
    main()
    return json.loads(output.read_text(encoding="utf-8"))


def _run_triage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selected_terms: list[str] | str,
) -> dict:
    output = tmp_path / "glossary_plan.json"
    terms = (
        json.dumps(selected_terms, ensure_ascii=False)
        if isinstance(selected_terms, list)
        else selected_terms
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_glossary.py",
            "--reviewed-shortlist",
            str(tmp_path / "glossary_reviewed.json"),
            "--terms",
            terms,
            "--source-manifest",
            str(tmp_path / "paper_source_manifest.json"),
            "--output",
            str(output),
        ],
    )
    main()
    return json.loads(output.read_text(encoding="utf-8"))


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


def test_triage_cli_emits_elapsed_ms_to_output_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_proposal(tmp_path, monkeypatch, _records())
    _run_review(tmp_path, monkeypatch, ["MoE"])
    payload = _run_triage(tmp_path, monkeypatch, ["MoE"])
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    assert payload["mode"] == "triage"
    assert [item["term"] for item in payload["terms"]] == ["MoE"]


def test_references_only_occurrence_does_not_count_as_found() -> None:
    occurrences, anchors = find_occurrences("Diffusion", _records())
    assert occurrences == 0
    assert anchors == []


def test_triage_helper_rejects_caller_supplied_alias_syntax() -> None:
    with pytest.raises(SystemExit, match="exact name|alias"):
        triage_terms(["知识蒸馏|knowledge distillation|KD"], _records())


def test_ascii_term_matches_whole_word_only() -> None:
    occurrences, _ = find_occurrences("F1", _records())
    assert occurrences == 1


def test_load_terms_accepts_json_list_and_delimited_string() -> None:
    assert load_terms('["MoE", "SSDG"]') == ["MoE", "SSDG"]
    assert load_terms("MoE, SSDG\nKD") == ["MoE", "SSDG", "KD"]
    assert load_terms('["MoE", "moe"]') == ["MoE"]
    assert load_terms('["F1", "3D Gaussian Splatting"]') == ["F1", "3D Gaussian Splatting"]


def test_load_terms_rejects_malformed_json_list(tmp_path: Path) -> None:
    terms = tmp_path / "terms.json"
    terms.write_text('["MoE",', encoding="utf-8")

    with pytest.raises(SystemExit) as inline_exc:
        load_terms('["MoE",')
    with pytest.raises(SystemExit) as file_exc:
        load_terms(str(terms))

    assert "Invalid terms JSON list" in str(inline_exc.value)
    assert "Invalid terms JSON list" in str(file_exc.value)


@pytest.mark.parametrize(
    "selection",
    [
        "全部写入",
        "全部写入。",
        "1,3",
        "1、3",
        "1;3",
        "1；3",
        "1.",
        "1)",
        "#1",
        "(1)",
        '["1", "3"]',
    ],
)
def test_load_terms_rejects_unresolved_shortlist_selection(selection: str) -> None:
    with pytest.raises(SystemExit, match="Resolve shortlist"):
        load_terms(selection)


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
    ordered_terms = [candidate["term"] for candidate in propose_candidates(records)]

    assert candidates["Domain Generalization"] == "keyword"
    assert candidates["Mixture-of-Experts"] == "keyword"
    assert candidates["Interictal Epileptiform Discharges"] == "full-name"
    assert candidates["IED"] == "acronym-or-model"
    assert candidates["Knowledge Distillation"] == "keyword"
    assert "The Method" not in candidates
    assert max(
        ordered_terms.index(term)
        for term in ("Domain Generalization", "Mixture-of-Experts", "Knowledge Distillation")
    ) < ordered_terms.index("Interictal Epileptiform Discharges")
    assert ordered_terms.index("Interictal Epileptiform Discharges") < ordered_terms.index("IED")


def test_propose_cli_emits_selection_gate_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _run_proposal(tmp_path, monkeypatch, _records())
    assert payload["status"] == "ok"
    assert payload["mode"] == "propose"
    assert payload["workflow_state"] == "awaiting_semantic_review"
    assert payload["next_action"] == "record_reviewed_shortlist_then_present_and_wait"
    assert payload["summary"]["effective_body_characters"] == len(
        "".join(plan_glossary.effective_prose_text(_records()).split())
    )
    assert payload["summary"]["shortlist_limit"] == 10
    assert payload["summary"]["pool_candidates"] == len(payload["candidates"])


def test_propose_cli_reports_no_candidates_without_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:intro",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
            "text": "ordinary lowercase prose without candidate terminology.",
        }
    ]

    payload = _run_proposal(tmp_path, monkeypatch, records)

    assert payload["candidates"] == []
    assert payload["workflow_state"] == "no_candidates"
    assert payload["next_action"] == "report_no_candidates"
    assert payload["summary"] == {
        "effective_body_characters": len(
            "".join(plan_glossary.effective_prose_text(records).split())
        ),
        "shortlist_limit": 10,
        "pool_candidates": 0,
    }


def test_review_can_drop_all_candidates_and_reports_no_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    assert proposal["candidates"]

    review = _run_review(tmp_path, monkeypatch, [])

    assert review["reviewed_shortlist"] == []
    assert review["workflow_state"] == "no_candidates"
    assert review["next_action"] == "report_no_candidates"
    assert review["summary"]["reviewed_candidates"] == 0


@pytest.mark.parametrize(
    ("characters", "expected"),
    [
        (9_999, 10),
        (10_000, 18),
        (29_999, 18),
        (30_000, 25),
        (59_999, 25),
        (60_000, 35),
    ],
)
def test_shortlist_limit_uses_effective_body_length(
    characters: int, expected: int
) -> None:
    assert plan_glossary.shortlist_limit(characters) == expected


def test_propose_filters_code_noise_and_keeps_emphasized_core_terms() -> None:
    highlighted_sentence = (
        "This is one entire highlighted sentence with several ordinary prose words"
    )
    records = [
        {
            "record_type": "section",
            "section_id": "sec:chapter",
            "kind": "chapter",
            "title": "Chapter",
            "text": (
                "**ReAct**. *Plan-and-Solve* and **Reflection** are core methods.\n"
                "<strong>SerpApi</strong> provides search.\n"
                "**[LinkedTerm](https://example.invalid/SECRET_MODEL)** is linked prose.\n"
                f"**{highlighted_sentence}**\n"
                "```python\nLLM_API_KEY = 'KEY'\n"
                "REACT_PROMPT_TEMPLATE = 'MODEL'\n"
                "print('HUAWEI phone result')\n```\n"
                "# References\n**CitationNoise** appears only in the reference tail.\n"
            ),
        },
        {
            "record_type": "section",
            "section_id": "sec:refs",
            "kind": "references",
            "title": "References",
            "text": "SERPAPI TEMPLATE PLANNER",
        },
    ]

    terms = {item["term"] for item in propose_candidates(records)}

    assert {"ReAct", "Plan-and-Solve", "Reflection", "SerpApi", "LinkedTerm"} <= terms
    assert terms.isdisjoint({"KEY", "MODEL", "TEMPLATE", "HUAWEI", "SECRET", "CitationNoise"})
    assert highlighted_sentence not in terms


def test_occurrence_grounding_masks_non_prose_and_keeps_original_snippet_offsets() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:chapter",
            "kind": "chapter",
            "title": "Chapter",
            "text": (
                "```text\nReAct fenced code\n```\n"
                "`ReAct inline code`\n"
                "https://example.invalid/ReAct\n"
                + "x" * 100
                + "\n**ReAct** body evidence.\n"
                + "y" * 100
                + "\n# References\n**ReAct** citation only.\n"
            ),
        }
    ]

    candidate = next(
        item for item in propose_candidates(records) if item["term"] == "ReAct"
    )
    occurrences, anchors = plan_glossary._find_occurrences_for_forms(
        candidate["surface_forms"], records
    )
    triaged = plan_glossary._triage_candidates([candidate], records)[0]

    assert occurrences == candidate["occurrences"] == triaged["occurrences"] == 1
    assert anchors == triaged["paper_anchors"]
    assert "body evidence" in anchors[0]["snippet"]
    assert "fenced code" not in anchors[0]["snippet"]
    assert "citation only" not in anchors[0]["snippet"]


def test_candidate_mask_handles_exact_fences_code_spans_and_nested_link_destinations() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:chapter",
            "kind": "chapter",
            "title": "Chapter",
            "text": (
                "````python\nignored\n```\n**FenceLeak**\n````\n"
                "``prefix ` **InlineLeak**``\n"
                "[LinkedTerm](docs/topic_(SECRET)_MODEL)\n"
                "**CoreTerm** is body evidence.\n"
            ),
        }
    ]

    candidates = {item["term"]: item for item in propose_candidates(records)}

    assert {"LinkedTerm", "CoreTerm"} <= candidates.keys()
    assert candidates["LinkedTerm"]["occurrences"] == 1
    assert {"FenceLeak", "InlineLeak", "SECRET", "MODEL"}.isdisjoint(candidates)
    for term in ("FenceLeak", "InlineLeak", "SECRET", "MODEL"):
        assert find_occurrences(term, records) == (0, [])


@pytest.mark.parametrize(
    "sentence",
    [
        "We propose a new method",
        "This model improves benchmark accuracy",
        "我们提出一种新的方法",
    ],
)
def test_propose_rejects_emphasized_sentences(sentence: str) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "text": f"**{sentence}**",
        }
    ]

    terms = {item["term"] for item in propose_candidates(records)}

    assert sentence not in terms


@pytest.mark.parametrize(
    "term",
    [
        "ReAct",
        "Plan-and-Solve",
        "Reflection",
        "SerpApi",
        "Graph Memory Augmented Routing",
        "智能体路由",
        "归纳式与传导式推理",
    ],
)
def test_propose_keeps_term_shaped_emphasis(term: str) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "text": f"**{term}** appears once.",
        }
    ]

    candidate = next(item for item in propose_candidates(records) if item["term"] == term)

    assert candidate["category"] == "emphasis"
    assert candidate["occurrences"] == 1


@pytest.mark.parametrize("heading", ["参考文献", "引用"])
def test_propose_removes_chinese_reference_tail_from_single_record(
    heading: str,
) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:chapter",
            "kind": "chapter",
            "title": "Chapter",
            "text": (
                "**CoreTerm** is discussed in the chapter.\n"
                f"# {heading}\n"
                "**CitationNoise** appears only in the reference tail.\n"
            ),
        }
    ]

    terms = {item["term"] for item in propose_candidates(records)}

    assert "CoreTerm" in terms
    assert "CitationNoise" not in terms
    assert f"# {heading}" not in plan_glossary.effective_prose_text(records)


def test_propose_merges_nfkc_equivalent_surface_form_occurrences() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "text": "**ReAct** and **ＲｅＡｃｔ** are equivalent spellings.",
        }
    ]

    matches = [
        item
        for item in propose_candidates(records)
        if unicodedata.normalize("NFKC", item["term"]).casefold() == "react"
    ]

    assert len(matches) == 1
    assert matches[0]["term"] == "ReAct"
    assert matches[0]["occurrences"] == 2
    assert "ＲｅＡｃｔ" in matches[0]["snippet"]


def test_propose_deduplicates_overlapping_casefold_surface_matches() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "text": "**ReAct** and **react** are two original occurrences.",
        }
    ]

    candidate = next(
        item
        for item in propose_candidates(records)
        if unicodedata.normalize("NFKC", item["term"]).casefold() == "react"
    )

    assert candidate["occurrences"] == 2


def test_equivalent_surface_forms_preserve_record_order_and_anchor_limit() -> None:
    forms = ["ReAct", "ＲｅＡｃｔ"]
    records = [
        {
            "record_type": "section",
            "section_id": f"sec:{index}",
            "kind": "method",
            "title": f"Method {index}",
            "page_start": index + 1,
            "page_end": index + 1,
            "text": f"**{forms[index % 2]}** appears in record {index}.",
        }
        for index in range(5)
    ]

    candidate = next(
        item
        for item in propose_candidates(records)
        if unicodedata.normalize("NFKC", item["term"]).casefold() == "react"
    )
    occurrences, anchors = plan_glossary._find_occurrences_for_forms(forms, records)

    assert candidate["occurrences"] == 5
    assert occurrences == 5
    assert [anchor["section_id"] for anchor in anchors] == ["sec:0", "sec:1", "sec:2"]
    assert [anchor["page_start"] for anchor in anchors] == [1, 2, 3]


def test_propose_caps_pool_at_dynamic_shortlist_limit_plus_buffer() -> None:
    terms = [f"Term{index:02d}" for index in range(21)]
    records = [
        {
            "record_type": "section",
            "section_id": "sec:intro",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
            "text": "Keywords: " + ", ".join(reversed(terms)),
        }
    ]

    candidates = propose_candidates(records)

    assert len(candidates) == 20


@pytest.mark.parametrize(
    ("effective_characters", "expected_pool"),
    [(10_000, 28), (30_000, 35), (60_000, 45)],
)
def test_propose_caps_pool_at_higher_dynamic_tiers(
    effective_characters: int, expected_pool: int
) -> None:
    terms = [f"Term{index:02d}" for index in range(50)]
    keyword_line = "Keywords: " + ", ".join(terms)
    keyword_characters = sum(1 for character in keyword_line if not character.isspace())
    records = [
        {
            "record_type": "section",
            "section_id": "sec:intro",
            "kind": "introduction",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 1,
            "text": keyword_line + "\n" + "x" * (effective_characters - keyword_characters),
        }
    ]

    assert sum(
        1
        for character in plan_glossary.effective_prose_text(records)
        if not character.isspace()
    ) == effective_characters
    assert len(propose_candidates(records)) == expected_pool


def test_proposal_emits_ordered_surface_forms_and_stable_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "page_start": 1,
            "text": "**ReAct** and **ＲｅＡｃｔ** are equivalent source spellings.",
        }
    ]

    first = _run_proposal(tmp_path, monkeypatch, records)
    second = _run_proposal(tmp_path, monkeypatch, records)
    candidate = next(item for item in first["candidates"] if item["term"] == "ReAct")

    assert candidate["surface_forms"] == ["ReAct", "ＲｅＡｃｔ"]
    assert first["provenance"] == second["provenance"]
    assert first["provenance"]["paper_id"] == "paper-1"
    assert len(first["provenance"]["source_sha256"]) == 64
    assert len(first["provenance"]["proposal_sha256"]) == 64


def test_review_recording_preserves_exact_ordered_candidate_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    names = [item["term"] for item in proposal["candidates"][:2]][::-1]

    reviewed = _run_review(tmp_path, monkeypatch, names)

    expected = [
        next(item for item in proposal["candidates"] if item["term"] == name)
        for name in names
    ]
    assert reviewed["mode"] == "review"
    assert reviewed["reviewed_shortlist"] == expected
    assert reviewed["proposal_provenance"] == proposal["provenance"]
    assert reviewed["provenance"]["proposal_sha256"] == proposal["provenance"][
        "proposal_sha256"
    ]


@pytest.mark.parametrize(
    "reviewed_terms",
    [
        ["renamed candidate"],
        ["MoE", "MoE"],
        ["MoE|invented-alias"],
    ],
)
def test_review_recording_rejects_non_exact_or_duplicate_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reviewed_terms: list[str],
) -> None:
    _run_proposal(tmp_path, monkeypatch, _records())

    with pytest.raises(SystemExit, match="reviewed|proposal|duplicate|exact"):
        _run_review(tmp_path, monkeypatch, reviewed_terms)


def test_review_recording_rejects_more_than_dynamic_shortlist_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:intro",
            "kind": "introduction",
            "title": "Introduction",
            "text": "Keywords: " + ", ".join(f"Term{index:02d}" for index in range(12)),
        }
    ]
    proposal = _run_proposal(tmp_path, monkeypatch, records)
    names = [item["term"] for item in proposal["candidates"][:11]]

    with pytest.raises(SystemExit, match="shortlist limit"):
        _run_review(tmp_path, monkeypatch, names)


def test_review_recording_rejects_tampered_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    proposal["candidates"][0]["term"] = "Tampered"
    (tmp_path / "glossary_candidates.json").write_text(
        json.dumps(proposal, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="proposal"):
        _run_review(tmp_path, monkeypatch, ["Tampered"])


def test_review_recording_rejects_proposal_from_another_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    manifest = tmp_path / "paper_source_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["paper_id"] = "paper-2"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="paper|source|proposal"):
        _run_review(tmp_path, monkeypatch, [proposal["candidates"][0]["term"]])


def test_review_recording_rejects_changed_source_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text(raw.read_text(encoding="utf-8") + "\n" + json.dumps({
        "record_type": "section",
        "section_id": "sec:new",
        "kind": "method",
        "text": "**NewTerm** changed the source.",
    }), encoding="utf-8")

    with pytest.raises(SystemExit, match="source|proposal"):
        _run_review(tmp_path, monkeypatch, [proposal["candidates"][0]["term"]])


def test_triage_requires_reviewed_shortlist_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_proposal(tmp_path, monkeypatch, _records())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plan_glossary.py",
            "--terms",
            '["MoE"]',
            "--source-manifest",
            str(tmp_path / "paper_source_manifest.json"),
        ],
    )

    with pytest.raises(SystemExit, match="reviewed shortlist|--reviewed-shortlist"):
        main()


def test_triage_uses_reviewed_surface_forms_and_preserves_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:method",
            "kind": "method",
            "title": "Method",
            "page_start": 1,
            "text": "**ReAct** and **ＲｅＡｃｔ** are equivalent source spellings.",
        }
    ]
    proposal = _run_proposal(tmp_path, monkeypatch, records)
    reviewed = _run_review(tmp_path, monkeypatch, ["ReAct"])

    triaged = _run_triage(tmp_path, monkeypatch, ["ReAct"])

    assert triaged["terms"][0]["surface_forms"] == ["ReAct", "ＲｅＡｃｔ"]
    assert triaged["terms"][0]["occurrences"] == 2
    assert triaged["provenance"]["proposal"] == proposal["provenance"]
    assert triaged["provenance"]["review"] == reviewed["provenance"]
    assert triaged["provenance"]["selection_sha256"]


@pytest.mark.parametrize(
    "selection",
    [["unknown"], ["ReAct|invented-alias"], "全部写入", "1", '["1"]'],
)
def test_triage_rejects_names_outside_review_or_unresolved_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: list[str] | str,
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    _run_review(tmp_path, monkeypatch, [proposal["candidates"][0]["term"]])

    with pytest.raises(SystemExit, match="shortlist|Resolve|exact"):
        _run_triage(tmp_path, monkeypatch, selection)


@pytest.mark.parametrize("field", ["reviewed_shortlist", "provenance"])
def test_triage_rejects_tampered_reviewed_candidate_or_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    name = proposal["candidates"][0]["term"]
    reviewed = _run_review(tmp_path, monkeypatch, [name])
    if field == "reviewed_shortlist":
        reviewed[field][0]["surface_forms"] = ["invented"]
    else:
        reviewed[field]["review_sha256"] = "0" * 64
    (tmp_path / "glossary_reviewed.json").write_text(
        json.dumps(reviewed, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="review|proposal|identity"):
        _run_triage(tmp_path, monkeypatch, [name])


def test_triage_rejects_reviewed_artifact_after_source_proposal_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    name = proposal["candidates"][0]["term"]
    _run_review(tmp_path, monkeypatch, [name])
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text(
        raw.read_text(encoding="utf-8")
        + "\n"
        + json.dumps(
            {
                "record_type": "section",
                "section_id": "sec:changed",
                "kind": "method",
                "text": "**ChangedTerm** changes the proposal source.",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="source|proposal|review"):
        _run_triage(tmp_path, monkeypatch, [name])


def test_triage_rejects_reviewed_artifact_from_another_paper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proposal = _run_proposal(tmp_path, monkeypatch, _records())
    name = proposal["candidates"][0]["term"]
    _run_review(tmp_path, monkeypatch, [name])
    manifest = tmp_path / "paper_source_manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["paper_id"] = "paper-2"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="proposal|review"):
        _run_triage(tmp_path, monkeypatch, [name])
