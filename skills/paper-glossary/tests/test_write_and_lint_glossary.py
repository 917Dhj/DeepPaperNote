from __future__ import annotations

from pathlib import Path

from lint_glossary import GLOSSARY_DISCLAIMER, lint_term_file_text
from write_glossary_terms import (
    build_alias_index,
    render_term_file,
    safe_term_filename,
    upsert_term_file,
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
