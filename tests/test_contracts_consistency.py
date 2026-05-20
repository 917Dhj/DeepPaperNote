from __future__ import annotations

import json
import re
from pathlib import Path

from build_synthesis_bundle import bundle
from contracts import NOTE_REQUIRED_SECTIONS, PAPER_TYPE_VALUES
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
    "paper_type_rationale",
    "dominant_domain",
    "must_cover",
    "key_numbers",
    "real_comparisons",
    "section_plan",
)
REFERENCE_ROUTING_DOCS = (
    "SKILL.md",
    "references/model-synthesis.md",
)
PDF_CONTRACT_DOCS = (
    "SKILL.md",
    "README.md",
    "README.zh-CN.md",
)
PDF_FAIL_CLOSED_BANNED_PHRASES = (
    "clearly labeled degraded",
    "degraded note",
    "provisional rather than finished",
    "abstract only, as the weakest fallback",
    "trustworthy full-text substitute",
)
PDF_FAIL_CLOSED_NEGATIONS = (
    "do not",
    "does not",
    "must not",
    "rather than",
    "instead of",
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


def pdf_contract_docs() -> dict[str, str]:
    docs = {
        doc_name: (PROJECT_ROOT / doc_name).read_text(encoding="utf-8")
        for doc_name in PDF_CONTRACT_DOCS
    }
    docs.update(
        {
            f"references/{path.name}": path.read_text(encoding="utf-8")
            for path in sorted((PROJECT_ROOT / "references").glob("*.md"))
        }
    )
    return docs


def allows_banned_pdf_fallback(text: str, phrase: str) -> bool:
    start = text.find(phrase)
    while start != -1:
        context = text[max(0, start - 80) : start]
        if not any(negation in context for negation in PDF_FAIL_CLOSED_NEGATIONS):
            return True
        start = text.find(phrase, start + len(phrase))
    return False


def test_lint_required_sections_use_canonical_contract() -> None:
    assert tuple(REQUIRED_SECTIONS) == NOTE_REQUIRED_SECTIONS


def test_bundle_required_sections_use_canonical_contract() -> None:
    synthesis = bundle(metadata={}, evidence_wrapper={}, figures_wrapper={}, assets_wrapper={})

    assert tuple(synthesis["writing_contract"]["must_include_sections"]) == NOTE_REQUIRED_SECTIONS


def test_bundle_paper_type_contracts_use_canonical_enum() -> None:
    synthesis = bundle(
        metadata={},
        evidence_wrapper={"summary": {"paper_type": "benchmark_or_dataset"}},
        figures_wrapper={},
        assets_wrapper={},
    )
    writing_contract = synthesis["writing_contract"]

    assert tuple(writing_contract["paper_type_contracts"]) == PAPER_TYPE_VALUES
    assert tuple(writing_contract["paper_type_selection"]["allowed_paper_types"]) == PAPER_TYPE_VALUES
    assert writing_contract["paper_type_selection"]["source_of_truth"] == "note_plan.paper_type"
    assert writing_contract["paper_type_selection"]["suggested_paper_type_role"] == "hint_only"


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


def test_normal_execution_docs_do_not_force_broad_reference_reads() -> None:
    for doc_name in REFERENCE_ROUTING_DOCS:
        text = (PROJECT_ROOT / doc_name).read_text(encoding="utf-8")

        assert "Read [references/" not in text
        assert "Use [references/" not in text

    skill_text = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    model_synthesis_text = (PROJECT_ROOT / "references" / "model-synthesis.md").read_text(encoding="utf-8")

    assert "not a default reading checklist" in skill_text
    assert "not a second router" in model_synthesis_text


def test_evidence_first_note_plan_example_matches_lint_contract() -> None:
    text = (PROJECT_ROOT / "references" / "evidence-first.md").read_text(encoding="utf-8")

    assert "```xml" not in text
    match = re.search(r"Recommended shape:\n\n```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert match is not None
    example = json.loads(match.group(1))

    assert tuple(example.keys()) == NOTE_PLAN_REQUIRED_FIELDS
    assert all(isinstance(example[field], str) for field in NOTE_PLAN_REQUIRED_FIELDS[:3])
    assert all(isinstance(example[field], list) for field in NOTE_PLAN_REQUIRED_FIELDS[3:])
    assert example["paper_type"] in PAPER_TYPE_VALUES
    assert example["section_plan"]


def test_pdf_contract_docs_do_not_allow_degraded_finished_notes() -> None:
    offending: list[str] = []
    for doc_name, text in pdf_contract_docs().items():
        normalized = text.lower()
        for phrase in PDF_FAIL_CLOSED_BANNED_PHRASES:
            if allows_banned_pdf_fallback(normalized, phrase):
                offending.append(f"{doc_name}: {phrase}")

    assert offending == []


def test_pdf_contract_banned_phrase_matcher_catches_allowed_fallbacks() -> None:
    for phrase in PDF_FAIL_CLOSED_BANNED_PHRASES:
        assert allows_banned_pdf_fallback(f"you may produce a {phrase}.", phrase)

    assert not allows_banned_pdf_fallback(
        "ask for OCR or a better source rather than finishing a degraded note.",
        "degraded note",
    )


def test_pdf_contract_docs_try_supported_acquisition_before_stopping() -> None:
    skill_text = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow_text = (PROJECT_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    readme_text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh_text = (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    source_priority = skill_text.index("## Tool and Source Priority")
    stop_policy = skill_text.index("If PDF or evidence quality is insufficient")
    assert source_priority < stop_policy

    for required_source in (
        "local PDF path given by the user",
        "local Zotero item and local Zotero attachment if available",
        "DOI and publisher metadata",
        "arXiv or open-access PDF sources",
    ):
        assert required_source in skill_text[source_priority:stop_policy]

    assert "Accepted inputs: title, DOI, URL, arXiv ID, local PDF path, Zotero item key." in workflow_text
    assert "Acquire the best available PDF" in workflow_text
    assert "stop and report the blocked stage honestly" in workflow_text
    assert "A title, DOI, URL, arXiv ID, or local PDF all work." in readme_text
    assert "标题、DOI、URL、本地 PDF 都可以" in readme_zh_text
