from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None

from build_synthesis_bundle import bundle
from contracts import NOTE_REQUIRED_SECTIONS
from extract_evidence import build_appendix_evidence, evidence_quality, extract_equation_candidates

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_EVIDENCE_SCRIPT = PROJECT_ROOT / "scripts" / "extract_evidence.py"


def write_test_pdf(path: Path, pages: list[str]) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for PDF coverage integration tests.")
    doc = fitz.open()
    try:
        for text in pages:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


def test_extract_evidence_outputs_ablation_evidence(tmp_path: Path) -> None:
    input_payload = {
        "paper_id": "paper:test",
        "title": "Ablation Heavy Paper",
        "abstract": (
            "We propose a multimodal framework. The visual encoder extracts region features and sends them to a fusion module. "
            "Without the memory replay module, accuracy drops by 4.1 points, "
            "and training becomes unstable during the final stage."
        ),
    }
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(EXTRACT_EVIDENCE_SCRIPT), "--input", str(input_path), "--output", str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    ablation_evidence = payload["evidence_pack"]["ablation_evidence"]
    mechanism_evidence = payload["evidence_pack"]["mechanism_evidence"]
    assert len(ablation_evidence) == 1
    assert "drops by 4.1 points" in ablation_evidence[0]["evidence"]
    assert mechanism_evidence
    assert payload["summary"]["ablation_signals"]
    assert payload["summary"]["mechanism_signals"]
    assert payload["summary"]["paper_type"] == "AI_method"
    assert payload["evidence_pack"]["reference_candidates"] == []


def test_extract_evidence_outputs_pdf_coverage_for_truncated_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pages = [
        (
            "Abstract\nWe propose a coverage-aware extraction test.\n"
            "Introduction\nThis paper studies evidence coverage."
        ),
        "Method\nThe method scans bounded PDF pages and records transparent coverage.",
        "Experiment\nThe experiment reports a useful result.",
    ]
    pages.extend(f"Main content page {index}" for index in range(4, 10))
    pages.append("References\n[1] Ignored reference.")
    pages.extend(f"Reference tail page {index}" for index in range(11, 20))
    pages.append("Appendix\nAdditional experiments live here.")
    pages.extend(f"Appendix tail page {index}" for index in range(21, 26))
    write_test_pdf(pdf_path, pages)

    input_payload = {
        "paper_id": "paper:coverage",
        "title": "Coverage Transparent Paper",
        "abstract": "We propose a coverage-aware extraction test.",
        "pdf_path": str(pdf_path),
    }
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT_EVIDENCE_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--max-pages",
            "18",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    coverage = payload["evidence_pack"]["pdf_coverage"]
    assert coverage["total_pages"] == 25
    assert coverage["text_max_pages"] == 18
    assert coverage["text_pages_scanned"] == 18
    assert coverage["truncated_due_to_page_limit"] is True
    assert coverage["references_start_page"] == 10
    assert coverage["appendix_detected"] is True
    assert coverage["appendix_start_page"] == 20
    assert payload["evidence_pack"]["reference_candidates"][:1] == [
        {
            "raw_text": "[1] Ignored reference.",
            "display_text": "Ignored reference.",
            "page_hint": "p. 10",
            "doi": "",
            "arxiv_id": "",
            "wikilink": "",
            "vault_target": "",
            "match_status": "no_vault_match",
            "match_reason": "none",
        }
    ]
    assert coverage["section_stop_reason"] == "references"
    assert coverage["section_stop_page"] == 10
    assert payload["summary"]["pdf_coverage"] == coverage


def test_extract_evidence_default_scans_short_pdf_without_truncation(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pages = [
        "Abstract\nWe propose a coverage-aware extraction test.",
        "Introduction\nThis paper studies evidence coverage.",
        "Method\nThe method scans bounded PDF pages and records transparent coverage.",
        "Experiment\nThe experiment reports a useful result.",
    ]
    pages.extend(f"Main content page {index}" for index in range(5, 26))
    write_test_pdf(pdf_path, pages)

    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(
        json.dumps(
            {
                "paper_id": "paper:default-coverage",
                "title": "Default Coverage Paper",
                "abstract": "We propose a coverage-aware extraction test.",
                "pdf_path": str(pdf_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_EVIDENCE_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )

    coverage = json.loads(output_path.read_text(encoding="utf-8"))["evidence_pack"]["pdf_coverage"]

    assert coverage["total_pages"] == 25
    assert coverage["text_max_pages"] == 32
    assert coverage["text_pages_scanned"] == 25
    assert coverage["truncated_due_to_page_limit"] is False


def test_extract_evidence_default_truncates_after_32_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pages = [
        "Abstract\nWe propose a coverage-aware extraction test.",
        "Introduction\nThis paper studies evidence coverage.",
        "Method\nThe method scans bounded PDF pages and records transparent coverage.",
        "Experiment\nThe experiment reports a useful result.",
    ]
    pages.extend(f"Main content page {index}" for index in range(5, 34))
    write_test_pdf(pdf_path, pages)

    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(
        json.dumps(
            {
                "paper_id": "paper:default-truncated",
                "title": "Default Truncated Paper",
                "abstract": "We propose a coverage-aware extraction test.",
                "pdf_path": str(pdf_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_EVIDENCE_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )

    coverage = json.loads(output_path.read_text(encoding="utf-8"))["evidence_pack"]["pdf_coverage"]

    assert coverage["total_pages"] == 33
    assert coverage["text_max_pages"] == 32
    assert coverage["text_pages_scanned"] == 32
    assert coverage["truncated_due_to_page_limit"] is True


def test_extract_evidence_outputs_appendix_index_and_selective_evidence(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pages = [
        "Abstract\nWe propose appendix-aware extraction.\nIntroduction\nThe paper studies coverage.",
        "Method\nThe main method uses a compact extraction pipeline.",
        "Experiment\nThe main experiment reports stable results.",
    ]
    pages.extend(f"Main content page {index}" for index in range(4, 20))
    pages.append(
        "\n".join(
            [
                "Appendix",
                "A. Additional Experiments",
                "Without replay, F1 drops by 4.1 points and training becomes unstable.",
                "Additional results improve accuracy to 91.2 on the hidden split.",
                "Table A1. Extra ablation results",
                "B. Hyperparameters",
                "We use learning rate 1e-4, batch size 32, and AdamW optimizer.",
                "The dataset split uses 80/10/10 train, validation, and test partitions.",
                "Figure A1: Qualitative examples",
                "Case study examples show failure cases in long conversations.",
            ]
        )
    )
    pages.extend(f"Appendix tail page {index}" for index in range(21, 26))
    write_test_pdf(pdf_path, pages)

    input_payload = {
        "paper_id": "paper:appendix",
        "title": "Appendix Aware Paper",
        "abstract": "We propose appendix-aware extraction.",
        "pdf_path": str(pdf_path),
    }
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(json.dumps(input_payload, ensure_ascii=False), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_EVIDENCE_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--max-pages",
            "18",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    pack = payload["evidence_pack"]
    assert pack["ablation_evidence"] == []
    assert pack["appendix_index"]["sections"][:2] == [
        {"title": "A. Additional Experiments", "page": 20},
        {"title": "B. Hyperparameters", "page": 20},
    ]
    assert pack["appendix_index"]["table_captions"][:1] == [
        {"id": "Table A1", "caption": "Extra ablation results", "page_hint": "p.20"}
    ]
    appendix_evidence = pack["appendix_evidence"]
    assert "drops by 4.1 points" in appendix_evidence["ablation"][0]["evidence"]
    assert "learning rate 1e-4" in appendix_evidence["implementation_details"][0]["evidence"]
    assert "dataset split" in appendix_evidence["dataset_details"][0]["evidence"]
    assert "accuracy to 91.2" in appendix_evidence["extra_results"][0]["evidence"]
    assert "Case study examples" in appendix_evidence["qualitative_examples"][0]["evidence"]
    assert payload["summary"]["appendix_evidence_counts"]["ablation"] == 1


def test_appendix_evidence_default_keeps_eight_items_per_category() -> None:
    appendix_pages = [
        {
            "page": 20,
            "text": " ".join(
                f"Ablation setting {index} drops by {index} points."
                for index in range(10)
            ),
        }
    ]

    evidence = build_appendix_evidence(
        appendix_pages,
        {"sections": [{"title": "A. Additional Experiments", "page": 20}]},
    )

    assert len(evidence["ablation"]) == 8
    assert evidence["ablation"][0]["source_section"] == "A. Additional Experiments"


def test_evidence_quality_caps_abstract_fallback_chunks_at_low() -> None:
    pack = {
        "candidate_chunks": {
            "introduction": [
                {
                    "text": "Abstract fallback.",
                    "actual_source_section": "abstract",
                    "is_abstract_fallback": True,
                }
            ],
            "method": [
                {
                    "text": "Abstract fallback.",
                    "actual_source_section": "abstract",
                    "is_abstract_fallback": True,
                }
            ],
            "experiment": [
                {
                    "text": "Abstract fallback.",
                    "actual_source_section": "abstract",
                    "is_abstract_fallback": True,
                }
            ],
        },
        "equation_candidates": [{"equation": r"L_i = -\log p_i"}],
        "figure_captions": [{"id": "Figure 1", "caption": "Overview"}],
        "table_captions": [{"id": "Table 1", "caption": "Results"}],
        "section_extraction_coverage": {
            "core_sections_found": [],
            "fallback_sections": ["introduction", "method", "experiment", "conclusion"],
            "coverage_status": "poor",
        },
    }

    assert evidence_quality(pack) == "low"


def test_evidence_quality_allows_real_core_sections_to_reach_high() -> None:
    pack = {
        "candidate_chunks": {
            "introduction": [{"text": "Problem context.", "actual_source_section": "introduction"}],
            "method": [{"text": "Method details.", "actual_source_section": "method"}],
            "experiment": [{"text": "Result details.", "actual_source_section": "experiment"}],
        },
        "equation_candidates": [{"equation": r"L_i = -\log p_i"}],
        "figure_captions": [{"id": "Figure 1", "caption": "Overview"}],
        "table_captions": [{"id": "Table 1", "caption": "Results"}],
        "section_extraction_coverage": {
            "core_sections_found": ["introduction", "method", "experiment"],
            "fallback_sections": [],
            "coverage_status": "good",
        },
    }

    assert evidence_quality(pack) == "high"


def test_extract_equation_candidates_filters_config_assignments() -> None:
    full_text = (
        "model = transformer. temperature = 0.7. lr = 1e-4. "
        "dataset = ImageNet. hidden_size = 768."
    )

    candidates = extract_equation_candidates(
        full_text=full_text,
        method_text=full_text,
        experiment_text="",
        conclusion_text="",
    )

    assert candidates == []


def test_extract_equation_candidates_requires_math_signal_for_objective_text() -> None:
    full_text = "The objective p(class) = baseline label. Loss = reported value."

    candidates = extract_equation_candidates(
        full_text=full_text,
        method_text=full_text,
        experiment_text=full_text,
        conclusion_text="",
    )

    assert candidates == []


def test_extract_equation_candidates_keeps_complexity_and_tex_math() -> None:
    full_text = (
        r"The method runs in O(n log n). "
        r"We model p(y_i|x_i) = \frac{\exp s_i}{\sum_j \exp s_j}. "
        r"The objective is L_i = -\log p_i. "
        r"The policy is R_t^{(c)} >= R_t^{(w)}."
    )

    candidates = extract_equation_candidates(
        full_text=full_text,
        method_text=full_text,
        experiment_text=full_text,
        conclusion_text="",
    )
    equations = [item["equation"] for item in candidates]

    assert "O(n log n)" in equations
    assert any(r"\frac" in equation and r"\sum" in equation for equation in equations)
    assert any(r"L_i" in equation and r"\log" in equation for equation in equations)
    assert any("R_t" in equation and ">=" in equation for equation in equations)


def test_bundle_exposes_coverage_without_removing_evidence_quality() -> None:
    synthesis = bundle(
        metadata={"title": "Coverage Paper"},
        evidence_wrapper={
            "evidence_pack": {
                "evidence_quality": "low",
                "language_hint": "zh",
                "section_extraction_coverage": {
                    "coverage_status": "poor",
                    "core_sections_found": [],
                    "missing_core_sections": ["introduction", "method", "experiment"],
                    "fallback_sections": ["introduction", "method", "experiment", "conclusion"],
                },
                "pdf_coverage": {
                    "total_pages": 25,
                    "text_max_pages": 32,
                    "text_pages_scanned": 25,
                    "truncated_due_to_page_limit": False,
                    "appendix_detected": True,
                    "appendix_start_page": 20,
                    "references_start_page": 10,
                    "section_stop_reason": "references",
                    "section_stop_page": 10,
                },
                "section_texts": {
                    "method": "方法" * 6500,
                    "experiment": "实验结果",
                },
                "appendix_index": {
                    "appendix_detected": True,
                    "start_page": 20,
                    "sections": [{"title": "A. Additional Experiments", "page": 20}],
                    "figure_captions": [],
                    "table_captions": [
                        {"id": "Table A1", "caption": "Extra ablation results", "page_hint": "p.20"}
                    ],
                },
                "appendix_evidence": {
                    "ablation": [
                        {
                            "evidence": "Without replay, F1 drops by 4.1 points.",
                            "source_section": "A. Additional Experiments",
                            "page_hint": "p.20",
                            "kind_hint": "ablation",
                        }
                    ],
                    "implementation_details": [],
                    "dataset_details": [],
                    "extra_results": [],
                    "qualitative_examples": [],
                },
                "extraction_failures": ["section_coverage_poor"],
            }
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    assert synthesis["evidence_quality"] == "low"
    assert synthesis["coverage"] == {
        "language_hint": "zh",
        "section_extraction_coverage": {
            "coverage_status": "poor",
            "core_sections_found": [],
            "missing_core_sections": ["introduction", "method", "experiment"],
            "fallback_sections": ["introduction", "method", "experiment", "conclusion"],
        },
        "pdf_coverage": {
            "total_pages": 25,
            "text_max_pages": 32,
            "text_pages_scanned": 25,
            "truncated_due_to_page_limit": False,
            "appendix_detected": True,
            "appendix_start_page": 20,
            "references_start_page": 10,
            "section_stop_reason": "references",
            "section_stop_page": 10,
        },
        "bundle_text_budget": {
            "section_text_default_max_chars": 4000,
            "section_text_limit_sections": 8,
            "section_text_limits": {
                "method": 12000,
                "experiment": 12000,
            },
            "section_text_original_chars": {
                "method": 13000,
                "experiment": 4,
            },
            "section_text_included_chars": {
                "method": 12000,
                "experiment": 4,
            },
            "section_text_truncated_sections": ["method"],
        },
        "appendix_evidence_counts": {
            "ablation": 1,
            "implementation_details": 0,
            "dataset_details": 0,
            "extra_results": 0,
            "qualitative_examples": 0,
        },
        "extraction_failures": ["section_coverage_poor"],
        "asset_coverage": {},
        "figure_quality_summary": {
            "usable": 0,
            "review": 0,
            "reject": 0,
            "unknown": 0,
        },
        "truncation_warnings": ["section_text_truncated"],
        "identity_confidence": "",
        "identity_confidence_reasons": [],
    }
    assert synthesis["appendix"] == {
        "index": {
            "appendix_detected": True,
            "start_page": 20,
            "sections": [{"title": "A. Additional Experiments", "page": 20}],
            "figure_captions": [],
            "table_captions": [
                {"id": "Table A1", "caption": "Extra ablation results", "page_hint": "p.20"}
            ],
        },
        "evidence": {
            "ablation": [
                {
                    "evidence": "Without replay, F1 drops by 4.1 points.",
                    "source_section": "A. Additional Experiments",
                    "page_hint": "p.20",
                    "kind_hint": "ablation",
                }
            ],
            "implementation_details": [],
            "dataset_details": [],
            "extra_results": [],
            "qualitative_examples": [],
        },
    }
    review_rules = synthesis["writing_contract"]["self_review_rules"]
    assert any("bundle.coverage" in rule for rule in review_rules)
    assert any("max_pages" in rule for rule in review_rules)
    assert any("bundle_text_budget" in rule for rule in review_rules)
    assert any("appendix evidence" in rule for rule in review_rules)


def test_bundle_coverage_exposes_asset_quality_truncation_and_identity() -> None:
    synthesis = bundle(
        metadata={
            "title": "Coverage Paper",
            "identity_confidence": "high",
            "identity_confidence_reasons": ["doi_present"],
        },
        evidence_wrapper={
            "evidence_pack": {
                "pdf_coverage": {"truncated_due_to_page_limit": False},
                "section_texts": {"method": "short"},
            }
        },
        figures_wrapper={},
        assets_wrapper={
            "asset_coverage": {
                "total_pages": 45,
                "asset_max_pages": 40,
                "asset_pages_scanned": 40,
                "truncated_due_to_asset_page_limit": True,
            },
            "figure_assets": [
                {"quality_signals": {"visual_quality_status": "usable"}},
                {"quality_signals": {"visual_quality_status": "needs_review"}},
                {"quality_signals": {"visual_quality_status": "mystery"}},
                {},
            ],
        },
    )

    assert synthesis["metadata"]["identity_confidence"] == "high"
    assert synthesis["metadata"]["identity_confidence_reasons"] == ["doi_present"]
    assert synthesis["coverage"]["asset_coverage"] == {
        "total_pages": 45,
        "asset_max_pages": 40,
        "asset_pages_scanned": 40,
        "truncated_due_to_asset_page_limit": True,
    }
    assert synthesis["coverage"]["figure_quality_summary"] == {
        "usable": 1,
        "review": 1,
        "reject": 0,
        "unknown": 2,
    }
    assert synthesis["coverage"]["truncation_warnings"] == ["asset_page_limit"]
    assert synthesis["coverage"]["identity_confidence"] == "high"
    assert synthesis["coverage"]["identity_confidence_reasons"] == ["doi_present"]


def test_bundle_uses_section_aware_text_budget() -> None:
    synthesis = bundle(
        metadata={"title": "Long Paper"},
        evidence_wrapper={
            "evidence_pack": {
                "section_texts": {
                    "method": "m" * 10000,
                    "introduction": "i" * 7000,
                    "data": "d" * 9000,
                    "general": "g" * 5000,
                }
            }
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    section_texts = synthesis["section_texts"]
    assert len(section_texts["method"]) == 10000
    assert len(section_texts["introduction"]) == 6000
    assert len(section_texts["data"]) == 8000
    assert len(section_texts["general"]) == 4000
    assert synthesis["coverage"]["bundle_text_budget"]["section_text_limits"] == {
        "method": 12000,
        "introduction": 6000,
        "data": 8000,
        "general": 4000,
    }
    assert synthesis["coverage"]["bundle_text_budget"]["section_text_truncated_sections"] == [
        "introduction",
        "data",
        "general",
    ]


def test_bundle_appendix_summary_keeps_eight_items_per_category() -> None:
    synthesis = bundle(
        metadata={"title": "Appendix Paper"},
        evidence_wrapper={
            "evidence_pack": {
                "appendix_evidence": {
                    "ablation": [
                        {
                            "evidence": f"Ablation setting {index} drops by {index} points.",
                            "source_section": "A. Additional Experiments",
                            "page_hint": "p.20",
                            "kind_hint": "ablation",
                        }
                        for index in range(10)
                    ]
                }
            }
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    assert len(synthesis["appendix"]["evidence"]["ablation"]) == 8


def test_bundle_exposes_ablation_evidence_and_new_contract_rules() -> None:
    synthesis = bundle(
        metadata={"title": "Mechanism Paper"},
        evidence_wrapper={
            "summary": {"paper_type": "AI_method"},
            "evidence_pack": {
                "mechanism_evidence": [
                    {
                        "evidence": "The encoder extracts audio tokens and sends them into the fusion module.",
                        "source_section": "method",
                        "page_hint": "p.4",
                    }
                ],
                "ablation_evidence": [
                    {
                        "evidence": "Removing the decoder causes a 2-point drop and unstable optimization.",
                        "source_section": "experiment",
                        "page_hint": "p.8",
                    }
                ]
            },
            "summary": {"ablation_signals": ["Removing the decoder causes a 2-point drop."]},
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    assert synthesis["evidence"]["mechanism"][0]["source_section"] == "method"
    assert synthesis["evidence"]["ablation"][0]["source_section"] == "experiment"
    planning_rules = synthesis["writing_contract"]["planning_rules"]
    self_review_rules = synthesis["writing_contract"]["self_review_rules"]
    method_contract = synthesis["writing_contract"]["paper_type_contracts"]["AI_method"]
    formula_rules = method_contract["formula_rules"]
    mechanism_flow_contract = method_contract["mechanism_flow_contract"]

    assert any("note_plan.paper_type" in rule for rule in planning_rules)
    assert any("section_semantics" in rule and "note_plan.section_plan" in rule for rule in planning_rules)
    assert any("recommended_subsections" in rule and "note_plan.section_plan" in rule for rule in planning_rules)
    assert any("工程解释" in rule for rule in formula_rules)
    assert any("ablation_evidence" in rule for rule in self_review_rules)
    assert method_contract["section_semantics"]["方法主线"] == "模型、算法、训练或推理机制。"
    assert method_contract["recommended_subsections"]["方法主线"] == [
        "机制流程",
        "模型结构",
        "训练目标",
        "推理与采样链路",
        "关键实现细节",
    ]
    assert mechanism_flow_contract["title"] == "机制流程"


@pytest.mark.parametrize(
    ("paper_type", "expected_token"),
    [
        ("AI_method", "方法机制"),
        ("benchmark_or_dataset", "benchmark"),
        ("clinical_or_psychology_empirical", "临床"),
        ("humanities_or_social_science", "理论"),
        ("survey_or_review", "综述"),
    ],
)
def test_bundle_exposes_all_paper_type_contracts_for_model_selection(paper_type: str, expected_token: str) -> None:
    synthesis = bundle(
        metadata={"title": "Typed Paper"},
        evidence_wrapper={"summary": {"paper_type": "AI_method"}, "evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={},
    )

    contract = synthesis["writing_contract"]
    typed_contract = contract["paper_type_contracts"][paper_type]
    typed_text = json.dumps(typed_contract, ensure_ascii=False)

    assert typed_contract["paper_type"] == paper_type
    assert {
        "paper_type",
        "reader_lens",
        "section_focus",
        "required_checks",
        "avoid_rules",
        "section_semantics",
        "recommended_subsections",
    } <= set(typed_contract)
    assert typed_contract["section_focus"]
    assert typed_contract["required_checks"]
    assert typed_contract["avoid_rules"]
    assert typed_contract["section_semantics"]
    assert typed_contract["recommended_subsections"]
    assert set(typed_contract["recommended_subsections"]) <= set(NOTE_REQUIRED_SECTIONS)
    assert expected_token in typed_text
    assert "active_paper_type_contract" not in contract
    assert contract["paper_type_selection"] == {
        "source_of_truth": "note_plan.paper_type",
        "suggested_paper_type": "AI_method",
        "suggested_paper_type_role": "hint_only",
        "allowed_paper_types": list(contract["paper_type_contracts"]),
    }
    assert "note_plan.paper_type" in "\n".join(contract["planning_rules"])
    assert "paper_type_contracts[note_plan.paper_type]" in "\n".join(contract["planning_rules"])
    assert "section_semantics" in "\n".join(contract["planning_rules"])
    assert "recommended_subsections" in "\n".join(contract["planning_rules"])
    assert "note_plan.section_plan" in "\n".join(contract["planning_rules"])
    assert "paper_type_contracts[note_plan.paper_type]" in "\n".join(contract["self_review_rules"])

    if paper_type != "AI_method":
        assert "### 机制流程" not in "\n".join(contract["planning_rules"])
        assert "开发者看懂方法主线" not in "\n".join(contract["self_review_rules"])


def test_bundle_exposes_sanitized_figure_asset_quality_and_hard_gate_rules() -> None:
    synthesis = bundle(
        metadata={"title": "Figure Paper"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={},
        assets_wrapper={
            "figure_assets": [
                {
                    "page_number": 1,
                    "label": "Figure 1",
                    "kind": "figure",
                    "caption_text": "Figure 1. Overview.",
                    "filename": "page_001_fig_figure_1.png",
                    "path": "/tmp/images/page_001_fig_figure_1.png",
                    "width": 640,
                    "height": 320,
                    "size_bytes": 1234,
                    "extraction_level": "figure",
                    "bbox_pt": [0, 0, 500, 400],
                    "quality_signals": {
                        "visual_quality_status": "reject",
                        "quality_reason_codes": ["large_text_block_suspected"],
                    },
                    "raw_unwanted": "do not expose",
                }
            ]
        },
    )

    figure_assets = synthesis["pdf_assets"]["figure_assets"]
    assert figure_assets == [
        {
            "filename": "page_001_fig_figure_1.png",
            "path": "/tmp/images/page_001_fig_figure_1.png",
            "page_number": 1,
            "label": "Figure 1",
            "kind": "figure",
            "caption_text": "Figure 1. Overview.",
            "width": 640,
            "height": 320,
            "size_bytes": 1234,
            "extraction_level": "figure",
            "quality_signals": {
                "visual_quality_status": "reject",
                "quality_reason_codes": ["large_text_block_suspected"],
            },
        }
    ]

    figure_rules_text = "\n".join(synthesis["writing_contract"]["figure_rules"])
    assert "label/caption match is not insertion approval" in figure_rules_text
    assert "caption-only" in figure_rules_text
    assert "missing table body" in figure_rules_text
    assert "low visual body ratio" in figure_rules_text
    assert "directly under the most relevant analytical section" in figure_rules_text
    assert "reject_visual_quality" in figure_rules_text
    assert "catch-all sections" in figure_rules_text
    assert "[!figure]" in figure_rules_text
    assert "[图表占位 |" in figure_rules_text
