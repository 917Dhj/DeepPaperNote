from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from build_synthesis_bundle import compact_writing_contract
from lint_grounding import validate_note_plan
from localization import (
    normalize_output_language,
    require_artifact_output_language,
    required_sections,
)
from plan_figures import build_figure_items

ENGLISH_SECTIONS = (
    "Core Information",
    "Abstract",
    "Contributions",
    "One-Sentence Summary",
    "Research Question",
    "Data and Task Definition",
    "Method",
    "Key Results",
    "Deep Analysis",
    "Limitations",
    "Research Notes",
    "References",
)


def english_note() -> str:
    return """---
tags:
  - papers/methods
aliases:
  - "Auditable Tool Use"
date: 2024
doi: 10.1234/example
---

# Auditable Tool Use

## Core Information

- Title: Auditable Tool Use
- Authors: Smith et al.
- Publication date: 2024
- Venue: Example Journal
- DOI: 10.1234/example
- Paper type: AI method

## Abstract

The paper develops an auditable state machine for multi-step question answering and evaluates whether explicit failure records improve answer reliability.

## Contributions

- It joins evidence selection and tool-state tracking in one execution record, preventing failed evidence from silently becoming trusted input.
- It adds explicit rollback states that distinguish missing evidence from reasoning errors and make the final answer traceable.

## One-Sentence Summary

An explicit tool-state record reduces error propagation in multi-step question answering.

## Research Question

How can a multi-step question-answering system remain traceable when retrieval is incomplete, external tools fail, or intermediate results are misused?

## Data and Task Definition

The input contains a question, candidate evidence, and available tools; the output contains an answer, a state trace, and a failure label when completion is unsupported.

## Method

### Mechanism Flow

1. **Input:** A question and candidate evidence. **Operation:** Extract relevant evidence. **Output:** A grounded initial state.
2. **Input:** The current state and tool registry. **Operation:** Align the request with an available tool. **Output:** A planned call.
3. **Input:** Tool output and confidence. **Operation:** Update or roll back the state. **Output:** An auditable execution record.
4. **Input:** The final state. **Operation:** Decode an answer or refusal. **Output:** A response with provenance.

> [!figure] Figure 1 System overview
> Suggested location: Method
> Why it matters: The figure shows how evidence and tool states move through the execution chain.
> Current status: Placeholder retained; the extracted crop is incomplete and cannot be interpreted independently.

## Key Results

Across three datasets, answer accuracy increased from 71.2% to 78.5%, while untraceable errors fell from 18% to 9%.

## Deep Analysis

The important contribution is not only the score increase. Failed calls become inspectable evidence rather than hidden intermediate state, which supports auditing and targeted recovery.

## Limitations

The evaluation covers English question-answering data and a narrow tool set, so it does not establish robustness for multimodal tools or high-latency services.

## Research Notes

The state-record design is reusable in evidence-first paper workflows because it separates missing source material from model interpretation failure.

## References

- Smith et al. (2024). Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example
"""


def plan_payload() -> dict:
    return {
        "output_language": "en",
        "paper_type": "AI_method",
        "paper_type_rationale": "The paper proposes and evaluates a model mechanism.",
        "dominant_domain": "reasoning",
        "must_cover": ["Method"],
        "key_numbers": ["78.5%"],
        "real_comparisons": ["71.2% versus 78.5%"],
        "central_claims": [{
            "claim": "The method improves traceability.",
            "supporting_evidence": [{"section_id": "sec:results"}],
            "what_it_actually_proves": "The reported protocol records tool states.",
            "what_it_does_not_prove": "It does not prove production robustness.",
        }],
        "claim_boundaries": ["Evidence is limited to the reported workflow."],
        "negative_or_limiting_results": ["Multimodal tools were not tested."],
        "mechanism_result_map": ["Rollback states explain fewer untraceable errors."],
        "comparative_positioning": ["Compared with answer-only baselines."],
        "reuse_takeaways": ["Track failure state explicitly."],
        "followup_questions": ["Test missing and delayed tool outputs."],
        "section_plan": [{"section": "Method", "evidence_sources": [{"section_id": "sec:method"}]}],
    }


def test_language_aliases_and_invalid_value() -> None:
    assert normalize_output_language("English") == "en"
    assert normalize_output_language("zh") == "zh-CN"
    with pytest.raises(ValueError):
        normalize_output_language("fr")


def test_artifact_language_requires_exact_supported_value() -> None:
    with pytest.raises(ValueError, match="requires output_language"):
        require_artifact_output_language({}, "Note Plan", "zh-CN")
    with pytest.raises(ValueError, match="requires output_language"):
        require_artifact_output_language(
            {"output_language": "English"},
            "Note Plan",
            "en",
        )


def test_english_contract_exposes_localized_schema() -> None:
    contract = compact_writing_contract("en")
    assert contract["language"] == "en"
    assert tuple(contract["must_include_sections"]) == ENGLISH_SECTIONS
    assert tuple(required_sections("en")) == ENGLISH_SECTIONS
    assert contract["mechanism_flow_heading"] == "Mechanism Flow"
    assert contract["core_info_fields"] == [
        "Title",
        "Translated title",
        "Authors",
        "Institutions",
        "Publication date",
        "Venue",
        "DOI",
        "arXiv",
        "Paper link",
        "Code / Project",
        "Data / Resources",
        "Paper type",
    ]
    assert contract["figure_labels"] == {
        "location": "Suggested location:",
        "reason": "Why it matters:",
        "status": "Current status:",
        "original_caption": "Original paper item:",
    }
    assert contract["abstract_contract"] == {
        "source": "source_abstract",
        "requirement": "faithful_rendering_in_output_language",
        "forbidden_additions": [
            "later_contribution_claims",
            "later_result_interpretation",
            "hindsight_judgment",
        ],
    }
    assert not any("\u4e00" <= character <= "\u9fff" for character in json.dumps(contract, ensure_ascii=False))


def test_english_grounding_accepts_english_section_plan() -> None:
    plan = plan_payload()
    plan["central_claims"][0]["supporting_evidence"] = [{"section_id": "sec:method"}]
    plan["section_plan"] = [
        {
            "section": section,
            "focus": f"Explain the paper-specific evidence and analytical role of {section}.",
            "evidence_sources": [{"section_id": "sec:method"}],
        }
        for section in (
            "Research Question",
            "Data and Task Definition",
            "Method",
            "Key Results",
            "Deep Analysis",
            "Limitations",
        )
    ]
    manifest = {
        "coverage": {"total_pages": 10, "text_truncated": False},
        "sections": [{"section_id": "sec:method", "title": "Method", "page_start": 1, "page_end": 10}],
        "pages": [],
    }
    assert validate_note_plan(plan, manifest, "en") == []


def test_english_figure_plan_uses_english_targets_and_reasons() -> None:
    items = build_figure_items(
        {"figure_captions": [{"id": "Figure 1", "caption": "Overview of the system architecture."}]},
        language="en",
    )
    assert items[0]["section"] == "Mechanism Flow"
    assert "visual" in items[0]["reason"].lower()
    assert not any("\u4e00" <= character <= "\u9fff" for character in json.dumps(items, ensure_ascii=False))


def test_english_note_passes_every_lint_gate_from_user_configuration(
    tmp_path: Path, configured_user_home: Path
) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note_path.write_text(english_note(), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    configured_user_home.write_text(
        json.dumps({"output_language": "en", "save_mode": "workspace"}),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            str(note_path),
            "--plan-file",
            str(plan_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["output_language"] == "en"
    assert payload["warnings"] == []
    assert all(value is True for key, value in payload.items() if key.startswith("passes_"))


def test_english_lint_rejects_chinese_prose(tmp_path: Path) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note_path.write_text(english_note().replace("The important contribution", "这项工作的 contribution"), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"
    subprocess.run([sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)], check=True)
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is False
    assert "mixed_language_lines_present" in payload["warnings"]


@pytest.mark.parametrize(
    ("original", "mixed"),
    [
        ("## Method", "## 方法 Method"),
        ("- Title: Auditable Tool Use", "- 标题 Title: Auditable Tool Use"),
        ("> Why it matters: The figure shows how evidence and tool states move through the execution chain.", "> Why it matters: 这张图 shows how evidence moves."),
        ("*Original paper item: Figure 1. System overview.*", "*Original paper item: Figure 1. 这是系统概览.*"),
    ],
)
def test_english_lint_rejects_chinese_structure_labels_and_captions(
    tmp_path: Path,
    original: str,
    mixed: str,
) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note = english_note()
    if original.startswith("*Original paper item:"):
        note = note.replace(
            "> [!figure] Figure 1 System overview",
            "![Figure 1](images/figure_1.png)\n" + original,
        )
    note_path.write_text(note.replace(original, mixed), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is False
    assert "mixed_language_lines_present" in payload["warnings"]


def test_english_lint_limits_chinese_exemptions_to_marked_source_spans(tmp_path: Path) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    allowed = english_note().replace(
        "- Title: Auditable Tool Use",
        "- Title: `可审计工具使用`",
    ).replace(
        "The important contribution is not only the score increase.",
        "The benchmark also evaluates [通义千问](https://example.org/qwen), and the source defines $\\operatorname{输入}=x$.",
    ).replace(
        "- Smith et al. (2024). Auditable Tool Use for Multi-hop Question Answering. DOI: 10.1234/example",
        "- Smith et al. (2024). [可审计工具使用](https://example.org/paper). DOI: 10.1234/example",
    ) + "\n```json\n{\"label\": \"原始代码输出\"}\n```\n"
    note_path.write_text(allowed, encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is True

    note_path.write_text(
        allowed.replace("- Title: `可审计工具使用`", "- Title: `可审计工具使用` 这是额外说明"),
        encoding="utf-8",
    )
    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is False
    assert payload["mixed_language_issues"][0]["reason"] == "non_english_text_present"


@pytest.mark.parametrize(
    "disguised",
    [
        "`这是一整句中文分析不是稳定专有名词`",
        "`这个方法显著提高了性能`",
        "$\\text{这是一整句中文分析不是公式标签}=x$",
        "$\\text{方法提高了性能}=x$",
        "Plain prose cannot use \\operatorname{输入} outside math delimiters.",
    ],
)
def test_english_lint_rejects_chinese_prose_disguised_as_bounded_span(
    tmp_path: Path,
    disguised: str,
) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note_path.write_text(
            english_note().replace(
                "The important contribution is not only the score increase.",
                disguised,
        ),
        encoding="utf-8",
    )
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is False


@pytest.mark.parametrize(
    ("original", "invalid"),
    [
        ("- Authors: Smith et al.", "- Author: Smith et al."),
        ("### Mechanism Flow", "### mechanism flow"),
    ],
)
def test_english_lint_requires_exact_labels_and_mechanism_heading(
    tmp_path: Path,
    original: str,
    invalid: str,
) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note_path.write_text(english_note().replace(original, invalid), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert not all(value is True for key, value in payload.items() if key.startswith("passes_"))


def test_english_lint_requires_complete_top_level_heading_order(tmp_path: Path) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note = english_note().replace("## Method", "## TEMP").replace("## Key Results", "## Method").replace("## TEMP", "## Key Results")
    note_path.write_text(note, encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_basic_structure"] is False
    assert "top_level_section_profile_invalid" in payload["warnings"]


def test_english_lint_does_not_extend_unclosed_code_exemption_to_rest_of_note(
    tmp_path: Path,
) -> None:
    note_path = tmp_path / "paper.md"
    plan_path = tmp_path / "paper.plan.json"
    output_path = tmp_path / "lint.json"
    note_path.write_text(english_note() + "\n```text\n这是未闭合代码块后的中文\n", encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/lint_note.py"

    subprocess.run(
        [sys.executable, str(script), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(output_path)],
        check=True,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passes_style_gate"] is False
    assert "mixed_language_lines_present" in payload["warnings"]


def test_english_local_pdf_pipeline_lints_and_formally_saves_note_with_images_dir(
    tmp_path: Path,
) -> None:
    fitz = pytest.importorskip("fitz")
    project_root = Path(__file__).resolve().parents[1]
    scripts = project_root / "skills/deeppapernote/scripts"
    pdf_path = tmp_path / "paper.pdf"
    document = fitz.open()
    page = document.new_page()
    source_abstract = "The paper develops an auditable state machine for multi-step question answering and evaluates whether explicit failure records improve answer reliability."
    page.insert_textbox(
        fitz.Rect(72, 72, 540, 500),
        f"Abstract\n{source_abstract}\nMethod\nThe system records tool states.\nResults\nAccuracy is 78.5%.",
    )
    document.save(pdf_path)
    document.close()

    workdir = tmp_path / "run"
    subprocess.run(
        [sys.executable, str(scripts / "run_pipeline.py"), "--input", str(pdf_path), "--workdir", str(workdir), "--prefix", "paper", "--language", "en"],
        check=True,
    )
    assert json.loads((workdir / "paper_bundle.json").read_text(encoding="utf-8"))["output_language"] == "en"
    raw_text = " ".join(
        json.loads(line)["text"]
        for line in (workdir / "paper_raw_sections.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert source_abstract in " ".join(raw_text.split())

    note_path = workdir / "paper.md"
    plan_path = workdir / "paper.plan.json"
    lint_path = workdir / "paper_lint.json"
    note_path.write_text(english_note(), encoding="utf-8")
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(scripts / "lint_note.py"), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(lint_path)],
        check=True,
    )
    lint = json.loads(lint_path.read_text(encoding="utf-8"))
    assert all(value is True for key, value in lint.items() if key.startswith("passes_"))

    save_root = tmp_path / "save"
    save_root.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "saved"
    saved = subprocess.run(
        [sys.executable, str(scripts / "write_obsidian_note.py"), "--language", "en", "--title", "English Local PDF", "--content-file", str(note_path), "--lint-json", str(lint_path), "--figure-decisions", str(workdir / "paper_figure_table_decisions.json")],
        cwd=save_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(saved.stdout)
    saved_note = Path(payload["note_path"])
    images_dir = Path(payload["images_dir"])
    assert payload["output_language"] == "en"
    assert saved_note.read_text(encoding="utf-8") == english_note()
    assert source_abstract in saved_note.read_text(encoding="utf-8")
    assert images_dir == saved_note.parent / "images"
    assert images_dir.is_dir()
