from __future__ import annotations

from pathlib import Path

from build_synthesis_bundle import bundle
from contracts import NOTE_REQUIRED_SECTIONS
from lint_note import REQUIRED_SECTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
