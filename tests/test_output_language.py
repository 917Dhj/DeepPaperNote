from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from formal_save_helpers import final_review_args
from build_synthesis_bundle import compact_writing_contract
from lint_grounding import validate_note_plan
from localization import (
    normalize_output_language,
    note_schema,
    require_artifact_output_language,
)
from contracts import note_required_sections
from plan_figures import build_figure_items

ENGLISH_SECTIONS = (
    "Core Information",
    "Abstract",
    "Contributions",
    "One-Sentence Summary",
    "Background and Problem",
    "Limitations of Prior Work",
    "Key Idea and Challenges",
    "Method",
    "Experimental Evidence",
    "Deep Analysis",
    "Limitations",
    "Takeaways",
    "Connections",
    "My Notes",
)


def english_note() -> str:
    return """---
tags:
  - papers/methods
aliases:
  - "Auditable Tool Use"
date: 2024
doi: 10.1234/example
paper_type: method
methods: [auditable tool-state tracking]
datasets: []
tasks: [multi-hop question answering]
read_date: 2026-11-06
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

## Background and Problem

How can a multi-step question-answering system remain traceable when retrieval is incomplete, external tools fail, or intermediate results are misused?

## Limitations of Prior Work

Answer-only systems cannot tell missing evidence apart from reasoning errors, and failed tool calls leave no inspectable record.

## Key Idea and Challenges

The key idea is to record every tool call in an auditable state machine; the challenge is that failure confidence must be consumed explicitly by later steps.

## Method

### Method Workflow

Evidence selection → Tool planning → Answer decoding

| Step | Input | What happens | Output | New in this paper |
| --- | --- | --- | --- | --- |
| Evidence selection | Question and candidate evidence | Extract relevant evidence | Grounded initial state | No |
| Tool planning | Current state and tool registry | Align the request with a tool, update or roll back | Auditable execution record | Yes |
| Answer decoding | Final state | Decode an answer or refusal | Response with provenance | Yes |

> [!figure] Figure 1 System overview
> Suggested location: Method
> Why it matters: The figure shows how evidence and tool states move through the execution chain.
> Current status: Placeholder retained; the extracted crop is incomplete and cannot be interpreted independently.

## Experimental Evidence

Across three datasets, answer accuracy increased from 71.2% to 78.5%, while untraceable errors fell from 18% to 9%.

## Deep Analysis

The important contribution is not only the score increase. Failed calls become inspectable evidence rather than hidden intermediate state, which supports auditing and targeted recovery.

## Limitations

The evaluation covers English question-answering data and a narrow tool set, so it does not establish robustness for multimodal tools or high-latency services.

## Takeaways

### Transferable Ideas

- The state-record design is reusable in evidence-first paper workflows: it separates missing source material from model interpretation failure, provided each step reports a checkable outcome.

### Next Steps

- I suspect the state machine degrades with high-latency services; rerunning the main benchmark with injected timeouts would test this.

## Connections

### In Your Vault

No related notes in your vault yet.

### Key Prior Work

- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering (baseline)
- Yao et al. 2023. ReAct: Synergizing Reasoning and Acting in Language Models (method source)
- Schick et al. 2023. Toolformer: Language Models Can Teach Themselves to Use Tools (method source)

## My Notes

""" + note_schema("en")["my_notes_guidance"] + "\n"


def plan_payload() -> dict:
    return {
        "output_language": "en",
        "paper_type": "method",
        "paper_type_rationale": "The paper proposes and evaluates a model mechanism.",
        "positioning": "technique",
        "survey_mode": "",
        "secondary_type": "",
        "secondary_host_section": "",
        "core_answers": {
            qid: {"answer": f"Answer for {qid}.", "evidence_refs": [{"pages": [1]}]}
            for qid in ("method.problem", "method.prior_gaps", "method.key_idea",
                        "method.claim_evidence", "method.comparison", "method.boundary_cost")
        },
        "workflow": [{"name": "inference", "steps": [
            {"step": "Evidence selection", "input": "Question and candidate evidence", "operation": "Extract relevant evidence", "output": "Grounded initial state", "novel": False},
            {"step": "Tool planning", "input": "Current state and tool registry", "operation": "Align the request with a tool, update or roll back", "output": "Auditable execution record", "novel": True},
            {"step": "Answer decoding", "input": "Final state", "operation": "Decode an answer or refusal", "output": "Response with provenance", "novel": True},
        ]}],
        "storyline": "Multi-step question answering silently accumulates errors after tool failures. The authors record every tool call in an auditable state machine. Ablations show the gain comes from the state log rather than extra retries.",
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
        "reuse_takeaways": ["Track tool failure state explicitly so later steps can tell missing evidence apart."],
        "followup_questions": ["Test whether the state log survives missing and delayed tool outputs."],
        "key_prior_work": [{"work": "Smith et al. 2024. Auditable Tool Use", "role": "baseline"}, {"work": "Yao et al. 2023. ReAct", "role": "method source"}, {"work": "Schick et al. 2023. Toolformer", "role": "method source"}],
        "connections": [],
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
    assert contract["section_order"]["head"] + contract["section_order"]["tail"] == [
        *ENGLISH_SECTIONS[:4], *ENGLISH_SECTIONS[-4:]
    ]
    assert note_required_sections("en", "method") == ENGLISH_SECTIONS
    assert contract["contracts_by_paper_type"]["method"]["workflow"]["heading"] == "Method Workflow"
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
            "Background and Problem",
            "Limitations of Prior Work",
            "Key Idea and Challenges",
            "Method",
            "Experimental Evidence",
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
    assert items[0]["section"] == "workflow subsection"
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
        ("### Method Workflow", "### method workflow"),
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
    note = english_note().replace("## Method", "## TEMP").replace("## Experimental Evidence", "## Method").replace("## TEMP", "## Experimental Evidence")
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
    note_path.write_bytes(english_note().encode("utf-8"))
    plan = plan_payload()
    plan["section_plan"] = [
        {
            "section": section,
            "focus": f"Explain how recorded tool states bound the auditable workflow's {section}.",
            "evidence_sources": [{"pages": [1]}],
        }
        for section in (
            "Background and Problem", "Limitations of Prior Work", "Key Idea and Challenges",
            "Method", "Experimental Evidence", "Deep Analysis", "Limitations",
        )
    ]
    plan["central_claims"][0]["supporting_evidence"] = [{"pages": [1]}]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(scripts / "lint_note.py"), "--language", "en", "--input", str(note_path), "--plan-file", str(plan_path), "--output", str(lint_path)],
        check=True,
    )
    lint = json.loads(lint_path.read_text(encoding="utf-8"))
    assert all(value is True for key, value in lint.items() if key.startswith("passes_"))

    grounding_path = workdir / "paper_grounding.json"
    subprocess.run(
        [
            sys.executable, str(scripts / "lint_grounding.py"), "--language", "en",
            "--note-plan", str(plan_path),
            "--source-manifest", str(workdir / "paper_source_manifest.json"),
            "--figure-decisions", str(workdir / "paper_figure_table_decisions.json"),
            "--bundle-json", str(workdir / "paper_bundle.json"),
            "--output", str(grounding_path),
        ],
        check=True,
    )
    grounding = json.loads(grounding_path.read_text(encoding="utf-8"))
    assert grounding["passes_grounding"] is True, grounding["issues"]
    review_args = final_review_args(
        workdir, english_note(), "en", plan_path=plan_path, content_path=note_path,
    )

    save_root = tmp_path / "save"
    save_root.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "saved"
    saved = subprocess.run(
        [
            sys.executable, str(scripts / "write_obsidian_note.py"),
            "--language", "en", "--title", "English Local PDF",
            "--lint-json", str(lint_path),
            "--figure-decisions", str(workdir / "paper_figure_table_decisions.json"),
            "--source-manifest", str(workdir / "paper_source_manifest.json"),
            "--plan-file", str(plan_path), "--grounding-lint-json", str(grounding_path),
            *review_args,
        ],
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
