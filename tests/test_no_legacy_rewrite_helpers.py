from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_script_side_chinese_rewrite_helpers_are_removed() -> None:
    common_source = (PROJECT_ROOT / "scripts" / "common.py").read_text(encoding="utf-8")

    legacy_names = (
        "TERM_REPLACEMENTS",
        "apply_term_replacements",
        "shorten_clause",
        "english_sentence_to_cn",
        "paraphrase_sentences_to_cn",
        "finalize_cn_line",
    )
    for name in legacy_names:
        assert name not in common_source
