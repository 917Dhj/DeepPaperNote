from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from formal_save_helpers import formal_save_args

import _frontmatter
import build_synthesis_bundle
import lint_note

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"
LINT_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "lint_note.py"

GOOD = """---
tags:
  - papers/机器学习
aliases:
  - "Self-Instruct"
date: 2023-07-09
doi: 10.18653/v1/2023.acl-long.754
paper_type: method
methods: [instruction tuning, "self-generated data"]
datasets:
  - SuperNI
tasks: []
read_date: 2026-11-06
---

# Paper
"""


# --- parser ----------------------------------------------------------------


def test_parser_reads_scalars_block_lists_and_flow_lists() -> None:
    fields = _frontmatter.parse_frontmatter(GOOD)
    assert fields["tags"] == ["papers/机器学习"]
    assert fields["aliases"] == ["Self-Instruct"]
    assert fields["date"] == "2023-07-09"
    assert fields["paper_type"] == "method"
    assert fields["methods"] == ["instruction tuning", "self-generated data"]
    assert fields["datasets"] == ["SuperNI"]
    assert fields["tasks"] == []
    assert fields["read_date"] == "2026-11-06"


def test_parser_keeps_quoted_wikilinks_and_commas_inside_quotes() -> None:
    text = '---\nmethods: ["[[DPO]]", "a, b"]\ndatasets:\n  - "[[MMLU]]"\n---\n'
    fields = _frontmatter.parse_frontmatter(text)
    assert fields["methods"] == ["[[DPO]]", "a, b"]
    assert fields["datasets"] == ["[[MMLU]]"]


def test_parser_returns_none_without_frontmatter() -> None:
    assert _frontmatter.parse_frontmatter("# Paper\n") is None


@pytest.mark.parametrize(
    "block",
    [
        "tags:\n  nested: value\n",
        "  - orphan item\n",
        "not a key line\n",
        "tags: [unterminated\n",
        "tags: a\ntags: b\n",
    ],
)
def test_parser_rejects_shapes_it_cannot_read(block: str) -> None:
    with pytest.raises(_frontmatter.FrontmatterError):
        _frontmatter.parse_frontmatter(f"---\n{block}---\n")


def test_parser_rejects_unclosed_frontmatter() -> None:
    with pytest.raises(_frontmatter.FrontmatterError):
        _frontmatter.parse_frontmatter("---\ntags: [a]\n# Paper\n")


# --- lint checks -----------------------------------------------------------


def codes(text: str, paper_type: str = "method") -> set[str]:
    return set(lint_note.frontmatter_issues(text, paper_type))


def test_complete_frontmatter_passes() -> None:
    assert codes(GOOD) == set()


def test_missing_frontmatter_is_reported() -> None:
    assert codes("# Paper\n") == {"frontmatter_missing"}


def test_unparseable_frontmatter_is_reported() -> None:
    assert codes("---\ntags:\n  nested: v\n---\n# P\n") == {"frontmatter_unparseable"}


@pytest.mark.parametrize("field", ["paper_type", "methods", "datasets", "tasks", "read_date"])
def test_each_new_field_is_required(field: str) -> None:
    lines = [line for line in GOOD.splitlines(keepends=True) if not line.startswith(f"{field}:")]
    if field == "datasets":
        lines = [line for line in lines if line != "  - SuperNI\n"]
    assert "frontmatter_field_missing" in codes("".join(lines))


def test_domain_tag_is_required() -> None:
    assert "frontmatter_domain_tag_missing" in codes(GOOD.replace("papers/机器学习", "reading"))


def test_only_one_domain_tag_is_allowed() -> None:
    two = GOOD.replace("  - papers/机器学习\n", "  - papers/机器学习\n  - papers/多模态\n")
    assert "frontmatter_domain_tag_multiple" in codes(two)
    topical = GOOD.replace("  - papers/机器学习\n", "  - papers/机器学习\n  - instruction-data\n")
    assert "frontmatter_domain_tag_multiple" not in codes(topical)


def test_paper_type_must_match_the_plan() -> None:
    assert "frontmatter_paper_type_mismatch" in codes(GOOD, paper_type="benchmark_or_dataset")
    assert "frontmatter_paper_type_mismatch" not in codes(GOOD, paper_type="")


@pytest.mark.parametrize(
    "replacement",
    [
        "methods: [a, b, c, d, e, f]",
        "methods: instruction tuning",
    ],
)
def test_list_fields_are_lists_of_at_most_five(replacement: str) -> None:
    text = GOOD.replace('methods: [instruction tuning, "self-generated data"]', replacement)
    assert "frontmatter_list_field_invalid" in codes(text)


@pytest.mark.parametrize("value", ["2026-11", "06/11/2026", "2026-13-01", ""])
def test_read_date_must_be_an_iso_day(value: str) -> None:
    assert "frontmatter_read_date_invalid" in codes(GOOD.replace("read_date: 2026-11-06", f"read_date: {value}"))


def test_frontmatter_issues_fail_basic_structure_in_cli(tmp_path: Path) -> None:
    from test_lint_note import _valid_note_text, _valid_plan_payload

    note = tmp_path / "note.md"
    note.write_text(lint_note.strip_frontmatter(_valid_note_text()), encoding="utf-8")
    plan = tmp_path / "note.plan.json"
    plan.write_text(json.dumps(_valid_plan_payload(), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "--input", str(note), "--plan-file", str(plan), "--language", "zh-CN"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["frontmatter_issues"] == ["frontmatter_missing"]
    assert payload["passes_basic_structure"] is False


def test_valid_fixture_note_passes_frontmatter_checks() -> None:
    from test_lint_note import _valid_note_text

    assert lint_note.frontmatter_issues(_valid_note_text(), "method") == []


def test_writing_contract_describes_the_frontmatter() -> None:
    for language in ("zh-CN", "en"):
        contract = build_synthesis_bundle.compact_writing_contract(language)["frontmatter_contract"]
        assert contract["required_fields"] == ["paper_type", "methods", "datasets", "tasks", "read_date"]
        assert contract["list_fields"] == ["methods", "datasets", "tasks"]
        assert contract["max_list_items"] == 5
        assert contract["domain_tag_prefix"] == "papers/"


# --- read_date carried across an overwrite ---------------------------------


def run_writer(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    return subprocess.run(
        [sys.executable, str(WRITE_SCRIPT), *args], cwd=tmp_path, env=env, capture_output=True, text=True
    )


def source_manifest_args(tmp_path: Path) -> list[str]:
    path = tmp_path / "source-manifest.json"
    path.write_text(json.dumps({"status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64}), encoding="utf-8")
    return ["--source-manifest", str(path)]


def test_overwrite_conflict_and_preflight_report_existing_read_date(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    first = run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper",
        *source_manifest_args(tmp_path), *formal_save_args(tmp_path, GOOD.replace("2026-11-06", "2026-01-15"), domain="机器学习"),
    )
    assert first.returncode == 0, first.stderr
    conflict = run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper", "--preflight", "--language", "zh-CN",
        *source_manifest_args(tmp_path),
    )
    assert conflict.returncode == 2
    blocked = json.loads(conflict.stdout)
    assert blocked["existing_read_date"] == "2026-01-15"
    approved = run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper", "--preflight", "--language", "zh-CN",
        "--overwrite-existing-note", "--expected-existing-note-sha256", blocked["existing_note_sha256"],
        *source_manifest_args(tmp_path),
    )
    assert approved.returncode == 0, approved.stderr
    assert json.loads(approved.stdout)["existing_read_date"] == "2026-01-15"


def test_existing_note_without_read_date_reports_empty(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    first = run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper",
        *source_manifest_args(tmp_path), *formal_save_args(tmp_path, "# My Test Paper\n\nOld note.\n"),
    )
    assert first.returncode == 0, first.stderr
    conflict = run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper", "--preflight", "--language", "zh-CN",
        *source_manifest_args(tmp_path),
    )
    assert json.loads(conflict.stdout)["existing_read_date"] == ""
