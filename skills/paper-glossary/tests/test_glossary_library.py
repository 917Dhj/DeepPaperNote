from __future__ import annotations

from copy import deepcopy
import json
import sys
from pathlib import Path

import pytest

from glossary_contracts import (
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_CONFIDENCE_VALUES,
    GLOSSARY_LABEL_CONFIDENCE,
    GLOSSARY_LABEL_DEFINITION,
    GLOSSARY_OCCURRENCE_HEADING,
)
from glossary_library import (
    add_missing_concept_fields,
    build_alias_index,
    inspect_selected_terms,
    missing_concept_fields,
    read_frontmatter_aliases,
)
from inspect_glossary_library import main as inspect_main
from conftest import build_triage_payload, write_current_workflow


def _triage_payload(terms: list[dict]) -> dict:
    return build_triage_payload(terms)


def _current_flags(workflow: dict) -> list[str]:
    return [
        "--source-manifest",
        str(workflow["manifest_path"]),
        "--reviewed-shortlist",
        str(workflow["review_path"]),
    ]


def _note(*, name: str, fields: dict[str, str], aliases: list[str] | None = None) -> str:
    aliases = aliases or []
    lines = ["---", "aliases:"]
    lines.extend(f'  - "{alias}"' for alias in aliases)
    lines.extend(["---", "", f"# {name}", "", f"## {GLOSSARY_CONCEPT_HEADING}"])
    labels = {
        "definition": GLOSSARY_LABEL_DEFINITION,
        "elaboration": "\u8be6\u89e3\uff1a",
        "intuition": "\u76f4\u89c9\uff1a",
        "distinction": "\u4e0e\u76f8\u90bb\u6982\u5ff5\u7684\u533a\u522b\uff1a",
        "confidence": GLOSSARY_LABEL_CONFIDENCE,
    }
    lines.extend(f"- {labels[field]}{value}" for field, value in fields.items())
    lines.extend(["", f"## {GLOSSARY_OCCURRENCE_HEADING}", "- [[OldPaper]]: old evidence", ""])
    return "\n".join(lines)


def test_inventory_classifies_alias_heading_and_new_notes(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "LLM.md").write_text(
        _note(
            name="LLM",
            aliases=["large language model"],
            fields={
                "definition": "definition",
                "confidence": GLOSSARY_CONFIDENCE_VALUES[1],
            },
        ),
        encoding="utf-8",
    )
    (terms_dir / "ReAct.md").write_text(
        _note(
            name="ReAct",
            fields={
                "definition": "definition",
                "elaboration": "elaboration",
                "intuition": "intuition",
                "confidence": GLOSSARY_CONFIDENCE_VALUES[0],
            },
        ),
        encoding="utf-8",
    )

    results = inspect_selected_terms(
        [
            {"term": "large language model", "surface_forms": ["LLM", "large language model"]},
            {"term": "ReAct", "surface_forms": ["ReAct"]},
            {"term": "Reflection", "surface_forms": ["Reflection"]},
        ],
        terms_dir,
    )

    by_term = {item["term"]: item for item in results}
    assert by_term["large language model"]["state"] == "existing_thin"
    assert by_term["large language model"]["file"] == str(terms_dir / "LLM.md")
    assert by_term["large language model"]["link_stem"] == "LLM"
    assert by_term["large language model"]["missing_fields"] == [
        "elaboration",
        "intuition",
        "distinction",
    ]
    assert by_term["ReAct"]["state"] == "existing_complete"
    assert by_term["Reflection"] == {
        "term": "Reflection",
        "surface_forms": ["Reflection"],
        "state": "new",
        "file": "",
        "link_stem": "Reflection",
        "missing_fields": [],
    }


def test_add_missing_concept_fields_preserves_existing_content_and_is_idempotent() -> None:
    original = _note(
        name="LLM",
        fields={
            "definition": "user definition",
            "confidence": GLOSSARY_CONFIDENCE_VALUES[1],
        },
    ).replace("- [[OldPaper]]: old evidence\n", "## Custom\nkeep this text\n")

    updated, fields_added = add_missing_concept_fields(
        original,
        {"elaboration": "new explanation", "intuition": "new intuition"},
    )

    assert fields_added == ["elaboration", "intuition"]
    assert "user definition" in updated
    assert "## Custom\nkeep this text\n" in updated
    assert updated.count("- \u8be6\u89e3\uff1anew explanation") == 1
    assert updated.count("- \u76f4\u89c9\uff1anew intuition") == 1
    assert updated.index("- \u8be6\u89e3\uff1anew explanation") < updated.index(
        f"- {GLOSSARY_LABEL_CONFIDENCE}{GLOSSARY_CONFIDENCE_VALUES[1]}"
    )
    repeated, repeated_fields = add_missing_concept_fields(
        updated,
        {"elaboration": "ignored", "intuition": "ignored"},
    )
    assert repeated == updated
    assert repeated_fields == []


def test_add_missing_concept_fields_appends_missing_concept_section() -> None:
    original = "# Existing\n\n## Custom\nkeep this text\n"

    updated, fields_added = add_missing_concept_fields(
        original,
        {
            "definition": "definition",
            "confidence": GLOSSARY_CONFIDENCE_VALUES[0],
        },
    )

    assert updated.startswith(original)
    assert fields_added == ["definition", "confidence"]
    assert f"## {GLOSSARY_CONCEPT_HEADING}" in updated
    assert missing_concept_fields(updated) == ["elaboration", "intuition", "distinction"]


def test_inspect_cli_emits_inventory_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(tmp_path / "workflow", ["Reflection"])
    selected = workflow["triage_path"]
    output = tmp_path / "inventory.json"
    triage = workflow["triage"]
    monkeypatch.setattr(
        "sys.argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
            "--output",
            str(output),
        ],
    )

    inspect_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload.pop("elapsed_ms"), int)
    assert payload == {
        "status": "ok",
        "script": "inspect_glossary_library.py",
        "paper_id": triage["paper_id"],
        "provenance": triage["provenance"],
        "results": [
            {
                "term": "Reflection",
                "surface_forms": ["Reflection"],
                "state": "new",
                "file": "",
                "link_stem": "Reflection",
                "missing_fields": [],
            }
        ],
    }


def test_inspect_cli_preserves_selection_provenance_and_exact_surface_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(
        tmp_path / "workflow",
        ["ReAct"],
        source_text="**ReAct** and **ＲｅＡｃｔ** are equivalent forms.",
    )
    triage = workflow["triage_path"]
    triage_payload = workflow["triage"]
    provenance = triage_payload["provenance"]
    output = tmp_path / "inventory.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(triage),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
            "--output",
            str(output),
        ],
    )

    inspect_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provenance"] == provenance
    assert payload["results"][0]["surface_forms"] == ["ReAct", "ＲｅＡｃｔ"]


def test_inspect_cli_rejects_missing_selection_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    selected = tmp_path / "selected.json"
    selected.write_text(
        json.dumps({"selected": [{"term": "ReAct", "surface_forms": ["ReAct"]}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
        ],
    )

    with pytest.raises(SystemExit, match="triage|provenance"):
        inspect_main()


def test_inspect_cli_rejects_surface_forms_changed_after_triage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(
        tmp_path / "workflow",
        ["ReAct"],
        source_text="**ReAct** and **ＲｅＡｃｔ** are equivalent forms.",
    )
    selected = tmp_path / "triage.json"
    triage = deepcopy(workflow["triage"])
    triage["terms"][0]["surface_forms"].append("invented alias")
    selected.write_text(json.dumps(triage, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
        ],
    )

    with pytest.raises(SystemExit, match="selection|provenance|surface_forms"):
        inspect_main()


def test_inventory_cli_rejects_source_changed_after_triage_before_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    workflow["raw_path"].write_text(
        workflow["raw_path"].read_text(encoding="utf-8")
        + json.dumps(
            {
                "record_type": "section",
                "section_id": "sec:changed",
                "kind": "body",
                "title": "Changed",
                "text": "Reflection was added after triage.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    sentinel = terms_dir / "Sentinel.md"
    sentinel.write_bytes(b"# Sentinel\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(workflow["triage_path"]),
            "--terms-dir",
            str(terms_dir),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="current|source|review|proposal"):
        inspect_main()

    assert sentinel.read_bytes() == b"# Sentinel\n"


def test_inventory_cli_rejects_fully_recomputed_forged_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    forged = tmp_path / "forged-triage.json"
    forged.write_text(
        json.dumps(
            build_triage_payload(
                [{"term": "Reflection", "surface_forms": ["Reflection"]}],
                paper_id="other-paper",
            )
        ),
        encoding="utf-8",
    )
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(forged),
            "--terms-dir",
            str(terms_dir),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="current|source|review|proposal|paper"):
        inspect_main()

    assert list(terms_dir.iterdir()) == []


@pytest.mark.parametrize("field", ["paper_id", "source_sha256", "proposal_sha256"])
def test_inventory_rejects_mismatched_proposal_review_common_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    triage = deepcopy(workflow["triage"])
    triage["provenance"]["review"][field] = (
        "other-paper" if field == "paper_id" else "0" * 64
    )
    selected = tmp_path / "triage.json"
    selected.write_text(json.dumps(triage), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
        ],
    )

    with pytest.raises(SystemExit, match="proposal|review|provenance|paper|source"):
        inspect_main()


@pytest.mark.parametrize("stage", ["proposal", "review"])
def test_inventory_rejects_digest_not_bound_to_embedded_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    triage = deepcopy(workflow["triage"])
    if stage == "proposal":
        triage["provenance"]["proposal"]["summary"]["pool_candidates"] = 2
    else:
        triage["provenance"]["review"]["reviewed_shortlist"].append(
            {"term": "Reflection", "surface_forms": ["Reflection"]}
        )
    selected = tmp_path / "triage.json"
    selected.write_text(json.dumps(triage), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
        ],
    )

    with pytest.raises(SystemExit, match="proposal|review|digest|provenance"):
        inspect_main()


@pytest.mark.parametrize("change", ["term", "append_form", "reorder_forms"])
def test_inventory_rejects_selected_term_or_forms_absent_from_reviewed_shortlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    workflow = write_current_workflow(
        tmp_path / "workflow",
        ["ReAct"],
        source_text="**ReAct** and **\uff32\uff45\uff21\uff43\uff54** are equivalent forms.",
    )
    triage = deepcopy(workflow["triage"])
    if change == "term":
        triage["terms"][0]["term"] = "Reflection"
        triage["terms"][0]["surface_forms"] = ["Reflection"]
    elif change == "append_form":
        triage["terms"][0]["surface_forms"].append("invented")
    else:
        triage["terms"][0]["surface_forms"].reverse()
    review_sha = triage["provenance"]["review"]["review_sha256"]
    from glossary_common import selection_sha256

    triage["provenance"]["selection_sha256"] = selection_sha256(
        review_sha, triage["terms"]
    )
    selected = tmp_path / "triage.json"
    selected.write_text(json.dumps(triage, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_glossary_library.py",
            "--terms",
            str(selected),
            "--terms-dir",
            str(terms_dir),
            *_current_flags(workflow),
        ],
    )

    with pytest.raises(SystemExit, match="reviewed|shortlist|surface_forms|provenance"):
        inspect_main()


@pytest.mark.parametrize(
    "selected",
    [
        [{"term": "ReAct"}],
        [{"term": "ReAct", "surface_forms": "ReAct"}],
        [{"term": "ReAct", "surface_forms": ["ReAct", 7]}],
        [{"term": "ReAct", "surface_forms": [" ReAct"]}],
        [{"term": "ReAct", "surface_forms": ["ＲｅＡｃｔ"]}],
    ],
)
def test_inventory_rejects_malformed_or_altered_surface_forms(
    tmp_path: Path, selected: list[dict]
) -> None:
    with pytest.raises(SystemExit, match="surface_forms"):
        inspect_selected_terms(selected, tmp_path / "terms")


def test_inventory_rejects_unreadable_existing_note(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "ReAct.md").write_bytes(b"\xff\xfe\x00")

    with pytest.raises(SystemExit, match="Unable to read glossary note.*ReAct.md"):
        inspect_selected_terms(
            [{"term": "ReAct", "surface_forms": ["ReAct"]}],
            terms_dir,
        )


def test_inventory_rejects_unclosed_frontmatter(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "ReAct.md").write_text(
        "---\naliases:\n  - ReAct\n# ReAct\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Unclosed frontmatter.*ReAct.md"):
        build_alias_index(terms_dir)


def test_inventory_rejects_malformed_quoted_alias(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "ReAct.md").write_text(
        "---\naliases:\n  - \"unterminated\n---\n# ReAct\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Malformed frontmatter scalar"):
        build_alias_index(terms_dir)


def test_inventory_rejects_normalized_alias_collision(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "Alpha.md").write_text(
        _note(name="Alpha", aliases=["Shared   Alias"], fields={}),
        encoding="utf-8",
    )
    (terms_dir / "Beta.md").write_text(
        _note(name="Beta", aliases=["shared alias"], fields={}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Glossary key collision.*shared alias"):
        build_alias_index(terms_dir)


def test_blank_field_is_missing_when_followed_by_another_label() -> None:
    text = (
        f"# Empty\n\n## {GLOSSARY_CONCEPT_HEADING}\n"
        f"- {GLOSSARY_LABEL_DEFINITION}\n"
        f"- {GLOSSARY_LABEL_CONFIDENCE}{GLOSSARY_CONFIDENCE_VALUES[0]}\n"
    )

    assert "definition" in missing_concept_fields(text)


def test_frontmatter_alias_subset_supports_quoted_and_unquoted_scalars() -> None:
    text = (
        "---\n"
        "aliases: [Plain, \"Double, alias\", 'Single ''quoted'' alias']\n"
        "---\n"
        "# Term\n"
    )

    assert read_frontmatter_aliases(text) == [
        "Plain",
        "Double, alias",
        "Single 'quoted' alias",
    ]


def test_inventory_rejects_unclosed_single_quoted_alias(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "ReAct.md").write_text(
        "---\naliases:\n  - 'unterminated\n---\n# ReAct\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Malformed frontmatter scalar"):
        build_alias_index(terms_dir)


def test_inventory_rejects_scalar_alias_structure(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "ReAct.md").write_text(
        "---\naliases: ScalarAlias\n---\n# ReAct\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Unsupported aliases metadata"):
        build_alias_index(terms_dir)


def test_inventory_rejects_one_item_matching_multiple_files(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "Alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (terms_dir / "Beta.md").write_text("# Beta\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Selected forms resolve to multiple glossary notes"):
        inspect_selected_terms(
            [{"term": "Alpha", "surface_forms": ["Alpha", "Beta"]}],
            terms_dir,
        )
