from __future__ import annotations

from copy import deepcopy
import json
import os
import sys
from pathlib import Path

import pytest
import write_glossary_terms as writer_module
from conftest import (
    bind_inventory_results,
    build_current_inventory,
    build_inventory_payload,
    write_current_workflow,
)

from glossary_config import configure_terms_dir
from glossary_common import selection_sha256
from glossary_contracts import (
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_OCCURRENCE_HEADING,
)
from glossary_library import inspect_selected_terms
from lint_glossary import GLOSSARY_DISCLAIMER, lint_term_file_text, main as lint_main
from write_glossary_terms import (
    append_occurrence,
    build_alias_index,
    main as write_main,
    render_term_file,
    safe_term_filename,
    upsert_term_file,
    write_glossary_entries,
)

ENTRY = {
    "name": "KL 散度",
    "aliases": ["KL divergence", "相对熵"],
    "routing": "needs_explanation",
    "definition": "衡量两个概率分布差异的非对称度量。",
    "elaboration": "常用于把学生分布拉近教师分布。",
    "intuition": "把 Q 当作近似 P 时的信息损失。",
    "confidence": "高",
    "occurrence": "方法 式(4)，第 3-6 页",
}


def _codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def _inventory(results: list[dict]) -> dict:
    return bind_inventory_results(results)


def test_render_term_file_is_lintable() -> None:
    text = render_term_file(ENTRY, "CAD-MoE")
    result = lint_term_file_text(text)
    assert result["passes"] is True
    assert "aliases:" in text and "KL divergence" in text
    assert "[[CAD-MoE]]" in text


def test_safe_term_filename_strips_illegal_chars() -> None:
    assert "/" not in safe_term_filename("KL/散度")
    assert ":" not in safe_term_filename("KL: 散度?")
    assert safe_term_filename("KL 散度") == "KL 散度"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("C#", "C＃"),
        ("term^block", "term＾block"),
        ("[term]", "［term］"),
        ("left|right", "left｜right"),
        ("key:value", "key：value"),
        ("100%", "100％"),
    ],
)
def test_safe_term_filename_translates_obsidian_link_syntax(
    name: str, expected: str
) -> None:
    assert safe_term_filename(name) == expected


def test_writer_preserves_exact_name_when_safe_link_stem_differs(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    selected = [{"term": "C#", "surface_forms": ["C#"]}]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))

    result = write_glossary_entries(
        {
            "entries": [
                {
                    "name": "C#",
                    "operation": "create",
                    "definition": "A programming language.",
                    "confidence": "高",
                    "occurrence": "Paper evidence.",
                }
            ]
        },
        inventory,
        terms_dir,
        "Paper",
    )

    note = terms_dir / "C＃.md"
    assert result["results"][0]["link_stem"] == "C＃"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    assert '  - "C#"' in text
    assert "# C#\n" in text
    existing = inspect_selected_terms(selected, terms_dir)[0]
    assert existing["file"] == str(note)
    assert existing["link_stem"] == "C＃"


def test_writer_rejects_unsafe_existing_stem_before_batch_write(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    unsafe = terms_dir / "C#.md"
    unsafe.write_text(
        render_term_file({**ENTRY, "name": "C#", "aliases": []}, "Paper"),
        encoding="utf-8",
    )
    before = unsafe.read_bytes()
    inventory = _inventory(
        [
            {
                "term": "Created",
                "surface_forms": ["Created"],
                "state": "new",
                "file": "",
                "link_stem": "Created",
                "missing_fields": [],
            },
            {
                "term": "C#",
                "surface_forms": ["C#"],
                "state": "existing_complete",
                "file": str(unsafe),
                "link_stem": "C#",
                "missing_fields": [],
            },
        ]
    )

    with pytest.raises(SystemExit, match=r"rename.*C＃\.md"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": name,
                        "operation": "create" if name == "Created" else "reuse",
                        "definition": "definition",
                        "confidence": "高",
                        "occurrence": "evidence",
                    }
                    for name in ("Created", "C#")
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert unsafe.read_bytes() == before
    assert not (terms_dir / "Created.md").exists()
    assert not (terms_dir / "C＃.md").exists()


def test_writer_and_lint_require_exact_confidence_value(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    selected = [{"term": "ReAct", "surface_forms": ["ReAct"]}]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))

    with pytest.raises(SystemExit, match="valid confidence"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "Reasoning and acting.",
                        "confidence": "不高",
                        "occurrence": "Paper evidence.",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    invalid = render_term_file({**ENTRY, "confidence": "不高"}, "Paper")
    assert "term_confidence_invalid" in _codes(lint_term_file_text(invalid))
    assert not terms_dir.exists()


def test_upsert_creates_then_dedupes_by_alias(tmp_path: Path) -> None:
    terms_dir = tmp_path / "术语"
    index = build_alias_index(terms_dir)

    r1 = upsert_term_file(ENTRY, "CAD-MoE", terms_dir, index)
    assert r1["action"] == "created"

    entry2 = {"name": "KL divergence", "definition": "...", "confidence": "中", "occurrence": "eq 3"}
    r2 = upsert_term_file(entry2, "OtherPaper", terms_dir, index)
    assert r2["action"] == "updated"
    assert r1["file"] == r2["file"]

    files = list(terms_dir.glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "[[CAD-MoE]]" in text and "[[OtherPaper]]" in text


def test_upsert_idempotent_for_same_paper(tmp_path: Path) -> None:
    terms_dir = tmp_path / "术语"
    index = build_alias_index(terms_dir)
    upsert_term_file(ENTRY, "CAD-MoE", terms_dir, index)
    again = upsert_term_file(ENTRY, "CAD-MoE", terms_dir, index)
    assert again["action"] == "unchanged"
    text = (terms_dir / f"{safe_term_filename(ENTRY['name'])}.md").read_text(encoding="utf-8")
    assert text.count("[[CAD-MoE]]") == 1


def test_upsert_rebuilt_index_dedupes_sanitized_filename(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    entry = {**ENTRY, "name": "A/B", "aliases": []}

    first = upsert_term_file(entry, "PaperOne", terms_dir, build_alias_index(terms_dir))
    second = upsert_term_file(entry, "PaperOne", terms_dir, build_alias_index(terms_dir))

    assert second["action"] == "unchanged"
    assert second["file"] == first["file"]
    assert sorted(path.name for path in terms_dir.glob("*.md")) == ["A B.md"]


def test_upsert_does_not_overwrite_sanitized_filename_collision(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    index = build_alias_index(terms_dir)
    first = {**ENTRY, "name": "A/B", "aliases": []}
    second = {**ENTRY, "name": "A:B", "aliases": []}

    r1 = upsert_term_file(first, "PaperOne", terms_dir, index)
    r2 = upsert_term_file(second, "PaperTwo", terms_dir, index)

    assert r1["file"] != r2["file"]
    assert len(list(terms_dir.glob("*.md"))) == 2
    assert "# A/B" in Path(r1["file"]).read_text(encoding="utf-8")
    assert "# A:B" in Path(r2["file"]).read_text(encoding="utf-8")


def test_render_term_file_quotes_frontmatter_alias_strings() -> None:
    entry = {
        **ENTRY,
        "name": "Term",
        "aliases": ["foo: bar", "[bracket]", 'quote "value"'],
    }

    text = render_term_file(entry, "PaperOne")

    assert '  - "foo: bar"' in text
    assert '  - "[bracket]"' in text
    assert '  - "quote \\"value\\""' in text


def test_append_occurrence_inserts_inside_existing_occurrence_section() -> None:
    text = render_term_file(ENTRY, "PaperOne") + "\n## Extra\nbody\n"

    updated = append_occurrence(text, {"occurrence": "new evidence"}, "PaperTwo")

    occurrence = updated.split(f"## {GLOSSARY_OCCURRENCE_HEADING}", 1)[1].split(
        "\n## Extra", 1
    )[0]
    assert "[[PaperTwo]]" in occurrence
    assert updated.index("[[PaperTwo]]") < updated.index("## Extra")


def test_lint_main_rejects_empty_terms_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "lint.json"
    empty_terms = tmp_path / "empty"
    empty_terms.mkdir()
    monkeypatch.setattr(
        "sys.argv",
        ["lint_glossary.py", "--terms-dir", str(empty_terms), "--output", str(output)],
    )

    with pytest.raises(SystemExit) as exc:
        lint_main()

    assert "No glossary markdown files found" in str(exc.value)
    assert not output.exists()


def test_lint_main_accepts_repeated_inputs_and_lints_exact_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "First.md"
    second = tmp_path / "Second.md"
    ignored = tmp_path / "Ignored.md"
    for path, name in ((first, "First"), (second, "Second"), (ignored, "Ignored")):
        path.write_text(render_term_file({**ENTRY, "name": name}, "Paper"), encoding="utf-8")
    output = tmp_path / "lint.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lint_glossary.py",
            "--input",
            str(first),
            "--input",
            str(second),
            "--output",
            str(output),
        ],
    )

    lint_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    assert [item["path"] for item in payload["files"]] == [
        str(first.resolve()),
        str(second.resolve()),
    ]
    assert payload["summary"] == {"total": 2, "passed": 2, "failed": 0}


def test_lint_main_rejects_missing_terms_dir_even_with_valid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = tmp_path / "Term.md"
    note.write_text(render_term_file({**ENTRY, "name": "Term"}, "Paper"), encoding="utf-8")
    missing_terms = tmp_path / "missing"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lint_glossary.py",
            "--input",
            str(note),
            "--terms-dir",
            str(missing_terms),
        ],
    )

    with pytest.raises(SystemExit, match="--terms-dir must be an existing directory"):
        lint_main()


def test_lint_main_rejects_file_terms_dir_even_with_valid_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = tmp_path / "Term.md"
    note.write_text(render_term_file({**ENTRY, "name": "Term"}, "Paper"), encoding="utf-8")
    terms_file = tmp_path / "not-a-directory"
    terms_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lint_glossary.py",
            "--input",
            str(note),
            "--terms-dir",
            str(terms_file),
        ],
    )

    with pytest.raises(SystemExit, match="--terms-dir must be an existing directory"):
        lint_main()


def test_lint_main_terms_dir_only_emits_elapsed_ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "Term.md"
    note.write_text(render_term_file({**ENTRY, "name": "Term"}, "Paper"), encoding="utf-8")
    output = tmp_path / "lint.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lint_glossary.py",
            "--terms-dir",
            str(terms_dir),
            "--output",
            str(output),
        ],
    )

    lint_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    assert [item["path"] for item in payload["files"]] == [str(note.resolve())]


def test_lint_main_merges_terms_dir_and_deduplicates_resolved_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    first = terms_dir / "First.md"
    second = terms_dir / "Second.md"
    for path, name in ((first, "First"), (second, "Second")):
        path.write_text(render_term_file({**ENTRY, "name": name}, "Paper"), encoding="utf-8")
    output = tmp_path / "lint.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lint_glossary.py",
            "--input",
            str(first),
            "--input",
            str(first.parent / "." / first.name),
            "--terms-dir",
            str(terms_dir),
            "--output",
            str(output),
        ],
    )

    lint_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    assert [item["path"] for item in payload["files"]] == [
        str(first.resolve()),
        str(second.resolve()),
    ]
    assert payload["summary"]["total"] == 2


def test_write_cli_emits_elapsed_ms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    glossary = tmp_path / "glossary.json"
    inventory = tmp_path / "inventory.json"
    output = tmp_path / "write.json"
    glossary.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "Reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Chapter evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary),
            "--inventory",
            str(inventory),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
            "--output",
            str(output),
        ],
    )

    write_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload["elapsed_ms"], int)
    assert payload["elapsed_ms"] >= 0
    assert payload["results"][0]["action"] == "created"


@pytest.mark.parametrize(
    ("authorized_names", "generated_names", "source_text"),
    [
        (["ReAct", "Reflection"], ["Reflection", "ReAct"], None),
        (
            ["ReAct"],
            ["react"],
            "**ReAct** and **react** are the same paper concept.",
        ),
    ],
    ids=["reversed-entries", "case-only-name"],
)
def test_writer_cli_rejects_generated_mapping_drift_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authorized_names: list[str],
    generated_names: list[str],
    source_text: str | None,
) -> None:
    workflow = write_current_workflow(
        tmp_path / "workflow", authorized_names, source_text=source_text
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    terms_dir.mkdir()
    (terms_dir / ".sentinel").write_bytes(b"unchanged glossary directory\n")
    if source_text is not None:
        (terms_dir / "ReAct.md").write_text(
            render_term_file(
                {
                    "name": "ReAct",
                    "aliases": ["react"],
                    "definition": "A reasoning and acting pattern.",
                    "elaboration": "It interleaves reasoning with actions.",
                    "intuition": "Think, act, and observe repeatedly.",
                    "distinction": "It is not a single reasoning pass.",
                    "confidence": "\u9ad8",
                    "occurrence": "Existing occurrence.",
                },
                "ExistingPaper",
            ),
            encoding="utf-8",
        )
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)), encoding="utf-8"
    )
    glossary_path = tmp_path / "generated-glossary.json"
    generated_entries = []
    for name in generated_names:
        entry = {
            "name": name,
            "operation": "reuse" if source_text is not None else "create",
            "occurrence": f"Occurrence for {name}.",
        }
        if entry["operation"] == "create":
            entry.update(
                {
                    "definition": f"Definition for {name}.",
                    "confidence": "\u9ad8",
                }
            )
        generated_entries.append(entry)
    glossary_path.write_text(
        json.dumps({"entries": generated_entries}),
        encoding="utf-8",
    )
    before = {
        path.relative_to(terms_dir): path.read_bytes()
        for path in terms_dir.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary_path),
            "--inventory",
            str(inventory_path),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="ordered inventory"):
        try:
            write_main()
        finally:
            after = {
                path.relative_to(terms_dir): path.read_bytes()
                for path in terms_dir.rglob("*")
                if path.is_file()
            }
            assert after == before


@pytest.mark.parametrize(
    ("with_article", "expected_paper_link"),
    [(True, "Paper"), (False, "paper-fixture")],
    ids=["article", "glossary-only"],
)
def test_writer_cli_derives_and_binds_backlink_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_article: bool,
    expected_paper_link: str,
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    article = vault / "Paper.md"
    article.write_text("# Paper\n\nReAct text.\n", encoding="utf-8")
    glossary_path = tmp_path / "glossary.json"
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "writer.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "A reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Paper evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory_path.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)), encoding="utf-8"
    )
    arguments = [
        "write_glossary_terms.py",
        "--glossary",
        str(glossary_path),
        "--inventory",
        str(inventory_path),
        "--config-path",
        str(config_path),
        "--source-manifest",
        str(workflow["manifest_path"]),
        "--reviewed-shortlist",
        str(workflow["review_path"]),
        "--triage",
        str(workflow["triage_path"]),
        "--output",
        str(output_path),
    ]
    if with_article:
        arguments.extend(["--article", str(article)])
    monkeypatch.setattr(sys, "argv", arguments)

    write_main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["context"] == {
        "paper_id": "paper-fixture",
        "paper_link": expected_paper_link,
        "article_path": str(article.resolve()) if with_article else "",
    }
    assert len(payload["triage_sha256"]) == 64
    assert len(payload["mappings_sha256"]) == 64
    assert f"[[{expected_paper_link}]]" in (terms_dir / "ReAct.md").read_text(
        encoding="utf-8"
    )


def test_writer_cli_rejects_unsafe_glossary_only_paper_id_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(
        tmp_path / "workflow", ["ReAct"], paper_id="unsafe|paper"
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    glossary_path = tmp_path / "glossary.json"
    inventory_path = tmp_path / "inventory.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory_path.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary_path),
            "--inventory",
            str(inventory_path),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="paper_id|wiki|backlink"):
        write_main()

    assert not (terms_dir / "ReAct.md").exists()


def test_writer_cli_rejects_changed_source_before_loading_generated_glossary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)), encoding="utf-8"
    )
    workflow["raw_path"].write_text(
        workflow["raw_path"].read_text(encoding="utf-8")
        + json.dumps(
            {
                "record_type": "section",
                "section_id": "sec:changed",
                "kind": "body",
                "title": "Changed",
                "text": "Source changed after inventory.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    malformed_glossary = tmp_path / "malformed-glossary.json"
    malformed_glossary.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(malformed_glossary),
            "--inventory",
            str(inventory_path),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="current|source|review|proposal"):
        write_main()

    assert not (terms_dir / "ReAct.md").exists()


def test_writer_cli_rejects_reviewed_but_unselected_forgery_before_loading_glossary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(
        tmp_path / "workflow",
        ["ReAct", "Reflection"],
        selected_names=["ReAct"],
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)

    reflection = next(
        item
        for item in workflow["review"]["reviewed_shortlist"]
        if item["term"] == "Reflection"
    )
    forged_results = inspect_selected_terms([reflection], terms_dir)
    forged_provenance = deepcopy(workflow["triage"]["provenance"])
    forged_provenance["selection_sha256"] = selection_sha256(
        forged_provenance["review"]["review_sha256"], forged_results
    )
    inventory_path = tmp_path / "forged-inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "inspect_glossary_library.py",
                "paper_id": workflow["triage"]["paper_id"],
                "provenance": forged_provenance,
                "results": forged_results,
            }
        ),
        encoding="utf-8",
    )
    glossary_path = tmp_path / "generated-glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "Reflection",
                        "operation": "create",
                        "definition": "A reflection step.",
                        "confidence": "\u9ad8",
                        "occurrence": "Forged occurrence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    generated_loaded = False
    real_loader = writer_module.maybe_load_json_record

    def tracked_loader(value: str) -> dict | None:
        nonlocal generated_loaded
        if value == str(glossary_path):
            generated_loaded = True
        return real_loader(value)

    monkeypatch.setattr(writer_module, "maybe_load_json_record", tracked_loader)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary_path),
            "--inventory",
            str(inventory_path),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="authorized|triage|selection"):
        write_main()

    assert generated_loaded is False
    assert not (terms_dir / "Reflection.md").exists()


@pytest.mark.parametrize("vault_root", [".", "C:drive-relative"])
def test_writer_cli_rejects_relative_vault_root_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    vault_root: str,
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    terms_dir.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"vault_root": vault_root, "terms_subdir": "Glossary"}),
        encoding="utf-8",
    )
    glossary_path = tmp_path / "glossary.json"
    inventory_path = tmp_path / "inventory.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory_path.write_text(
        json.dumps(build_current_inventory(workflow, terms_dir)), encoding="utf-8"
    )
    monkeypatch.chdir(vault)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary_path),
            "--inventory",
            str(inventory_path),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(workflow["manifest_path"]),
            "--reviewed-shortlist",
            str(workflow["review_path"]),
            "--triage",
            str(workflow["triage_path"]),
        ],
    )

    with pytest.raises(SystemExit, match="Invalid paper-glossary config object"):
        write_main()

    assert not (terms_dir / "ReAct.md").exists()


def test_write_cli_rejects_missing_config_before_creating_terms_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "arbitrary-destination"
    glossary = tmp_path / "glossary.json"
    inventory = tmp_path / "inventory.json"
    glossary.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "Reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Chapter evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(build_inventory_payload([{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary),
            "--inventory",
            str(inventory),
            "--config-path",
            str(tmp_path / "missing-config.json"),
            "--source-manifest",
            str(tmp_path / "unused-manifest.json"),
            "--reviewed-shortlist",
            str(tmp_path / "unused-review.json"),
            "--triage",
            str(tmp_path / "unused-triage.json"),
        ],
    )

    with pytest.raises(SystemExit, match="configuration"):
        write_main()

    assert not terms_dir.exists()


@pytest.mark.parametrize(
    "config_payload, terms_dir, error",
    [
        ("{", "Glossary", "Invalid paper-glossary config"),
        (
            {"vault_root": "{vault}", "terms_subdir": "Missing"},
            "Missing",
            "Configured Obsidian term directory",
        ),
        (
            {"vault_root": "{non_vault}", "terms_subdir": "Glossary"},
            "Glossary",
            "Configured Obsidian term directory",
        ),
        (
            {"vault_root": "{vault}", "terms_subdir": "../outside"},
            "../outside",
            "Configured Obsidian term directory",
        ),
    ],
    ids=["malformed", "stale", "non-obsidian", "outside-vault"],
)
def test_write_cli_rejects_invalid_config_before_mutating_glossary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config_payload: str | dict[str, str],
    terms_dir: str,
    error: str,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    non_vault = tmp_path / "not-a-vault"
    (non_vault / "Glossary").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    glossary = tmp_path / "glossary.json"
    inventory = tmp_path / "inventory.json"
    config_path = tmp_path / "config.json"
    glossary.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "Reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Chapter evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(
            build_inventory_payload(
                [{"term": "ReAct", "surface_forms": ["ReAct"]}], vault / "Glossary"
            )
        ),
        encoding="utf-8",
    )
    if isinstance(config_payload, str):
        config_path.write_text(config_payload, encoding="utf-8")
    else:
        config_path.write_text(
            json.dumps(
                {
                    key: value.format(vault=vault, non_vault=non_vault)
                    for key, value in config_payload.items()
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary),
            "--inventory",
            str(inventory),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(tmp_path / "unused-manifest.json"),
            "--reviewed-shortlist",
            str(tmp_path / "unused-review.json"),
            "--triage",
            str(tmp_path / "unused-triage.json"),
        ],
    )

    with pytest.raises(SystemExit, match=error):
        write_main()

    assert not (vault / "Glossary" / "ReAct.md").exists()
    assert not (non_vault / "Glossary" / "ReAct.md").exists()
    assert not (outside / "ReAct.md").exists()
    assert not (vault / terms_dir / "ReAct.md").exists()


@pytest.mark.parametrize(
    "case",
    [
        "missing-vault-root",
        "missing-terms-subdir",
        "empty-vault-root",
        "whitespace-vault-root",
        "empty-terms-subdir",
        "whitespace-terms-subdir",
        "non-string-vault-root",
        "non-string-terms-subdir",
        "absolute-terms-subdir",
        "root-dot-terms-subdir",
        "root-normalized-terms-subdir",
    ],
)
def test_write_cli_rejects_invalid_config_schema_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    terms_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    config_path = tmp_path / "config.json"
    glossary = tmp_path / "glossary.json"
    inventory = tmp_path / "inventory.json"
    glossary.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "Reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Chapter evidence.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    inventory.write_text(
        json.dumps(
            build_inventory_payload(
                [{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir
            )
        ),
        encoding="utf-8",
    )
    payload: dict[str, object] = {
        "vault_root": str(vault),
        "terms_subdir": "Glossary",
    }
    if case == "missing-vault-root":
        del payload["vault_root"]
    elif case == "missing-terms-subdir":
        del payload["terms_subdir"]
    elif case == "empty-vault-root":
        payload["vault_root"] = ""
    elif case == "whitespace-vault-root":
        payload["vault_root"] = "  \t"
    elif case == "empty-terms-subdir":
        payload["terms_subdir"] = ""
    elif case == "whitespace-terms-subdir":
        payload["terms_subdir"] = "  \t"
    elif case == "non-string-vault-root":
        payload["vault_root"] = 7
    elif case == "non-string-terms-subdir":
        payload["terms_subdir"] = ["Glossary"]
    elif case == "absolute-terms-subdir":
        payload["terms_subdir"] = str(outside)
    elif case == "root-dot-terms-subdir":
        payload["terms_subdir"] = "."
    elif case == "root-normalized-terms-subdir":
        payload["terms_subdir"] = str(Path("Glossary") / "..")
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "write_glossary_terms.py",
            "--glossary",
            str(glossary),
            "--inventory",
            str(inventory),
            "--config-path",
            str(config_path),
            "--source-manifest",
            str(tmp_path / "unused-manifest.json"),
            "--reviewed-shortlist",
            str(tmp_path / "unused-review.json"),
            "--triage",
            str(tmp_path / "unused-triage.json"),
        ],
    )

    error = None
    try:
        write_main()
    except SystemExit as exc:
        error = str(exc)

    assert not (vault / "ReAct.md").exists()
    assert not (terms_dir / "ReAct.md").exists()
    assert not (outside / "ReAct.md").exists()
    assert error is not None
    assert "Invalid paper-glossary config object" in error


def test_writer_preflight_rejects_invalid_batch_without_creating_files(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    entries = {
        "entries": [
            {
                "name": "Valid",
                "aliases": [],
                "operation": "create",
                "definition": "definition",
                "confidence": "\u9ad8",
                "occurrence": "evidence",
            },
            {
                "name": "Invalid",
                "aliases": [],
                "operation": "enrich",
                "occurrence": "evidence",
            },
        ]
    }
    inventory = _inventory(
        [
            {
                "term": "Valid",
                "surface_forms": ["Valid"],
                "state": "new",
                "file": "",
                "link_stem": "Valid",
                "missing_fields": [],
            },
            {
                "term": "Invalid",
                "surface_forms": ["Invalid"],
                "state": "new",
                "file": "",
                "link_stem": "Invalid",
                "missing_fields": [],
            },
        ]
    )

    with pytest.raises(SystemExit, match="Invalid operation"):
        write_glossary_entries(entries, inventory, terms_dir, "Paper")

    assert not terms_dir.exists()


def test_writer_enriches_only_missing_fields_and_appends_occurrence_once(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "LLM.md"
    original = (
        "# LLM\n\n## \u6982\u5ff5\u89e3\u91ca\n- \u5b9a\u4e49\uff1auser definition\n- \u7f6e\u4fe1\u5ea6\uff1a\u4e2d\n"
        "\n## Custom\nkeep this text\n"
    )
    note.write_text(original, encoding="utf-8")
    inventory = _inventory(
        [
            {
                "term": "LLM",
                "surface_forms": ["LLM", "large language model"],
                "state": "existing_thin",
                "file": str(note),
                "link_stem": "LLM",
                "missing_fields": ["elaboration", "intuition", "distinction"],
            }
        ]
    )
    entries = {
        "entries": [
            {
                "name": "LLM",
                "aliases": ["large language model"],
                "operation": "enrich",
                "elaboration": "new explanation",
                "intuition": "new intuition",
                "occurrence": "paper evidence",
            }
        ]
    }

    first = write_glossary_entries(entries, inventory, terms_dir, "Paper")
    first_bytes = note.read_bytes()
    refreshed_inventory = _inventory(
        inspect_selected_terms(
            [{"term": "LLM", "surface_forms": ["LLM", "large language model"]}],
            terms_dir,
        )
    )
    second = write_glossary_entries(
        {
            "entries": [
                {
                    "name": "LLM",
                    "aliases": ["large language model"],
                    "operation": "reuse",
                    "occurrence": "paper evidence",
                }
            ]
        },
        refreshed_inventory,
        terms_dir,
        "Paper",
    )

    text = note.read_text(encoding="utf-8")
    assert "- \u5b9a\u4e49\uff1auser definition" in text
    assert "## Custom\nkeep this text" in text
    assert first["results"] == [
        {
            "name": "LLM",
            "forms": ["LLM", "large language model"],
            "file": str(note),
            "action": "enriched",
            "link_stem": "LLM",
            "fields_added": ["elaboration", "intuition"],
            "occurrence_added": True,
        }
    ]
    assert second["results"][0]["action"] == "unchanged"
    assert second["results"][0]["fields_added"] == []
    assert second["results"][0]["occurrence_added"] is False
    assert note.read_bytes() == first_bytes
    assert text.count("[[Paper]]") == 1


def test_writer_preserves_bom_crlf_custom_content_and_second_run_bytes(
    tmp_path: Path,
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "BOM Term.md"
    original_text = (
        f"# BOM Term\r\n\r\n## {GLOSSARY_CONCEPT_HEADING}\r\n"
        "- \u5b9a\u4e49\uff1auser definition\r\n"
        "- \u8be6\u89e3\uff1auser elaboration\r\n"
        "- \u76f4\u89c9\uff1auser intuition\r\n"
        "- \u7f6e\u4fe1\u5ea6\uff1a\u4e2d\r\n\r\n"
        "## Custom\r\nkeep this text\r\n\r\n"
        f"## {GLOSSARY_OCCURRENCE_HEADING}\r\n"
        "- [[OldPaper]]: old evidence\r\n"
    )
    original_bytes = b"\xef\xbb\xbf" + original_text.encode("utf-8")
    note.write_bytes(original_bytes)
    inventory = _inventory(
        inspect_selected_terms(
            [{"term": "BOM Term", "surface_forms": ["BOM Term"]}], terms_dir
        )
    )
    glossary = {
        "entries": [
            {
                "name": "BOM Term",
                "aliases": [],
                "operation": "reuse",
                "occurrence": "new evidence",
            }
        ]
    }

    first = write_glossary_entries(glossary, inventory, terms_dir, "Paper")
    first_bytes = note.read_bytes()
    second = write_glossary_entries(glossary, inventory, terms_dir, "Paper")

    assert first["results"][0]["action"] == "updated"
    assert second["results"][0]["action"] == "unchanged"
    assert first_bytes != original_bytes
    assert first_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\n" not in first_bytes[3:].replace(b"\r\n", b"")
    assert b"## Custom\r\nkeep this text\r\n" in first_bytes
    assert first_bytes.count(b"[[Paper]]") == 1
    assert note.read_bytes() == first_bytes


def test_writer_reuse_rejects_concept_replacement_and_can_add_occurrence(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "ReAct.md"
    note.write_text(render_term_file({**ENTRY, "name": "ReAct"}, "OldPaper"), encoding="utf-8")
    inventory = _inventory(
        [
            {
                "term": "ReAct",
                "surface_forms": ["ReAct"],
                "state": "existing_complete",
                "file": str(note),
                "link_stem": "ReAct",
                "missing_fields": ["distinction"],
            }
        ]
    )

    with pytest.raises(SystemExit, match="reuse"):
        write_glossary_entries(
            {"entries": [{"name": "ReAct", "operation": "reuse", "definition": "replace", "occurrence": "evidence"}]},
            inventory,
            terms_dir,
            "Paper",
        )

    result = write_glossary_entries(
        {"entries": [{"name": "ReAct", "operation": "reuse", "occurrence": "evidence"}]},
        inventory,
        terms_dir,
        "Paper",
    )

    assert result["results"][0]["action"] == "updated"
    assert result["results"][0]["fields_added"] == []
    assert result["results"][0]["occurrence_added"] is True


def test_writer_rejects_forged_outside_target_and_link_stem(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    inside = terms_dir / "LLM.md"
    outside = tmp_path / "outside.md"
    text = (
        f"# LLM\n\n## {GLOSSARY_CONCEPT_HEADING}\n"
        "- \u5b9a\u4e49\uff1adefinition\n- \u7f6e\u4fe1\u5ea6\uff1a\u4e2d\n"
    )
    inside.write_text(text, encoding="utf-8")
    outside.write_text(text, encoding="utf-8")
    outside_before = outside.read_bytes()
    inventory = _inventory(
        [
            {
                "term": "LLM",
                "surface_forms": ["LLM"],
                "state": "existing_thin",
                "file": str(outside),
                "link_stem": "Forged",
                "missing_fields": ["elaboration", "intuition", "distinction"],
            }
        ]
    )

    with pytest.raises(SystemExit, match="Inventory mismatch"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "LLM",
                        "operation": "enrich",
                        "elaboration": "new",
                        "occurrence": "evidence",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert outside.read_bytes() == outside_before
    assert "new" not in inside.read_text(encoding="utf-8")


def test_writer_rejects_stale_inventory_state_before_writing(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "ReAct.md"
    note.write_text(render_term_file({**ENTRY, "name": "ReAct"}, "OldPaper"), encoding="utf-8")
    before = note.read_bytes()
    stale = _inventory(
        [
            {
                "term": "ReAct",
                "surface_forms": ["ReAct"],
                "state": "existing_thin",
                "file": str(note),
                "link_stem": "ReAct",
                "missing_fields": ["distinction"],
            }
        ]
    )

    with pytest.raises(SystemExit, match="Inventory mismatch"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "enrich",
                        "distinction": "replacement",
                        "occurrence": "evidence",
                    }
                ]
            },
            stale,
            terms_dir,
            "Paper",
        )

    assert note.read_bytes() == before


def test_writer_rejects_two_entries_resolving_to_same_target(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "Canonical.md"
    note.write_text(
        render_term_file({**ENTRY, "name": "Canonical", "aliases": ["Alias"]}, "OldPaper"),
        encoding="utf-8",
    )
    selected = [
        {"term": "Canonical", "surface_forms": ["Canonical"]},
        {"term": "Alias", "surface_forms": ["Alias"]},
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))
    before = note.read_bytes()

    with pytest.raises(SystemExit, match="Duplicate target"):
        write_glossary_entries(
            {
                "entries": [
                    {"name": "Canonical", "operation": "reuse", "occurrence": "one"},
                    {"name": "Alias", "operation": "reuse", "occurrence": "two"},
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert note.read_bytes() == before


def test_writer_prepares_all_targets_before_any_create(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    (terms_dir / "Broken.md").write_bytes(b"\xff\xfe\x00")
    inventory = _inventory(
        [
            {
                "term": "Created",
                "surface_forms": ["Created"],
                "state": "new",
                "file": "",
                "link_stem": "Created",
                "missing_fields": [],
            },
            {
                "term": "Broken",
                "surface_forms": ["Broken"],
                "state": "existing_thin",
                "file": str(terms_dir / "Broken.md"),
                "link_stem": "Broken",
                "missing_fields": ["definition", "elaboration", "intuition", "distinction", "confidence"],
            },
        ]
    )

    with pytest.raises(SystemExit, match="Unable to read glossary note.*Broken.md"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "Created",
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    },
                    {
                        "name": "Broken",
                        "operation": "enrich",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    },
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not (terms_dir / "Created.md").exists()


def test_writer_allocates_sanitized_create_collisions_and_reports_actual_stems(
    tmp_path: Path,
) -> None:
    terms_dir = tmp_path / "terms"
    selected = [
        {"term": "A/B", "surface_forms": ["A/B"]},
        {"term": r"A\B", "surface_forms": [r"A\B"]},
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))
    entries = {
        "entries": [
            {
                "name": item["term"],
                "operation": "create",
                "definition": "definition",
                "confidence": "\u9ad8",
                "occurrence": "evidence",
            }
            for item in selected
        ]
    }

    result = write_glossary_entries(entries, inventory, terms_dir, "Paper")

    assert [item["link_stem"] for item in result["results"]] == ["A B", "A B-2"]
    assert sorted(path.name for path in terms_dir.glob("*.md")) == ["A B-2.md", "A B.md"]
    second = (terms_dir / "A B-2.md").read_text(encoding="utf-8")
    assert '  - "A\\\\B"' in second
    assert "# A\\B\n" in second


def test_append_occurrence_ignores_same_paper_link_outside_occurrence_section() -> None:
    text = (
        "# Existing\n\nCustom mention [[Paper]] outside the occurrence section.\n\n"
        f"## {GLOSSARY_OCCURRENCE_HEADING}\n- [[OldPaper]]: old evidence\n"
    )

    updated = append_occurrence(text, {"occurrence": "new evidence"}, "Paper")
    repeated = append_occurrence(updated, {"occurrence": "new evidence"}, "Paper")

    occurrence = updated.split(f"## {GLOSSARY_OCCURRENCE_HEADING}", 1)[1]
    assert occurrence.count("[[Paper]]") == 1
    assert repeated == updated


def test_writer_preserves_grounded_forms_when_entry_omits_or_adds_aliases(
    tmp_path: Path,
) -> None:
    terms_dir = tmp_path / "terms"
    selected = [
        {"term": "ReAct", "surface_forms": ["ReAct", "ＲｅＡｃｔ"]}
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))

    result = write_glossary_entries(
        {
            "entries": [
                {
                    "name": "ReAct",
                    "aliases": ["Reasoning and Acting"],
                    "operation": "create",
                    "definition": "A reasoning and acting pattern.",
                    "confidence": "高",
                    "occurrence": "Paper evidence.",
                }
            ]
        },
        inventory,
        terms_dir,
        "Paper",
    )

    assert result["results"][0]["forms"] == ["ReAct", "ＲｅＡｃｔ"]
    assert '  - "Reasoning and Acting"' in (terms_dir / "ReAct.md").read_text(
        encoding="utf-8"
    )


def test_writer_rejects_missing_inventory_provenance_without_writes(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    inventory = {
        "results": inspect_selected_terms(
            [{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir
        )
    }

    with pytest.raises(SystemExit, match="provenance"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "A reasoning and acting pattern.",
                        "confidence": "高",
                        "occurrence": "Paper evidence.",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not terms_dir.exists()


@pytest.mark.parametrize("change", ["append", "reorder", "replace"])
def test_writer_rejects_changed_inventory_surface_forms_without_writes(
    tmp_path: Path, change: str
) -> None:
    terms_dir = tmp_path / "terms"
    source_forms = ["ReAct", "ＲｅＡｃｔ"]
    inventory = build_inventory_payload(
        [{"term": "ReAct", "surface_forms": source_forms}], terms_dir
    )
    if change == "append":
        inventory["results"][0]["surface_forms"].append("invented")
    elif change == "reorder":
        inventory["results"][0]["surface_forms"].reverse()
    else:
        inventory["results"][0]["surface_forms"][1] = "invented"

    with pytest.raises(SystemExit, match="selection|provenance|surface_forms"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "operation": "create",
                        "definition": "A reasoning and acting pattern.",
                        "confidence": "高",
                        "occurrence": "Paper evidence.",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not terms_dir.exists()


def test_writer_rejects_entry_only_alias_redirect_to_existing_note(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    victim = terms_dir / "Victim.md"
    victim.write_text(
        render_term_file({**ENTRY, "name": "Victim", "aliases": []}, "OldPaper"),
        encoding="utf-8",
    )
    victim_item = inspect_selected_terms(
        [{"term": "Victim", "surface_forms": ["Victim"]}], terms_dir
    )[0]
    inventory = _inventory(
        [
            {
                **victim_item,
                "term": "Innocent",
                "surface_forms": ["Innocent"],
            }
        ]
    )
    before = victim.read_bytes()

    with pytest.raises(SystemExit, match="Inventory mismatch"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "Innocent",
                        "aliases": ["Victim"],
                        "operation": "reuse",
                        "occurrence": "redirect",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert victim.read_bytes() == before


def test_writer_rejects_create_alias_owned_by_unselected_existing_note_without_writes(
    tmp_path: Path,
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    owner = terms_dir / "Existing.md"
    owner.write_text(
        render_term_file(
            {**ENTRY, "name": "Existing", "aliases": ["Generated Alias"]},
            "OldPaper",
        ),
        encoding="utf-8",
    )
    inventory = build_inventory_payload(
        [{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir
    )
    before = owner.read_bytes()

    with pytest.raises(SystemExit, match="alias|logical|collision|existing glossary"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "ReAct",
                        "aliases": ["Generated Alias"],
                        "operation": "create",
                        "definition": "A reasoning and acting pattern.",
                        "confidence": "\u9ad8",
                        "occurrence": "Paper evidence.",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert owner.read_bytes() == before
    assert not (terms_dir / "ReAct.md").exists()


def test_writer_allows_generated_alias_owned_by_the_same_existing_target(
    tmp_path: Path,
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "ReAct.md"
    note.write_text(
        render_term_file(
            {**ENTRY, "name": "ReAct", "aliases": ["Reasoning and Acting"]},
            "OldPaper",
        ),
        encoding="utf-8",
    )
    inventory = build_inventory_payload(
        [{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir
    )

    result = write_glossary_entries(
        {
            "entries": [
                {
                    "name": "ReAct",
                    "aliases": ["Reasoning and Acting"],
                    "operation": "reuse",
                    "occurrence": "New paper evidence.",
                }
            ]
        },
        inventory,
        terms_dir,
        "Paper",
    )

    assert result["results"][0]["file"] == str(note.resolve())
    assert "[[Paper]]" in note.read_text(encoding="utf-8")


def test_writer_requires_canonical_name_in_inventory_surface_forms(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    inventory = _inventory(
        [
            {
                "term": "Canonical",
                "surface_forms": ["Alias"],
                "state": "new",
                "file": "",
                "link_stem": "Canonical",
                "missing_fields": [],
            }
        ]
    )

    with pytest.raises(SystemExit, match="Canonical|canonical.*surface_forms"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "Canonical",
                        "aliases": ["Alias"],
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not terms_dir.exists()


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "CON", "nul.txt", "trailing.", "trailing "],
)
def test_safe_term_filename_rejects_unsafe_components(name: str) -> None:
    with pytest.raises(SystemExit, match="Unsafe glossary filename"):
        safe_term_filename(name)


def test_writer_rejects_overlong_create_before_any_write(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    long_name = "X" * 300
    selected = [
        {"term": "First", "surface_forms": ["First"]},
        {"term": long_name, "surface_forms": [long_name]},
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))

    with pytest.raises(SystemExit, match="Unsafe glossary filename.*too long"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": item["term"],
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                    for item in selected
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not (terms_dir / "First.md").exists()


def test_writer_rejects_non_bmp_overlong_create_before_any_write(tmp_path: Path) -> None:
    terms_dir = tmp_path / "terms"
    long_name = "\U0001f600" * 130
    selected = [
        {"term": "First", "surface_forms": ["First"]},
        {"term": long_name, "surface_forms": [long_name]},
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))

    with pytest.raises(SystemExit, match="Unsafe glossary filename.*too long"):
        write_glossary_entries(
            {
                "entries": [
                    {
                        "name": item["term"],
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                    for item in selected
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert not (terms_dir / "First.md").exists()


def test_writer_rechecks_existing_snapshot_before_first_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    terms_dir.mkdir()
    note = terms_dir / "ReAct.md"
    note.write_text(
        render_term_file({**ENTRY, "name": "ReAct", "aliases": []}, "OldPaper"),
        encoding="utf-8",
    )
    inventory = _inventory(
        inspect_selected_terms(
            [{"term": "ReAct", "surface_forms": ["ReAct"]}], terms_dir
        )
    )
    original_prepare = writer_module._prepare_write_plans
    concurrent = b"# Concurrent user edit\n"

    def prepare_then_modify(*args: object, **kwargs: object) -> list[dict]:
        plans = original_prepare(*args, **kwargs)
        note.write_bytes(concurrent)
        return plans

    monkeypatch.setattr(writer_module, "_prepare_write_plans", prepare_then_modify)

    with pytest.raises(SystemExit, match="changed after planning"):
        writer_module.write_glossary_entries(
            {"entries": [{"name": "ReAct", "operation": "reuse", "occurrence": "new"}]},
            inventory,
            terms_dir,
            "Paper",
        )

    assert note.read_bytes() == concurrent
    assert not list(terms_dir.glob("*.tmp"))


def test_writer_rechecks_create_absence_before_first_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    selected = [{"term": "Created", "surface_forms": ["Created"]}]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))
    original_prepare = writer_module._prepare_write_plans
    concurrent = b"# Concurrent create\n"

    def prepare_then_create(*args: object, **kwargs: object) -> list[dict]:
        plans = original_prepare(*args, **kwargs)
        target = Path(plans[0]["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(concurrent)
        return plans

    monkeypatch.setattr(writer_module, "_prepare_write_plans", prepare_then_create)

    with pytest.raises(SystemExit, match="appeared after planning"):
        writer_module.write_glossary_entries(
            {
                "entries": [
                    {
                        "name": "Created",
                        "operation": "create",
                        "definition": "definition",
                        "confidence": "\u9ad8",
                        "occurrence": "evidence",
                    }
                ]
            },
            inventory,
            terms_dir,
            "Paper",
        )

    assert (terms_dir / "Created.md").read_bytes() == concurrent


def test_writer_rolls_back_prior_create_reservations_on_exclusive_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terms_dir = tmp_path / "terms"
    selected = [
        {"term": "First", "surface_forms": ["First"]},
        {"term": "Second", "surface_forms": ["Second"]},
    ]
    inventory = _inventory(inspect_selected_terms(selected, terms_dir))
    entries = {
        "entries": [
            {
                "name": item["term"],
                "operation": "create",
                "definition": "definition",
                "confidence": "\u9ad8",
                "occurrence": "evidence",
            }
            for item in selected
        ]
    }
    original_open = writer_module.os.open
    concurrent = b"# Concurrent second create\n"

    def race_on_second(path: str | bytes, flags: int, mode: int = 0o777) -> int:
        target = Path(path)
        if target.name == "Second.md" and not target.exists():
            target.write_bytes(concurrent)
        return original_open(path, flags, mode)

    monkeypatch.setattr(writer_module.os, "open", race_on_second)

    with pytest.raises(SystemExit, match="appeared during commit"):
        writer_module.write_glossary_entries(entries, inventory, terms_dir, "Paper")

    assert not (terms_dir / "First.md").exists()
    assert (terms_dir / "Second.md").read_bytes() == concurrent


@pytest.mark.skipif(os.name != "nt", reason="Windows path comparison semantics")
def test_writer_accepts_windows_case_variant_for_same_contained_file(tmp_path: Path) -> None:
    terms_dir = tmp_path / "Terms"
    terms_dir.mkdir()
    note = terms_dir / "MixedCase.md"
    note.write_text(
        render_term_file({**ENTRY, "name": "MixedCase", "aliases": []}, "OldPaper"),
        encoding="utf-8",
    )
    inventory = _inventory(
        inspect_selected_terms(
            [{"term": "MixedCase", "surface_forms": ["MixedCase"]}], terms_dir
        )
    )
    inventory["results"][0]["file"] = str(note.with_name("mixedcase.MD"))

    result = write_glossary_entries(
        {"entries": [{"name": "MixedCase", "operation": "reuse", "occurrence": "case"}]},
        inventory,
        terms_dir.with_name("TERMS"),
        "Paper",
    )

    assert result["results"][0]["file"].casefold() == str(note).casefold()
    assert "[[Paper]]" in note.read_text(encoding="utf-8")


def test_lint_rejects_missing_required_term_note_fields() -> None:
    good = render_term_file(ENTRY, "CAD-MoE")

    assert "term_disclaimer_missing" in _codes(
        lint_term_file_text(good.replace(GLOSSARY_DISCLAIMER + "\n\n", ""))
    )
    assert "term_definition_missing" in _codes(
        lint_term_file_text(good.replace("- 定义：衡量两个概率分布差异的非对称度量。\n", ""))
    )
    assert "term_confidence_invalid" in _codes(
        lint_term_file_text(good.replace("- 置信度：高", "- 置信度：也许"))
    )
    assert "term_occurrence_reference_missing" in _codes(
        lint_term_file_text(good.replace("- [[CAD-MoE]]：方法 式(4)，第 3-6 页\n", "（暂无）\n"))
    )
