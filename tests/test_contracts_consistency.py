from __future__ import annotations

import json
import re
from pathlib import Path

from build_synthesis_bundle import bundle
from contracts import NOTE_REQUIRED_SECTIONS
from lint_note import REQUIRED_SECTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTE_PLAN_REFERENCE_DOCS = (
    "workflow.md",
    "evidence-first.md",
    "final-writing.md",
    "model-synthesis.md",
    "note-quality.md",
)
NOTE_PLAN_REQUIRED_FIELDS = (
    "paper_type",
    "dominant_domain",
    "must_cover",
    "key_numbers",
    "real_comparisons",
    "section_plan",
)


def note_quality_structural_sections() -> tuple[str, ...]:
    text = (PROJECT_ROOT / "references" / "note-quality.md").read_text(encoding="utf-8")
    start = text.index("The note should usually include:")
    end = text.index("For non-trivial papers", start)
    sections: list[str] = []
    for line in text[start:end].splitlines():
        line = line.strip()
        if line.startswith("- `") and line.endswith("`"):
            sections.append(line.removeprefix("- `").removesuffix("`"))
    return tuple(sections)


def test_lint_required_sections_use_canonical_contract() -> None:
    assert tuple(REQUIRED_SECTIONS) == NOTE_REQUIRED_SECTIONS


def test_bundle_required_sections_use_canonical_contract() -> None:
    synthesis = bundle(metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={})

    assert tuple(synthesis["writing_contract"]["must_include_sections"]) == NOTE_REQUIRED_SECTIONS


def test_note_quality_structural_sections_match_canonical_contract() -> None:
    assert note_quality_structural_sections() == NOTE_REQUIRED_SECTIONS


def test_note_plan_docs_make_json_file_canonical() -> None:
    for doc_name in NOTE_PLAN_REFERENCE_DOCS:
        text = (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8")

        assert "canonical" in text.lower()
        assert "short JSON" in text
        assert "scripts/lint_note.py --plan-file ..." in text
        assert "<note>.plan.json" in text
        assert "*_note_plan.json" in text


def test_note_plan_xml_mentions_are_display_only() -> None:
    for doc_name in NOTE_PLAN_REFERENCE_DOCS:
        lines = (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8").splitlines()

        for line in lines:
            if "<note_plan>" in line:
                normalized = line.lower()
                assert "interactive" in normalized
                assert "display-only" in normalized


def test_note_plan_docs_do_not_offer_xml_or_temporary_files_as_alternatives() -> None:
    combined = "\n".join(
        (PROJECT_ROOT / "references" / doc_name).read_text(encoding="utf-8")
        for doc_name in NOTE_PLAN_REFERENCE_DOCS
    )

    note_plan_tag = "`<note_" + "plan>...</note_" + "plan>`"
    conjunction = "o" + "r"
    banned_phrases = (
        "equivalent temporary " + "planning file",
        "equivalent temporary " + "plan file",
        "dynamic internal note " + "plan",
        "planning block such as " + note_plan_tag,
        "planning artifact such as " + note_plan_tag,
        "- a compact " + note_plan_tag + " block\n- " + conjunction,
    )
    for phrase in banned_phrases:
        assert phrase not in combined


def test_evidence_first_note_plan_example_matches_lint_contract() -> None:
    text = (PROJECT_ROOT / "references" / "evidence-first.md").read_text(encoding="utf-8")

    assert "```xml" not in text
    match = re.search(r"Recommended shape:\n\n```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert match is not None
    example = json.loads(match.group(1))

    assert tuple(example.keys()) == NOTE_PLAN_REQUIRED_FIELDS
    assert all(isinstance(example[field], str) for field in NOTE_PLAN_REQUIRED_FIELDS[:2])
    assert all(isinstance(example[field], list) for field in NOTE_PLAN_REQUIRED_FIELDS[2:])
    assert example["section_plan"]
