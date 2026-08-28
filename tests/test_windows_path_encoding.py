"""Regression tests for cross-platform (Windows) path & encoding robustness.

Each test feeds a Windows-flavored input — a UTF-8 BOM, CRLF line endings, or a
backslash path separator — to a code path that previously assumed
BOM-less / LF / forward-slash input. They fail on the pre-fix code and pass
after the fixes in this branch. They are platform-agnostic: the inputs are
constructed explicitly, so they also guard the behavior when run on Linux CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import citation_links
import common
import lint_grounding
import lint_note
import plan_figure_table_decisions
import write_obsidian_note
from common import load_json_file, resolve_obsidian_note_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"
BOM = "﻿"


def _formal_save_artifacts(tmp_path: Path, canonical_note_text: str) -> tuple[Path, Path]:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "note_sha256": hashlib.sha256(
                    canonical_note_text.encode("utf-8")
                ).hexdigest(),
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
            }
        ),
        encoding="utf-8",
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps({"output_language": "zh-CN", "decisions": []}),
        encoding="utf-8",
    )
    return lint_path, decisions_path


def _source_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "source-manifest.json"
    path.write_text(
        json.dumps({"status": "ok", "source_sha256": "a" * 64}),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# BOM handling (utf-8-sig)                                                     #
# --------------------------------------------------------------------------- #
def test_load_json_file_strips_bom(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    # A UTF-8 BOM is exactly what PowerShell Out-File / Notepad prepend.
    path.write_bytes(BOM.encode("utf-8") + json.dumps({"status": "ok"}).encode("utf-8"))
    assert load_json_file(path) == {"status": "ok"}


def test_lint_grounding_load_record_strips_bom(tmp_path: Path) -> None:
    # A path without a .json suffix skips maybe_load_json_record and hits the
    # direct read branch that previously used plain utf-8.
    path = tmp_path / "note_plan"
    path.write_bytes(BOM.encode("utf-8") + json.dumps({"paper_type": "AI_method"}).encode("utf-8"))
    assert lint_grounding.load_record(str(path)) == {"paper_type": "AI_method"}


def test_shell_config_value_strips_bom(tmp_path: Path, monkeypatch) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_bytes(
        BOM.encode("utf-8") + b"export DEEPPAPERNOTE_OBSIDIAN_VAULT=/home/u/vault\n"
    )
    monkeypatch.setattr(common, "SHELL_CONFIG_FILES", [rc])
    # Without utf-8-sig the BOM sits before "export", so the first line fails
    # the `^\s*(?:export\s+)?NAME=` regex and the value is not found.
    assert common.shell_config_value("DEEPPAPERNOTE_OBSIDIAN_VAULT") == "/home/u/vault"


def test_load_domain_rules_strips_bom(tmp_path: Path, monkeypatch) -> None:
    rules_yaml = (
        "domains:\n"
        "  - label: 测试专用域ZZZ\n"
        "    aliases:\n"
        "      - zzztestalias\n"
        "    keywords:\n"
        "      - zzztestkeyword\n"
    )
    path = tmp_path / "domain_rules.yaml"
    path.write_bytes(BOM.encode("utf-8") + rules_yaml.encode("utf-8"))
    monkeypatch.setattr(common, "DOMAIN_RULES_PATH", path)
    rules = common.load_domain_rules()
    labels = [d.get("label") for d in rules.get("domains", [])]
    # If the BOM were not stripped, the top-level `domains:` key would be
    # "﻿domains", the section would be skipped, and load_domain_rules would
    # silently fall back to the built-in defaults (which lack this label).
    assert "测试专用域ZZZ" in labels


def test_citation_index_includes_bom_prefixed_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "attention_transformer.md").write_bytes(
        BOM.encode("utf-8")
        + "---\naliases:\n  - Attention Is All You Need\n---\n# Transformer\n".encode("utf-8")
    )
    candidates = [{"display_text": "Vaswani et al. (2017). Attention Is All You Need."}]
    resolved = citation_links.resolve_reference_links(candidates, {"obsidian_vault": str(vault)})
    # A BOM before "---" used to break the frontmatter check, dropping the note
    # from the index so the wiki-link never resolved.
    assert resolved[0]["match_status"] == "vault_match"
    assert resolved[0]["vault_target"] == "attention_transformer"


# --------------------------------------------------------------------------- #
# CRLF handling                                                                #
# --------------------------------------------------------------------------- #
def test_strip_frontmatter_handles_crlf() -> None:
    note = "---\r\ntags:\r\n  - x\r\n---\r\n# Real Title\r\n\r\nbody\r\n"
    body = lint_note.strip_frontmatter(note)
    # Frontmatter must be removed even with CRLF; otherwise the leading "---"
    # remains and the note is falsely flagged as missing its H1 title.
    assert body.lstrip().startswith("# Real Title")
    assert "tags:" not in body


# --------------------------------------------------------------------------- #
# Path separators                                                              #
# --------------------------------------------------------------------------- #
def test_resolve_obsidian_note_path_no_double_papers_prefix(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(
        config,
        title="Some Paper",
        subdir="Research/Papers/大模型/Some_Paper",
    )
    # The papers_dir prefix must appear exactly once (the pre-fix code compared
    # str(Path(subdir)) — backslashes on Windows — and duplicated the prefix).
    assert path.relative_to(vault).parts.count("Research") == 1
    assert path == vault / "Research/Papers" / "大模型" / "Some_Paper" / "Some_Paper.md"


def test_source_image_filename_handles_backslash_path() -> None:
    plan_item = {
        "figure_asset_candidate": {
            "path": r"C:\vault\Research\Papers\大模型\Paper\images\page_004_fig.png",
            "filename": "",
        }
    }
    # rsplit("/", ...) alone would return the whole backslash path as the
    # "filename", producing a broken Markdown image embed.
    assert plan_figure_table_decisions.source_image_filename(plan_item) == "page_004_fig.png"


def test_windows_sidecar_hidden_attribute_preserves_existing_attributes(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / ".deeppapernote.json"
    sidecar.write_text("{}", encoding="utf-8")
    attributes = {"value": 0x20}

    def get_attributes(_path: str) -> int:
        return attributes["value"]

    def set_attributes(_path: str, value: int) -> bool:
        attributes["value"] = value
        return True

    write_obsidian_note.ensure_sidecar_hidden(
        sidecar,
        platform="nt",
        get_attributes=get_attributes,
        set_attributes=set_attributes,
    )

    assert attributes["value"] == 0x20 | 0x2


# --------------------------------------------------------------------------- #
# End-to-end (subprocess) — the script main() read paths                      #
# --------------------------------------------------------------------------- #
def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    return env


def test_lint_note_detects_title_in_bom_crlf_note(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    content = "---\ntags:\n  - papers/x\n---\n# 标题\n\n正文\n".replace("\n", "\r\n")
    note.write_bytes(BOM.encode("utf-8") + content.encode("utf-8"))
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "lint_note.py"), "--input", str(note)],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    # BOM + CRLF used to defeat both strip_frontmatter and the "starts with #"
    # check, producing a spurious title_heading_missing warning.
    assert "title_heading_missing" not in payload["warnings"]


def test_write_obsidian_note_strips_bom_from_saved_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    content_file = tmp_path / "note.md"
    content_file.write_bytes(
        BOM.encode("utf-8") + "# 标题\n\n正文内容。\n".encode("utf-8")
    )
    canonical_note_text = "# 标题\n\n正文内容。\n"
    lint_path, decisions_path = _formal_save_artifacts(tmp_path, canonical_note_text)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "write_obsidian_note.py"),
            "--title", "BOM Content Test",
            "--vault", str(vault),
            "--content-file", str(content_file),
            "--lint-json", str(lint_path),
            "--figure-decisions", str(decisions_path),
            "--source-manifest", str(_source_manifest(tmp_path)),
        ],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    saved = Path(payload["note_path"]).read_text(encoding="utf-8")
    # The BOM must not survive into the saved note (it breaks Obsidian
    # frontmatter / the H1 title).
    assert not saved.startswith(BOM)
    assert saved.lstrip().startswith("# 标题")
    if os.name == "nt":
        sidecar = Path(payload["sidecar_path"])
        assert sidecar.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN


def test_write_obsidian_note_accepts_unchanged_crlf_after_final_lint(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    content_file = tmp_path / "note.md"
    crlf_text = "# CRLF Note\r\n\r\n正文内容。\r\n"
    content_file.write_bytes(crlf_text.encode("utf-8"))
    lint_output = tmp_path / "lint-from-script.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "lint_note.py"),
            "--input", str(content_file),
            "--output", str(lint_output),
        ],
        cwd=tmp_path,
        env=_clean_env(),
        check=True,
    )
    lint = json.loads(lint_output.read_text(encoding="utf-8"))
    lint.update({key: True for key in lint if key.startswith("passes_")})
    lint_output.write_text(json.dumps(lint), encoding="utf-8")
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps({"output_language": "zh-CN", "decisions": []}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "write_obsidian_note.py"),
            "--title", "CRLF Note",
            "--vault", str(vault),
            "--content-file", str(content_file),
            "--lint-json", str(lint_output),
            "--figure-decisions", str(decisions_path),
            "--source-manifest", str(_source_manifest(tmp_path)),
        ],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    saved = Path(json.loads(result.stdout)["note_path"]).read_bytes()
    assert b"\r\n" not in saved


def test_materialize_figure_asset_embed_uses_forward_slashes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source_image = tmp_path / "fig.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\n")  # header bytes are enough
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "materialize_figure_asset.py"),
            "--title", "Embed Slash Test",
            "--vault", str(vault),
            "--source-image", str(source_image),
        ],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # str(Path) would embed backslashes on Windows and break the Markdown link.
    assert "\\" not in payload["absolute_markdown_embed"]
    assert "\\" not in payload["relative_markdown_embed"]
