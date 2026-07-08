from __future__ import annotations

from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]


def test_skill_documents_shared_file_contract_not_direct_workflow_call() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "raw_sections_path" in text
    assert "*_source_manifest.json" in text
    assert "*_raw_sections.jsonl" in text
    assert "scripts/run_pipeline.py" not in text


def test_scripts_are_self_contained_within_paper_glossary() -> None:
    scripts = sorted((SKILL_DIR / "scripts").glob("*.py"))
    assert scripts
    for path in scripts:
        text = path.read_text(encoding="utf-8")
        assert "skills.deeppapernote" not in text
        assert "deeppapernote" not in text.lower()
