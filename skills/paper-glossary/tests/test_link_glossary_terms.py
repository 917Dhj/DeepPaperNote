from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sys
from pathlib import Path

import pytest

import link_glossary_terms as linker
from conftest import write_current_workflow
from glossary_common import canonical_sha256, selection_sha256
from glossary_config import configure_terms_dir
from link_glossary_terms import link_article_terms, main
from write_glossary_terms import render_term_file


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _writer_mappings_sha256(payload: dict) -> str:
    mappings = [
        {
            field: item[field]
            for field in ("name", "forms", "file", "link_stem")
        }
        for item in payload["results"]
    ]
    return canonical_sha256(
        {
            "provenance": payload["provenance"],
            "mappings": mappings,
            "context": payload["context"],
            "triage_sha256": payload["triage_sha256"],
        }
    )


def _triage_sha256(payload: dict) -> str:
    return canonical_sha256(
        {
            "paper_id": payload["paper_id"],
            "provenance": payload["provenance"],
            "terms": payload["terms"],
        }
    )


def test_linker_links_first_safe_alias_and_skips_all_protected_regions(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        "---\ntitle: ReAct\n---\n"
        "# ReAct heading\n\n"
        "`ReAct` and [ReAct](https://example.test/ReAct) are protected.\n"
        "<span>ReAct</span> https://example.test/ReAct [[Other|ReAct]]\n\n"
        "REACT combines reasoning and acting. ReAct appears again.\n\n"
        "```python\nReAct = 'code'\n```\n\n"
        "## References\nReAct paper\n",
        encoding="utf-8",
    )

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct", "REACT"]}],
        digest(article),
    )

    text = article.read_text(encoding="utf-8")
    assert "[[ReAct|REACT]] combines reasoning" in text
    assert "# ReAct heading" in text
    assert "`ReAct`" in text
    assert "[ReAct](https://example.test/ReAct)" in text
    assert "<span>ReAct</span>" in text
    assert "https://example.test/ReAct" in text
    assert "[[Other|ReAct]]" in text
    assert "```python\nReAct = 'code'\n```" in text
    assert "## References\nReAct paper" in text
    assert text.count("[[ReAct|REACT]]") == 1
    assert result["summary"] == {"linked": 1, "already_linked": 0, "not_found": 0}


def test_linker_uses_safe_stem_and_does_not_duplicate_link(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("C# is a programming language.\n", encoding="utf-8")
    mappings = [{"link_stem": "C＃", "forms": ["C#"]}]

    first = link_article_terms(article, mappings, digest(article))
    second = link_article_terms(article, mappings, digest(article))

    assert article.read_text(encoding="utf-8") == (
        "[[C＃|C#]] is a programming language.\n"
    )
    assert first["results"] == [{"link_stem": "C＃", "status": "linked"}]
    assert second["results"] == [
        {"link_stem": "C＃", "status": "already_linked"}
    ]


def test_linker_rejects_stale_article_hash_before_writing(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = b"ReAct text\n"
    article.write_bytes(original)

    with pytest.raises(SystemExit, match="changed since preview"):
        link_article_terms(article, [{"link_stem": "ReAct", "forms": ["ReAct"]}], "0" * 64)

    assert article.read_bytes() == original


def test_linker_prefers_longer_forms_and_rejects_substrings(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("SerpApi is an API. XAPI and APIClient are not API terms.\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [
            {"link_stem": "API", "forms": ["API"]},
            {"link_stem": "SerpApi", "forms": ["SerpApi"]},
        ],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "[[SerpApi]] is an [[API]]. XAPI and APIClient are not API terms.\n"
    )
    assert result["summary"] == {"linked": 2, "already_linked": 0, "not_found": 0}


def test_linker_reports_existing_target_as_already_linked_without_rewriting(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    original = b"[[ReAct|REACT]] is already linked. ReAct remains plain.\n"
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct", "REACT"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "already_linked"}]
    assert result["summary"] == {"linked": 0, "already_linked": 1, "not_found": 0}


def test_linker_preserves_utf8_bom_and_crlf_newlines(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_bytes(b"\xef\xbb\xbfReAct text\r\nSecond line\r\n")

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == b"\xef\xbb\xbf[[ReAct]] text\r\nSecond line\r\n"


def test_linker_reports_not_found_and_leaves_bytes_unchanged(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = b"Only plain prose here.\n"
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "not_found"}]
    assert result["summary"] == {"linked": 0, "already_linked": 0, "not_found": 1}


def test_linker_is_idempotent(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("ReAct text\n", encoding="utf-8")
    mappings = [{"link_stem": "ReAct", "forms": ["ReAct"]}]

    link_article_terms(article, mappings, digest(article))
    linked_bytes = article.read_bytes()
    result = link_article_terms(article, mappings, digest(article))

    assert article.read_bytes() == linked_bytes
    assert result["summary"] == {"linked": 0, "already_linked": 1, "not_found": 0}


def test_cli_rejects_article_outside_configured_vault_before_linking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_vault = tmp_path / "configured"
    other_vault = tmp_path / "other"
    (configured_vault / ".obsidian").mkdir(parents=True)
    (other_vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "device" / "config.json"
    configure_terms_dir(configured_vault / "Terms", config_path)
    article = other_vault / "Paper.md"
    original = b"ReAct text\n"
    article.write_bytes(original)
    writer_result = tmp_path / "writer-result.json"
    writer_result.write_text(
        json.dumps(
            {
                "status": "ok",
                "results": [{"link_stem": "ReAct", "forms": ["ReAct"]}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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

    with pytest.raises(SystemExit, match="same Obsidian vault"):
        main()

    assert article.read_bytes() == original


def test_cli_consumes_only_successful_writer_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "device" / "config.json"
    configure_terms_dir(vault / "Terms", config_path)
    article = vault / "Paper.md"
    original = b"ReAct text\n"
    article.write_bytes(original)
    writer_result = tmp_path / "writer-result.json"
    writer_result.write_text(
        json.dumps({"status": "failed", "results": []}), encoding="utf-8"
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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

    with pytest.raises(SystemExit, match="successful writer result"):
        main()

    assert article.read_bytes() == original


@pytest.mark.parametrize(
    "original",
    [
        b"---\ntitle: ReAct\nbody: ReAct\n",
        b"```python\nReAct = 'protected'\n",
        b"````python\nReAct = 'protected'\n```\nstill ReAct\n",
    ],
    ids=["unclosed-frontmatter", "unclosed-fence", "short-fence-closer"],
)
def test_linker_protects_unclosed_frontmatter_and_fences_to_eof(
    tmp_path: Path, original: bytes
) -> None:
    article = tmp_path / "Paper.md"
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["summary"] == {"linked": 0, "already_linked": 0, "not_found": 1}


def test_linker_protects_nested_same_name_html_elements(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        "<span><span>nested</span> ReAct</span>\nReAct prose\n", encoding="utf-8"
    )

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "<span><span>nested</span> ReAct</span>\n[[ReAct]] prose\n"
    )


@pytest.mark.parametrize("tag", ["strong", "b", "em", "i"])
def test_linker_links_visible_text_inside_simple_html_emphasis(
    tmp_path: Path, tag: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(f"<{tag}>ReAct</{tag}> prose\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"<{tag}>[[ReAct]]</{tag}> prose\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_linker_keeps_emphasis_text_protected_inside_html_container(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        "<div><strong>ReAct</strong></div>\nReAct prose\n", encoding="utf-8"
    )

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "<div><strong>ReAct</strong></div>\n[[ReAct]] prose\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_linker_handles_gt_and_term_text_inside_emphasis_attributes(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        '<strong title="attribute > ReAct">Other</strong>\n'
        '<strong title="1 > 0">ReAct</strong> prose\n',
        encoding="utf-8",
    )

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        '<strong title="attribute > ReAct">Other</strong>\n'
        '<strong title="1 > 0">[[ReAct]]</strong> prose\n'
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_linker_does_not_treat_attribute_markup_as_an_html_container(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        '<div title="<br>"><strong>ReAct</strong></div>\nReAct prose\n',
        encoding="utf-8",
    )

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        '<div title="<br>"><strong>ReAct</strong></div>\n[[ReAct]] prose\n'
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_linker_protects_mismatched_html_then_links_following_prose(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("<strong>ReAct</em></strong>\nReAct prose\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "<strong>ReAct</em></strong>\n[[ReAct]] prose\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "autolink",
    ["<https://example.test/ReAct>", "<ReAct@example.test>"],
    ids=["uri", "email"],
)
def test_linker_preserves_markdown_autolinks_and_links_following_prose(
    tmp_path: Path, autolink: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(f"{autolink}\nReAct prose\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == f"{autolink}\n[[ReAct]] prose\n"
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "original",
    [b"<div>\nReAct remains protected\n", b"<!-- ReAct remains protected\n"],
    ids=["unclosed-element", "unclosed-comment"],
)
def test_linker_protects_unclosed_html_and_comments_to_eof(
    tmp_path: Path, original: bytes
) -> None:
    article = tmp_path / "Paper.md"
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "not_found"}]


def test_linker_rejects_external_update_before_replace_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = tmp_path / "Paper.md"
    article.write_bytes(b"ReAct text\n")
    external = b"external update\n"
    real_fsync = linker.os.fsync

    def fsync_then_update(descriptor: int) -> None:
        real_fsync(descriptor)
        article.write_bytes(external)

    monkeypatch.setattr(linker.os, "fsync", fsync_then_update)

    with pytest.raises(SystemExit, match="changed while linking"):
        link_article_terms(
            article,
            [{"link_stem": "ReAct", "forms": ["ReAct"]}],
            digest(article),
        )

    assert article.read_bytes() == external
    assert list(tmp_path.glob(f".{article.name}.*.tmp")) == []


def test_linker_coalesces_case_insensitive_targets_and_merged_forms(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("ReAct then reasoning and acting.\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [
            {"link_stem": "ReAct", "forms": ["ReAct", "REACT"]},
            {"link_stem": "react", "forms": ["reasoning and acting", "ReAct"]},
        ],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "ReAct then [[ReAct|reasoning and acting]].\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]
    assert result["summary"] == {"linked": 1, "already_linked": 0, "not_found": 0}


def test_linker_detects_case_insensitive_wiki_target_with_fragment_and_alias(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    original = "[[rEaCt#Heading|显示]] exists. ReAct remains plain.\n".encode("utf-8")
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "already_linked"}]


def test_linker_protects_nested_parentheses_in_markdown_destination(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        "[docs](https://example.test/a_(b)/ReAct) ReAct prose\n", encoding="utf-8"
    )

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        "[docs](https://example.test/a_(b)/ReAct) [[ReAct]] prose\n"
    )


def test_atomic_replace_failure_preserves_article_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    article = tmp_path / "Paper.md"
    original = b"ReAct text\n"
    article.write_bytes(original)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(linker.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        link_article_terms(
            article,
            [{"link_stem": "ReAct", "forms": ["ReAct"]}],
            digest(article),
        )

    assert article.read_bytes() == original
    assert list(tmp_path.glob(f".{article.name}.*.tmp")) == []


def test_cli_links_same_vault_article_and_writes_output_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    config_path = tmp_path / "device" / "config.json"
    terms_dir = vault / "Terms"
    configure_terms_dir(terms_dir, config_path)
    article = vault / "Paper.md"
    article.write_bytes(b"ReAct text\n")
    note = terms_dir / "ReAct.md"
    note.write_text(
        render_term_file(
            {
                "name": "ReAct",
                "aliases": [],
                "definition": "definition",
                "confidence": "\u9ad8",
                "occurrence": "evidence",
            },
            "Paper",
        ),
        encoding="utf-8",
    )
    writer_result = tmp_path / "writer-result.json"
    writer_payload = {
        "status": "ok",
        "script": "write_glossary_terms.py",
        "paper_id": "paper-fixture",
        "provenance": deepcopy(workflow["triage"]["provenance"]),
        "context": {
            "paper_id": "paper-fixture",
            "paper_link": "Paper",
            "article_path": str(article.resolve()),
        },
        "results": [
            {
                "name": "ReAct",
                "action": "created",
                "file": str(note.resolve()),
                "link_stem": "ReAct",
                "forms": ["ReAct"],
            }
        ],
    }
    writer_payload["triage_sha256"] = _triage_sha256(workflow["triage"])
    writer_payload["mappings_sha256"] = _writer_mappings_sha256(writer_payload)
    writer_result.write_text(json.dumps(writer_payload), encoding="utf-8")
    output = tmp_path / "link-result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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

    main()

    assert article.read_bytes() == b"[[ReAct]] text\n"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload.pop("elapsed_ms"), int)
    assert payload == {
        "status": "ok",
        "article_path": str(article.resolve()),
        "results": [{"link_stem": "ReAct", "status": "linked"}],
        "summary": {"linked": 1, "already_linked": 0, "not_found": 0},
        "script": "link_glossary_terms.py",
    }


@pytest.mark.parametrize(
    "tamper",
    ["forms", "stem", "file", "order", "provenance", "context", "mapping_digest"],
)
def test_linker_cli_rejects_tampered_writer_artifact_without_article_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    workflow = write_current_workflow(
        tmp_path / "workflow", ["ReAct", "Reflection"]
    )
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    article = vault / "Paper.md"
    original = b"ReAct and Reflection are article concepts.\n"
    article.write_bytes(original)
    results = []
    for name in ("ReAct", "Reflection"):
        note = terms_dir / f"{name}.md"
        note.write_text(
            render_term_file(
                {
                    "name": name,
                    "aliases": [],
                    "definition": "definition",
                    "confidence": "\u9ad8",
                    "occurrence": "evidence",
                },
                "Paper",
            ),
            encoding="utf-8",
        )
        results.append(
            {
                "name": name,
                "forms": [name],
                "file": str(note.resolve()),
                "link_stem": name,
                "action": "created",
            }
        )
    payload = {
        "status": "ok",
        "script": "write_glossary_terms.py",
        "paper_id": "paper-fixture",
        "provenance": deepcopy(workflow["triage"]["provenance"]),
        "context": {
            "paper_id": "paper-fixture",
            "paper_link": "Paper",
            "article_path": str(article.resolve()),
        },
        "results": results,
    }
    payload["triage_sha256"] = _triage_sha256(workflow["triage"])
    payload["mappings_sha256"] = _writer_mappings_sha256(payload)

    if tamper == "forms":
        payload["results"][0]["forms"] = ["Injected"]
    elif tamper == "stem":
        payload["results"][0]["link_stem"] = "Injected"
    elif tamper == "file":
        outside = tmp_path / "ReAct.md"
        outside.write_text("# ReAct\n", encoding="utf-8")
        payload["results"][0]["file"] = str(outside.resolve())
    elif tamper == "order":
        payload["results"].reverse()
    elif tamper == "provenance":
        payload["provenance"]["proposal"]["source_sha256"] = "0" * 64
    elif tamper == "context":
        other = vault / "Other.md"
        other.write_text("# Other\n", encoding="utf-8")
        payload["context"]["article_path"] = str(other.resolve())
    elif tamper == "mapping_digest":
        payload["mappings_sha256"] = "0" * 64
    if tamper != "mapping_digest":
        payload["mappings_sha256"] = _writer_mappings_sha256(payload)

    writer_result = tmp_path / "writer-result.json"
    writer_result.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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

    with pytest.raises(
        SystemExit,
        match="writer|mapping|provenance|digest|glossary|current|review|file|stem|form|article",
    ):
        main()

    assert article.read_bytes() == original


def test_linker_cli_rejects_reviewed_but_unselected_forged_mapping(
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
    article = vault / "Paper.md"
    original = b"Reflection is an article concept.\n"
    article.write_bytes(original)
    note = terms_dir / "Reflection.md"
    note.write_text(
        render_term_file(
            {
                "name": "Reflection",
                "aliases": [],
                "definition": "A reflection step.",
                "confidence": "\u9ad8",
                "occurrence": "Paper evidence.",
            },
            "Paper",
        ),
        encoding="utf-8",
    )
    reflection = next(
        item
        for item in workflow["review"]["reviewed_shortlist"]
        if item["term"] == "Reflection"
    )
    forged_provenance = deepcopy(workflow["triage"]["provenance"])
    forged_provenance["selection_sha256"] = selection_sha256(
        forged_provenance["review"]["review_sha256"], [reflection]
    )
    payload = {
        "status": "ok",
        "script": "write_glossary_terms.py",
        "paper_id": workflow["triage"]["paper_id"],
        "provenance": forged_provenance,
        "context": {
            "paper_id": workflow["triage"]["paper_id"],
            "paper_link": "Paper",
            "article_path": str(article.resolve()),
        },
        "results": [
            {
                "name": "Reflection",
                "forms": list(reflection["surface_forms"]),
                "file": str(note.resolve()),
                "link_stem": "Reflection",
                "action": "created",
            }
        ],
    }
    forged_triage = deepcopy(workflow["triage"])
    forged_triage["provenance"] = deepcopy(forged_provenance)
    forged_triage["terms"] = [deepcopy(reflection)]
    payload["triage_sha256"] = _triage_sha256(forged_triage)
    payload["mappings_sha256"] = _writer_mappings_sha256(payload)
    writer_result = tmp_path / "forged-writer.json"
    writer_result.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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
        main()

    assert article.read_bytes() == original


def test_linker_cli_rejects_glossary_only_writer_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = write_current_workflow(tmp_path / "workflow", ["ReAct"])
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    terms_dir = vault / "Glossary"
    config_path = tmp_path / "config.json"
    configure_terms_dir(terms_dir, config_path)
    article = vault / "Paper.md"
    original = b"ReAct is an article concept.\n"
    article.write_bytes(original)
    note = terms_dir / "ReAct.md"
    note.write_text(
        render_term_file(
            {
                "name": "ReAct",
                "aliases": [],
                "definition": "definition",
                "confidence": "\u9ad8",
                "occurrence": "evidence",
            },
            "paper-fixture",
        ),
        encoding="utf-8",
    )
    payload = {
        "status": "ok",
        "script": "write_glossary_terms.py",
        "paper_id": "paper-fixture",
        "provenance": deepcopy(workflow["triage"]["provenance"]),
        "context": {
            "paper_id": "paper-fixture",
            "paper_link": "paper-fixture",
            "article_path": "",
        },
        "results": [
            {
                "name": "ReAct",
                "forms": ["ReAct"],
                "file": str(note.resolve()),
                "link_stem": "ReAct",
                "action": "created",
            }
        ],
    }
    payload["triage_sha256"] = _triage_sha256(workflow["triage"])
    payload["mappings_sha256"] = _writer_mappings_sha256(payload)
    writer_result = tmp_path / "writer-result.json"
    writer_result.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "link_glossary_terms.py",
            "--input",
            str(article),
            "--write-result",
            str(writer_result),
            "--expected-sha256",
            digest(article),
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

    with pytest.raises(SystemExit, match="bound article|article context"):
        main()

    assert article.read_bytes() == original


@pytest.mark.parametrize(
    ("literal", "suffix"),
    [("<div>", ""), ("[x](", ")")],
    ids=["html-opener", "markdown-destination"],
)
def test_second_review_context_scanners_ignore_fenced_code_literals(
    tmp_path: Path, literal: str, suffix: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        f"```text\n{literal}\n```\nReAct prose{suffix}\n", encoding="utf-8"
    )

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"```text\n{literal}\n```\n[[ReAct]] prose{suffix}\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    ("literal", "suffix"),
    [("<div>", ""), ("[x](", ")")],
    ids=["html-opener", "markdown-destination"],
)
def test_second_review_context_scanners_ignore_inline_code_literals(
    tmp_path: Path, literal: str, suffix: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(f"`{literal}` then ReAct prose{suffix}\n", encoding="utf-8")

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"`{literal}` then [[ReAct]] prose{suffix}\n"
    )


@pytest.mark.parametrize(
    ("metadata", "suffix"),
    [("example: <div>", ""), ('example: "[x]("', ")")],
    ids=["html-opener", "markdown-destination"],
)
def test_second_review_context_scanners_ignore_closed_frontmatter_literals(
    tmp_path: Path, metadata: str, suffix: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        f"---\n{metadata}\n---\nReAct prose{suffix}\n", encoding="utf-8"
    )

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"---\n{metadata}\n---\n[[ReAct]] prose{suffix}\n"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("`[[ReAct]]` then ReAct prose\n", "`[[ReAct]]` then [[ReAct]] prose\n"),
        (
            "```text\n[[ReAct]]\n```\nReAct prose\n",
            "```text\n[[ReAct]]\n```\n[[ReAct]] prose\n",
        ),
        (
            "---\nexample: '[[ReAct]]'\n---\nReAct prose\n",
            "---\nexample: '[[ReAct]]'\n---\n[[ReAct]] prose\n",
        ),
        (
            "<!-- [[ReAct]] -->\nReAct prose\n",
            "<!-- [[ReAct]] -->\n[[ReAct]] prose\n",
        ),
    ],
    ids=["inline", "fence", "frontmatter", "html-comment"],
)
def test_second_review_wiki_literals_in_protected_context_are_not_targets(
    tmp_path: Path, source: str, expected: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(source, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == expected
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "source",
    ["<br> ReAct prose\n", '<img alt="ReAct"> ReAct prose\n'],
    ids=["br", "img"],
)
def test_second_review_void_html_tags_do_not_protect_following_prose(
    tmp_path: Path, source: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(source, encoding="utf-8")

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == source.replace(
        " ReAct prose", " [[ReAct]] prose"
    )


def test_second_review_coalesced_target_exact_canonical_uses_direct_link(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("ReAct prose\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [
            {"link_stem": "ReAct", "forms": ["REACT"]},
            {"link_stem": "react", "forms": ["ReAct"]},
        ],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == "[[ReAct]] prose\n"
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_final_review_reference_heading_skips_fenced_literal(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = (
        "```text\n"
        "## References\n"
        "```\n\n"
        "## References\n"
        "ReAct citation\n"
    ).encode("utf-8")
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "not_found"}]
    assert result["summary"] == {"linked": 0, "already_linked": 0, "not_found": 1}


def test_crlf_review_reference_heading_protects_tail(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = b"## References\r\nReAct citation\r\n"
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "not_found"}]


def test_crlf_review_reference_heading_skips_fenced_literal(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = (
        b"```text\r\n"
        b"## References\r\n"
        b"```\r\n\r\n"
        b"## References\r\n"
        b"ReAct citation\r\n"
    )
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original
    assert result["results"] == [{"link_stem": "ReAct", "status": "not_found"}]


@pytest.mark.parametrize(
    ("reference_link", "definition"),
    [
        ("[ReAct][method]", "[method]: https://example.test/react"),
        ("[ReAct][]", "[ReAct]: https://example.test/react"),
        ("[ReAct]", "[ReAct]: https://example.test/react"),
    ],
    ids=["full", "collapsed", "shortcut"],
)
def test_final_review_protects_valid_reference_links_and_definitions(
    tmp_path: Path, reference_link: str, definition: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"{reference_link}\n\n{definition}\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"{reference_link}\n\n{definition}\n[[ReAct]] prose\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    ("reference_link", "definition"),
    [
        ("[ReAct][method]", "[method]:\n  https://example.test/react"),
        ("[ReAct][]", "[ReAct]:\n  https://example.test/react"),
        ("[ReAct]", "[ReAct]:\n  https://example.test/react"),
    ],
    ids=["full", "collapsed", "shortcut"],
)
def test_second_final_review_protects_next_line_reference_destinations(
    tmp_path: Path, reference_link: str, definition: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"{reference_link}\n\n{definition}\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"{reference_link}\n\n{definition}\n[[ReAct]] prose\n"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "definition",
    [
        '[method]: /react\n  "ReAct title"',
        '[method]: /react\n  "A title\n  containing ReAct"',
    ],
    ids=["continuation-title", "multiline-title"],
)
def test_second_final_review_protects_complete_reference_definition_titles(
    tmp_path: Path, definition: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"[ReAct][method]\n\n{definition}\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == (
        f"[ReAct][method]\n\n{definition}\n[[ReAct]] prose\n"
    )


@pytest.mark.parametrize(
    "definition",
    [
        b"[method]:\r\n  https://example.test/react",
        b'[method]: /react\r\n  "ReAct title"',
    ],
    ids=["destination-next-line", "title-next-line"],
)
def test_second_final_review_preserves_crlf_reference_definition_blocks(
    tmp_path: Path, definition: bytes
) -> None:
    article = tmp_path / "Paper.md"
    original = b"[ReAct][method]\r\n\r\n" + definition + b"\r\nReAct prose\r\n"
    article.write_bytes(original)

    link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == (
        b"[ReAct][method]\r\n\r\n" + definition + b"\r\n[[ReAct]] prose\r\n"
    )


@pytest.mark.parametrize(
    ("reference_link", "definition"),
    [
        ("[ReAct][method]", "[method]: /react"),
        ("[ReAct][]", "[ReAct]: /react"),
        ("[ReAct]", "[ReAct]: /react"),
    ],
    ids=["full", "collapsed", "shortcut"],
)
def test_final_review_protects_reference_links_inside_block_quotes(
    tmp_path: Path, reference_link: str, definition: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"> {reference_link}\n>\n> {definition}\n\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_final_review_protects_multiline_reference_definitions_in_crlf_block_quotes(
    tmp_path: Path,
) -> None:
    article = tmp_path / "Paper.md"
    original = (
        b"> [ReAct][method]\r\n>\r\n> [method]:\r\n"
        b">   /react\r\n>   \"ReAct title\"\r\n\r\nReAct prose\r\n"
    )
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original.replace(
        b"ReAct prose", b"[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_final_review_skips_setext_and_quoted_atx_headings(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = (
        b"ReAct setext heading\r\n====================\r\n\r\n"
        b"> ReAct quoted setext\r\n> --------------------\r\n\r\n"
        b"> ## ReAct quoted heading\r\n\r\nReAct prose\r\n"
    )
    article.write_bytes(original)

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_bytes() == original.replace(
        b"ReAct prose", b"[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "code_line",
    ["    ReAct code", ">     ReAct quoted code"],
    ids=["top-level", "blockquote"],
)
def test_final_review_skips_indented_code_lines(
    tmp_path: Path, code_line: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"{code_line}\n\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize(
    "line",
    ["   ReAct prose", ">    ReAct prose"],
    ids=["top-level", "blockquote"],
)
def test_final_review_keeps_three_space_indented_prose_linkable(
    tmp_path: Path, line: str
) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(f"{line}\n", encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    expected = f"{line.replace('ReAct', '[[ReAct]]')}\n"
    assert article.read_text(encoding="utf-8") == expected
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_final_review_skips_nested_blockquote_fenced_code(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = "> > ```text\n> > ReAct code\n> > ```\n\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize("marker", ["-", "1."], ids=["bullet", "ordered"])
def test_final_review_skips_atx_headings_inside_list_items(
    tmp_path: Path, marker: str
) -> None:
    article = tmp_path / "Paper.md"
    original = f"{marker} ## ReAct list heading\n\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


@pytest.mark.parametrize("marker", ["-", "1."], ids=["bullet", "ordered"])
def test_final_review_skips_fenced_code_inside_list_items(
    tmp_path: Path, marker: str
) -> None:
    article = tmp_path / "Paper.md"
    indent = " " * (len(marker) + 1)
    original = (
        f"{marker} ```text\n{indent}ReAct code\n{indent}```\n\nReAct prose\n"
    )
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]


def test_final_review_protects_long_delimiter_inline_code(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    original = "``prefix ` ReAct code``\n\nReAct prose\n"
    article.write_text(original, encoding="utf-8")

    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct"]}],
        digest(article),
    )

    assert article.read_text(encoding="utf-8") == original.replace(
        "ReAct prose", "[[ReAct]] prose"
    )
    assert result["results"] == [{"link_stem": "ReAct", "status": "linked"}]
