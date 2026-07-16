from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import glossary_common
from conftest import build_current_inventory, write_current_workflow
from glossary_common import elapsed_ms
from glossary_config import configure_terms_dir, validate_article
from lint_glossary import lint_term_file_text
from write_glossary_terms import render_term_file


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _run_writer_cli(
    tmp_path: Path,
    entries: dict,
    inventory: dict,
    config_path: Path,
    source_manifest: Path,
    reviewed_shortlist: Path,
    triage: Path,
    article: Path | None = None,
) -> dict:
    glossary_path = tmp_path / "writer_glossary.json"
    inventory_path = tmp_path / "writer_inventory.json"
    output_path = tmp_path / "writer_output.json"
    glossary_path.write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False), encoding="utf-8"
    )
    arguments = [
        sys.executable,
        str(SCRIPTS_DIR / "write_glossary_terms.py"),
        "--glossary",
        str(glossary_path),
        "--inventory",
        str(inventory_path),
        "--config-path",
        str(config_path),
        "--source-manifest",
        str(source_manifest),
        "--reviewed-shortlist",
        str(reviewed_shortlist),
        "--triage",
        str(triage),
        "--output",
        str(output_path),
    ]
    if article is not None:
        arguments.extend(["--article", str(article)])
    subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_linker_cli(
    tmp_path: Path,
    article: Path,
    expected_sha256: str,
    config_path: Path,
    source_manifest: Path,
    reviewed_shortlist: Path,
    triage: Path,
) -> dict:
    output_path = tmp_path / "linker_output.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "link_glossary_terms.py"),
            "--input",
            str(article),
            "--write-result",
            str(tmp_path / "writer_output.json"),
            "--expected-sha256",
            expected_sha256,
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(source_manifest),
            "--reviewed-shortlist",
            str(reviewed_shortlist),
            "--triage",
            str(triage),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_elapsed_ms_returns_non_negative_integer(monkeypatch) -> None:
    monkeypatch.setattr(glossary_common, "perf_counter", lambda: 2.125)

    assert elapsed_ms(2.0) == 125
    assert elapsed_ms(3.0) == 0
    assert isinstance(elapsed_ms(2.0), int)


def test_complete_selected_flow_creates_enriches_links_and_lints(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    article = vault / "Chapter.md"
    article.write_text(
        "# Agent Patterns\n\nReAct and Reflection are two agent patterns.\n",
        encoding="utf-8",
    )
    terms_dir = vault / "book" / "Glossary"
    config_path = tmp_path / "config.json"
    config = configure_terms_dir(terms_dir, config_path)
    article_info = validate_article(article, config)

    reflection = terms_dir / "Reflection.md"
    reflection.write_text(
        render_term_file(
            {
                "name": "Reflection",
                "aliases": ["self-reflection"],
                "definition": "An agent pattern that reviews prior results.",
                "confidence": "\u9ad8",
                "occurrence": "Earlier source evidence.",
            },
            "Earlier Chapter",
        ),
        encoding="utf-8",
    )
    selected = [
        {"term": "ReAct", "surface_forms": ["ReAct"]},
        {"term": "Reflection", "surface_forms": ["Reflection"]},
    ]
    workflow = write_current_workflow(
        tmp_path / "workflow", [item["term"] for item in selected]
    )
    inventory = build_current_inventory(workflow, terms_dir)
    entries = {
        "entries": [
            {
                "name": "ReAct",
                "aliases": ["Reasoning and Acting"],
                "operation": "create",
                "definition": "An agent pattern that interleaves reasoning and action.",
                "confidence": "\u9ad8",
                "occurrence": "The chapter introduces ReAct.",
            },
            {
                "name": "Reflection",
                "aliases": ["self-reflection"],
                "operation": "enrich",
                "elaboration": "The agent uses feedback to improve a prior result.",
                "intuition": "Review the last attempt before trying again.",
                "distinction": "Unlike ReAct, it focuses on reviewing prior output.",
                "occurrence": "The chapter presents Reflection as an agent pattern.",
            },
        ]
    }

    write_result = _run_writer_cli(
        tmp_path,
        entries,
        inventory,
        config_path,
        workflow["manifest_path"],
        workflow["review_path"],
        workflow["triage_path"],
        article,
    )
    assert write_result["script"] == "write_glossary_terms.py"
    assert write_result["terms_dir"] == str(terms_dir.resolve())
    link_result = _run_linker_cli(
        tmp_path,
        article,
        article_info["article_sha256"],
        config_path,
        workflow["manifest_path"],
        workflow["review_path"],
        workflow["triage_path"],
    )
    changed_notes = [
        Path(item["file"])
        for item in write_result["results"]
        if item["action"] in {"created", "enriched", "updated"}
    ]
    lint_results = [
        lint_term_file_text(path.read_text(encoding="utf-8-sig"))
        for path in changed_notes
    ]

    assert [item["action"] for item in write_result["results"]] == [
        "created",
        "enriched",
    ]
    assert link_result["summary"] == {
        "linked": 2,
        "already_linked": 0,
        "not_found": 0,
    }
    article_text = article.read_text(encoding="utf-8")
    assert "[[ReAct]]" in article_text
    assert "[[Reflection]]" in article_text
    assert len(changed_notes) == 2
    assert all(result["passes"] for result in lint_results)


def test_model_only_alias_is_note_metadata_but_never_an_article_match_form(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    article = vault / "Chapter.md"
    article.write_text("# Paper\n\nReasoning and Acting appears here.\n", encoding="utf-8")
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    config = configure_terms_dir(terms_dir, config_path)
    article_info = validate_article(article, config)
    workflow = write_current_workflow(
        tmp_path / "workflow",
        ["ReAct"],
        source_text="**ReAct** and **\uff32\uff45\uff21\uff43\uff54** are equivalent forms.",
    )
    inventory = build_current_inventory(workflow, terms_dir)

    write_result = _run_writer_cli(
        tmp_path,
        {
            "entries": [
                {
                    "name": "ReAct",
                    "aliases": ["Reasoning and Acting"],
                    "operation": "create",
                    "definition": "A reasoning and acting pattern.",
                    "confidence": "高",
                    "occurrence": "The paper uses ReAct.",
                }
            ]
        },
        inventory,
        config_path,
        workflow["manifest_path"],
        workflow["review_path"],
        workflow["triage_path"],
        article,
    )

    link_result = _run_linker_cli(
        tmp_path,
        article,
        article_info["article_sha256"],
        config_path,
        workflow["manifest_path"],
        workflow["review_path"],
        workflow["triage_path"],
    )

    assert write_result["results"][0]["forms"] == ["ReAct", "ＲｅＡｃｔ"]
    assert '  - "Reasoning and Acting"' in (terms_dir / "ReAct.md").read_text(
        encoding="utf-8"
    )
    assert link_result["summary"] == {
        "linked": 0,
        "already_linked": 0,
        "not_found": 1,
    }
    assert "[[" not in article.read_text(encoding="utf-8")


def test_grounded_equivalent_form_survives_the_complete_artifact_chain(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "paper_raw_sections.jsonl"
    raw.write_text(
        json.dumps(
            {
                "record_type": "section",
                "section_id": "sec:method",
                "kind": "method",
                "title": "Method",
                "text": "**ReAct** and **ＲｅＡｃｔ** are equivalent source spellings.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "paper_source_manifest.json"
    manifest.write_text(
        json.dumps({"paper_id": "paper-1", "raw_sections_path": str(raw)}),
        encoding="utf-8",
    )
    proposal = tmp_path / "proposal.json"
    reviewed = tmp_path / "reviewed.json"
    triage = tmp_path / "triage.json"
    inventory_path = tmp_path / "inventory.json"
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "terms"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)

    commands = [
        [
            sys.executable,
            str(SCRIPTS_DIR / "plan_glossary.py"),
            "--propose",
            "--source-manifest",
            str(manifest),
            "--output",
            str(proposal),
        ],
        [
            sys.executable,
            str(SCRIPTS_DIR / "plan_glossary.py"),
            "--review-proposal",
            str(proposal),
            "--reviewed-terms",
            '["ReAct"]',
            "--source-manifest",
            str(manifest),
            "--output",
            str(reviewed),
        ],
        [
            sys.executable,
            str(SCRIPTS_DIR / "plan_glossary.py"),
            "--reviewed-shortlist",
            str(reviewed),
            "--terms",
            '["ReAct"]',
            "--source-manifest",
            str(manifest),
            "--output",
            str(triage),
        ],
        [
            sys.executable,
            str(SCRIPTS_DIR / "inspect_glossary_library.py"),
            "--terms",
            str(triage),
            "--terms-dir",
            str(terms_dir),
            "--source-manifest",
            str(manifest),
            "--reviewed-shortlist",
            str(reviewed),
            "--output",
            str(inventory_path),
        ],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")

    proposal_payload = json.loads(proposal.read_text(encoding="utf-8"))
    reviewed_payload = json.loads(reviewed.read_text(encoding="utf-8"))
    triage_payload = json.loads(triage.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    write_result = _run_writer_cli(
        tmp_path,
        {
            "entries": [
                {
                    "name": "ReAct",
                    "aliases": [],
                    "operation": "create",
                    "definition": "A reasoning and acting pattern.",
                    "confidence": "高",
                    "occurrence": "The paper uses both forms.",
                }
            ]
        },
        inventory,
        config_path,
        manifest,
        reviewed,
        triage,
    )

    assert write_result["script"] == "write_glossary_terms.py"
    assert write_result["terms_dir"] == str(terms_dir.resolve())
    forms = ["ReAct", "ＲｅＡｃｔ"]
    assert proposal_payload["candidates"][0]["surface_forms"] == forms
    assert reviewed_payload["reviewed_shortlist"][0]["surface_forms"] == forms
    assert triage_payload["terms"][0]["surface_forms"] == forms
    assert inventory["results"][0]["surface_forms"] == forms
    assert write_result["results"][0]["forms"] == forms
