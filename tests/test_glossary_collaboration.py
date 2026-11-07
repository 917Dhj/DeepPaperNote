from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from formal_save_helpers import formal_save_args

import build_synthesis_bundle
import glossary_terms
import lint_note
from localization import note_schema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"
ZH_GUIDANCE = note_schema("zh-CN")["my_notes_guidance"]


def term_note(terms_dir: Path, stem: str, *, aliases: str = "[]", heading: str = "") -> Path:
    path = terms_dir / f"{stem}.md"
    path.write_text(f"---\naliases: {aliases}\ntags: [term]\n---\n\n# {heading or stem}\n", encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    terms = root / "Glossary"
    terms.mkdir()
    term_note(terms, "DPO", aliases='["Direct Preference Optimization"]')
    term_note(terms, "ACT", aliases="[Adaptive Computation Time]")
    term_note(terms, "C＃", aliases='["C#"]', heading="C#")
    term_note(terms, "注意力机制", aliases="[attention mechanism]")
    term_note(terms, "Unused Term")
    paper = root / "Papers" / "AI" / "Some_Paper"
    paper.mkdir(parents=True)
    (paper / "Some_Paper.zh-CN.md").write_text("---\ntags: [papers/AI]\n---\n\n# Some Paper\n", encoding="utf-8")
    return root


def glossary_config(tmp_path: Path, vault_root: Path, subdir: str = "Glossary") -> Path:
    path = tmp_path / "glossary-config.json"
    path.write_text(json.dumps({"vault_root": str(vault_root), "terms_subdir": subdir}), encoding="utf-8")
    return path


def dpn_config(vault: Path, mode: str = "obsidian") -> dict:
    return {"save_mode": mode, "obsidian_vault": str(vault), "papers_dir": "Papers"}


BODY = (
    "We train with DPO, i.e. direct preference optimization, and compare to DPO baselines. "
    "Each agent must act quickly; the act of acting is not ACT. "
    "我们使用注意力机制。The C# implementation is public."
)


def recall(tmp_path: Path, vault: Path, body: str = BODY, **kwargs) -> dict:
    config_path = kwargs.pop("config_path", None) or glossary_config(tmp_path, vault)
    return glossary_terms.glossary_terms(
        kwargs.pop("config", None) or dpn_config(vault), body, config_path=config_path
    )


def by_term(result: dict) -> dict[str, dict]:
    return {item["term"]: item for item in result["terms"]}


# --- when the glossary is read -------------------------------------------------


def test_same_vault_glossary_is_read(tmp_path: Path, vault: Path) -> None:
    result = recall(tmp_path, vault)
    assert result["status"] == "ok"
    assert result["terms_dir"] == str((vault / "Glossary").resolve())


def test_workspace_mode_reads_no_glossary(tmp_path: Path, vault: Path) -> None:
    result = recall(tmp_path, vault, config=dpn_config(vault, "workspace"))
    assert (result["status"], result["terms"]) == ("workspace", [])


def test_missing_glossary_configuration(tmp_path: Path, vault: Path) -> None:
    result = recall(tmp_path, vault, config_path=tmp_path / "missing.json")
    assert (result["status"], result["terms"]) == ("not_configured", [])


def test_malformed_glossary_configuration_is_not_configured(tmp_path: Path, vault: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert recall(tmp_path, vault, config_path=bad)["status"] == "not_configured"


def test_glossary_in_another_vault(tmp_path: Path, vault: Path) -> None:
    other = tmp_path / "other"
    (other / ".obsidian").mkdir(parents=True)
    (other / "Glossary").mkdir()
    result = recall(tmp_path, vault, config_path=glossary_config(tmp_path, other))
    assert (result["status"], result["terms"]) == ("other_vault", [])


def test_missing_terms_directory_is_unavailable(tmp_path: Path, vault: Path) -> None:
    result = recall(tmp_path, vault, config_path=glossary_config(tmp_path, vault, "NoSuchDir"))
    assert (result["status"], result["terms"]) == ("unavailable", [])


# --- tolerant reader ----------------------------------------------------------


def test_malformed_term_note_is_skipped_with_a_warning(tmp_path: Path, vault: Path) -> None:
    (vault / "Glossary" / "Broken.md").write_text("---\naliases: [unterminated\n---\n# Broken\n", encoding="utf-8")
    result = recall(tmp_path, vault, body=BODY + " Broken appears too.")
    assert "Broken" not in by_term(result)
    assert any("Broken.md" in warning for warning in result["warnings"])
    assert "DPO" in by_term(result)


def test_name_shared_by_two_notes_is_dropped_from_both(tmp_path: Path, vault: Path) -> None:
    term_note(vault / "Glossary", "Preference Learning", aliases="[DPO]")
    result = recall(tmp_path, vault, body="DPO is used. Direct Preference Optimization too.")
    terms = by_term(result)
    assert terms["DPO"]["matched_forms"] == ["Direct Preference Optimization"]
    assert "Preference Learning" not in terms
    assert any("dpo" in warning.casefold() for warning in result["warnings"])


def test_subdirectories_of_the_terms_directory_are_not_read(tmp_path: Path, vault: Path) -> None:
    nested = vault / "Glossary" / "archive"
    nested.mkdir()
    term_note(nested, "Nested Term")
    assert "Nested Term" not in by_term(recall(tmp_path, vault, body="Nested Term here."))


# --- matching -----------------------------------------------------------------


def test_terms_found_in_the_body_with_counts_and_forms(tmp_path: Path, vault: Path) -> None:
    terms = by_term(recall(tmp_path, vault))
    assert terms["DPO"]["matched_forms"] == ["DPO", "Direct Preference Optimization"]
    assert terms["DPO"]["occurrences"] == 3
    assert terms["注意力机制"]["matched_forms"] == ["注意力机制"]
    assert "Unused Term" not in terms


def test_all_caps_acronym_is_case_sensitive(tmp_path: Path, vault: Path) -> None:
    terms = by_term(recall(tmp_path, vault))
    assert terms["ACT"]["occurrences"] == 1
    assert "ACT" not in by_term(recall(tmp_path, vault, body="Agents act and react."))


def test_terms_are_sorted_by_occurrences_and_capped(tmp_path: Path, vault: Path) -> None:
    for i in range(45):
        term_note(vault / "Glossary", f"Concept{i:02d}")
    body = " ".join(f"Concept{i:02d} " * (i % 3 + 1) for i in range(45)) + " DPO DPO DPO DPO DPO"
    result = recall(tmp_path, vault, body=body)
    assert len(result["terms"]) == glossary_terms.MAX_TERMS == 40
    assert result["terms"][0]["term"] == "DPO"
    counts = [item["occurrences"] for item in result["terms"]]
    assert counts == sorted(counts, reverse=True)


def test_body_text_excludes_the_references_section(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(
        "\n".join(json.dumps(record) for record in [
            {"record_type": "section", "kind": "method", "text": "We use DPO."},
            {"record_type": "section", "kind": "references", "text": "Rafailov 2023. Direct Preference Optimization."},
            {"record_type": "figure", "text": "ignored"},
        ]),
        encoding="utf-8",
    )
    assert glossary_terms.body_text_from_raw_sections(raw) == "We use DPO."
    assert glossary_terms.body_text_from_raw_sections(tmp_path / "missing.jsonl") == ""


# --- links ----------------------------------------------------------------------


def test_link_is_the_stem_when_unique(tmp_path: Path, vault: Path) -> None:
    terms = by_term(recall(tmp_path, vault))
    assert terms["DPO"]["link"] == "[[DPO]]"
    assert terms["C#"]["link"] == "[[C＃|C#]]"


def test_link_carries_the_path_when_the_stem_is_not_unique(tmp_path: Path, vault: Path) -> None:
    project = vault / "Projects"
    project.mkdir()
    (project / "DPO.md").write_text("# A project note\n", encoding="utf-8")
    assert by_term(recall(tmp_path, vault))["DPO"]["link"] == "[[Glossary/DPO|DPO]]"


def test_bundle_carries_glossary_terms(tmp_path: Path, vault: Path, monkeypatch) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"record_type": "section", "kind": "method", "text": "We use DPO."}), encoding="utf-8")
    monkeypatch.setattr(build_synthesis_bundle, "runtime_config", lambda **_: {**dpn_config(vault), "output_language": "zh-CN"})
    monkeypatch.setattr(glossary_terms, "default_config_path", lambda: glossary_config(tmp_path, vault))
    synthesis = build_synthesis_bundle.bundle(
        metadata={"title": "Paper"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={"output_language": "zh-CN", "figure_plan": {}},
        assets_wrapper={},
        figure_decisions_wrapper={"output_language": "zh-CN", "decisions": []},
        source_manifest={
            "raw_sections_path": str(raw),
            "identity_contract": {
                "artifact_type": "canonical_identity", "schema_version": 2, "paper_id": "paper:x",
                "identity_verdict": "accepted", "work_level_identity": {"title": "Paper"},
                "accepted_metadata": {"title": "Paper"},
            },
        },
    )
    assert [item["link"] for item in synthesis["glossary_terms"]["terms"]] == ["[[DPO]]"]
    assert synthesis["writing_contract"]["frontmatter_contract"]["term_link_source"] == "glossary_terms"


# --- Final Note Lint: body links ------------------------------------------------


@pytest.fixture(autouse=True)
def zh_profile():
    lint_note.configure_output_language("zh-CN")
    yield
    lint_note.configure_output_language("zh-CN")


NOTE_TAIL = "## 关联\n\n### 库内笔记\n\n- [[Some_Paper.zh-CN|Some Paper]]（基线/对比）：主要对照。\n\n## 我的笔记\n\n"


def body_link_reasons(text: str) -> list[str]:
    return [str(item["reason"]) for item in lint_note.body_wikilink_issues(text)]


def test_links_in_connections_frontmatter_embeds_and_my_notes_are_allowed() -> None:
    text = (
        '---\nmethods: ["[[DPO]]"]\n---\n\n# Paper\n\n## 方法主线\n\n![[images/fig1.png]]\n\n'
        + NOTE_TAIL + "想读 [[还没写的笔记]]。\n"
    )
    assert body_link_reasons(text) == []


def test_a_link_in_the_body_is_an_error() -> None:
    text = "# Paper\n\n## 方法主线\n\n本文使用 [[DPO]] 训练。\n\n" + NOTE_TAIL + ZH_GUIDANCE + "\n"
    issues = lint_note.body_wikilink_issues(text)
    assert [(item["section"], item["reason"], item["severity"]) for item in issues] == [
        ("方法主线", "wikilink_outside_connections", "error")
    ]


def test_body_link_issue_counts_as_substantive_content() -> None:
    text = "# Paper\n\n## 方法主线\n\n本文使用 [[DPO]] 训练。\n\n" + NOTE_TAIL + ZH_GUIDANCE + "\n"
    assert "wikilink_outside_connections" in {item["reason"] for item in lint_note.inspect_substantive_content(text)}


def test_english_prose_no_longer_exempts_cjk_wikilinks() -> None:
    lint_note.configure_output_language("en")
    text = "# Paper\n\n## Method\n\nThe model follows [[注意力机制]] closely.\n"
    assert lint_note.mixed_language_issues(text)


# --- Formal Save ----------------------------------------------------------------


def run_writer(tmp_path: Path, home: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run([sys.executable, str(WRITE_SCRIPT), *args], cwd=tmp_path, env=env, capture_output=True, text=True)


def home_with_glossary(tmp_path: Path, vault_root: Path | None) -> Path:
    home = tmp_path / "home"
    (home / ".paper-glossary").mkdir(parents=True)
    if vault_root is not None:
        (home / ".paper-glossary" / "config.json").write_text(
            json.dumps({"vault_root": str(vault_root), "terms_subdir": "Glossary"}), encoding="utf-8"
        )
    return home


def frontmatter_note(methods: str) -> str:
    return (
        f"---\ntags: [papers/AI]\nmethods: [{methods}]\n---\n\n# My Test Paper\n\n## 局限\n\n正文。\n\n"
        f"## 我的笔记\n\n{ZH_GUIDANCE}\n"
    )


def save(tmp_path: Path, vault: Path, home: Path, text: str) -> subprocess.CompletedProcess:
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(json.dumps({"status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64}), encoding="utf-8")
    return run_writer(
        tmp_path, home, "--vault", str(vault), "--papers-dir", "Papers", "--title", "My Test Paper",
        "--source-manifest", str(manifest), *formal_save_args(tmp_path, text, domain="AI"),
    )


def receipt(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_frontmatter_link_to_a_glossary_term_saves(tmp_path: Path, vault: Path) -> None:
    home = home_with_glossary(tmp_path, vault)
    payload = receipt(save(tmp_path, vault, home, frontmatter_note('"[[DPO]]", "[[Glossary/C＃|C#]]"')))
    followup = payload["glossary_followup"]
    assert followup["status"] == "suggested"
    assert followup["terms_dir"] == str((vault / "Glossary").resolve())
    assert followup["note_path"] == payload["note_path"]
    assert followup["source_manifest"] == str((tmp_path / "source-manifest.json").resolve())
    assert followup["regenerated"] is False


def test_frontmatter_link_to_a_paper_note_is_refused(tmp_path: Path, vault: Path) -> None:
    home = home_with_glossary(tmp_path, vault)
    result = save(tmp_path, vault, home, frontmatter_note('"[[Some_Paper.zh-CN]]"'))
    assert result.returncode != 0
    assert "Some_Paper.zh-CN" in result.stdout + result.stderr


def test_frontmatter_link_without_a_glossary_is_refused(tmp_path: Path, vault: Path) -> None:
    home = home_with_glossary(tmp_path, None)
    result = save(tmp_path, vault, home, frontmatter_note('"[[DPO]]"'))
    assert result.returncode != 0
    assert "glossary" in (result.stdout + result.stderr).lower()


def test_no_glossary_means_no_suggestion(tmp_path: Path, vault: Path) -> None:
    home = home_with_glossary(tmp_path, None)
    payload = receipt(save(tmp_path, vault, home, frontmatter_note("plain method")))
    assert payload["glossary_followup"]["status"] == "not_configured"
