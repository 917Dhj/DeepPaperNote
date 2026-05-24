from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import common
from common import (
    clean_local_pdf_stem,
    domain_name_score,
    extract_appendix_index,
    extract_local_pdf_hints,
    extract_caption_lines,
    extract_pdf_sections,
    env_config_value,
    existing_domain_dirs,
    extract_arxiv_id,
    extract_doi,
    extract_mechanism_flow_sentences,
    extract_negative_claims,
    infer_domain_label,
    infer_paper_type,
    infer_source_type,
    fetch_arxiv_entries,
    enrich_metadata,
    match_section_heading,
    normalize_caption_label,
    normalize_pdf_text_artifacts,
    pdf_coverage_summary,
    resolve_reference,
    resolve_domain_subdir,
    resolve_note_output_mode,
    resolve_obsidian_note_path,
    semantic_scholar_headers,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_SCRIPT = PROJECT_ROOT / "scripts" / "check_environment.py"


class FakePdfPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self.text


class FakePdfDoc:
    def __init__(self, metadata: dict[str, str], pages: list[str]) -> None:
        self.metadata = metadata
        self._pages = [FakePdfPage(text) for text in pages]

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, index: int) -> FakePdfPage:
        return self._pages[index]

    def close(self) -> None:
        return None


class FakeFitz:
    def __init__(self, doc: FakePdfDoc) -> None:
        self.doc = doc

    def open(self, path: Path) -> FakePdfDoc:
        return self.doc


def test_extract_doi_from_url_like_text() -> None:
    text = "Published version: https://doi.org/10.1038/s44184-025-00175-1."
    assert extract_doi(text) == "10.1038/s44184-025-00175-1"


def test_extract_arxiv_id_strips_version() -> None:
    text = "https://arxiv.org/abs/2508.09736v4"
    assert extract_arxiv_id(text) == "2508.09736"


def test_extract_arxiv_id_does_not_match_plain_doi_suffix() -> None:
    text = "doi: 10.3389/fpubh.2019.00399"
    assert extract_arxiv_id(text) is None


def test_extract_arxiv_id_supports_arxiv_doi_marker() -> None:
    text = "doi: 10.48550/arXiv.2302.13971"
    assert extract_arxiv_id(text) == "2302.13971"


def test_infer_source_type_prefers_doi_over_arxiv_like_suffix() -> None:
    assert infer_source_type("10.3389/fpubh.2019.00399") == "doi"


def test_infer_source_type_for_local_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    assert infer_source_type(str(pdf_path)) == "local_pdf"


def test_clean_local_pdf_stem_removes_zotero_style_noise() -> None:
    stem = "Xu 等 - 2025 - Identifying psychiatric manifestations in outpatients with depression and anxiety a large language-182952"
    assert clean_local_pdf_stem(stem) == "Identifying psychiatric manifestations in outpatients with depression and anxiety a large language"


def test_normalize_pdf_text_artifacts_expands_ligatures() -> None:
    assert normalize_pdf_text_artifacts("Efﬁcient ﬂow oﬀers aﬃne aﬄuent") == "Efficient flow offers affine affluent"


def test_match_section_heading_supports_chinese_and_nonstandard_english_headings() -> None:
    assert match_section_heading("一、摘要") == "abstract"
    assert match_section_heading("2 材料与方法") == "method"
    assert match_section_heading("3. 实验结果") == "experiment"
    assert match_section_heading("4 结论") == "conclusion"
    assert match_section_heading("参考文献") == "stop"
    assert match_section_heading("Findings") == "experiment"
    assert match_section_heading("Materials and Methods") == "method"
    assert match_section_heading("Study Design") == "method"
    assert match_section_heading("Data") == "data"


def test_extract_caption_lines_supports_chinese_figure_and_table_labels() -> None:
    text = "\n".join(
        [
            "图 1：总体框架。",
            "图2 | 消融实验流程",
            "表 1 实验结果",
            "Table 2. English baseline",
        ]
    )

    figure_captions = extract_caption_lines(text, "figure")
    table_captions = extract_caption_lines(text, "table")

    assert figure_captions[:2] == [
        {"id": "图 1", "caption": "总体框架。"},
        {"id": "图 2", "caption": "消融实验流程"},
    ]
    assert table_captions[:2] == [
        {"id": "表 1", "caption": "实验结果"},
        {"id": "Table 2", "caption": "English baseline"},
    ]


def test_extract_caption_lines_supports_conservative_appendix_labels() -> None:
    text = "\n".join(
        [
            "Fig. S1. Supplemental ablation.",
            "Figure A2: Appendix pipeline.",
            "Table S3 Extended results.",
        ]
    )

    assert extract_caption_lines(text, "figure") == [
        {"id": "Fig S1", "caption": "Supplemental ablation."},
        {"id": "Figure A2", "caption": "Appendix pipeline."},
    ]
    assert extract_caption_lines(text, "table") == [
        {"id": "Table S3", "caption": "Extended results."},
    ]


def test_extract_caption_lines_supports_extended_scheme_algorithm_labels() -> None:
    text = "\n".join(
        [
            "Extended Data Fig. 1. Extra examples.",
            "Extended Data Figure 2: Extra overview.",
            "Extended Data Table 1. Extra results.",
            "Scheme 2. Synthetic route.",
            "Algorithm 1 Training loop.",
        ]
    )

    assert extract_caption_lines(text, "figure") == [
        {"id": "Extended Data Fig 1", "caption": "Extra examples."},
        {"id": "Extended Data Fig 2", "caption": "Extra overview."},
        {"id": "Scheme 2", "caption": "Synthetic route."},
        {"id": "Algorithm 1", "caption": "Training loop."},
    ]
    assert extract_caption_lines(text, "table") == [
        {"id": "Extended Data Table 1", "caption": "Extra results."},
    ]


def test_normalize_caption_label_supports_extended_scheme_algorithm_labels() -> None:
    assert normalize_caption_label("Extended Data Fig. 1") == "Extended Data Fig 1"
    assert normalize_caption_label("Extended Data Figure 1") == "Extended Data Fig 1"
    assert normalize_caption_label("Extended Data Table 1") == "Extended Data Table 1"
    assert normalize_caption_label("Scheme 2") == "Scheme 2"
    assert normalize_caption_label("Algorithm 1") == "Algorithm 1"


def test_extract_caption_lines_rejects_caption_like_prose() -> None:
    text = "\n".join(
        [
            "Figure out whether the method generalizes before drawing conclusions.",
            "Table stakes for a good benchmark include held-out evaluation.",
            "Figuratively speaking, the result is not a Figure caption.",
            "Figure 2.1. Hierarchical result.",
            "Figure 3(a). Subpanel detail.",
        ]
    )

    assert extract_caption_lines(text, "figure") == []
    assert extract_caption_lines(text, "table") == []


def test_extract_pdf_sections_supports_chinese_headings(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        metadata={},
        pages=[
            "\n".join(
                [
                    "摘要",
                    "本文提出一个证据优先的阅读流程。",
                    "1 引言",
                    "现有方法容易过度总结。",
                    "2 材料与方法",
                    "我们构建了一个分阶段处理管线。",
                    "3 实验结果",
                    "该方法在三个数据集上提升明显。",
                    "参考文献",
                    "[1] Ignored reference.",
                ]
            )
        ],
    )
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    sections = extract_pdf_sections(pdf_path)

    assert sections["abstract"] == "本文提出一个证据优先的阅读流程。"
    assert sections["introduction"] == "现有方法容易过度总结。"
    assert sections["method"] == "我们构建了一个分阶段处理管线。"
    assert sections["experiment"] == "该方法在三个数据集上提升明显。"
    assert "conclusion" not in sections


def test_pdf_coverage_reports_page_limit_and_late_appendix(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    pages = [f"Page {index}" for index in range(1, 26)]
    pages[9] = "References\n[1] Ignored reference."
    pages[19] = "Appendix\nAdditional experiments."
    fake_doc = FakePdfDoc(metadata={}, pages=pages)
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    coverage = pdf_coverage_summary(pdf_path, max_pages=18)

    assert coverage["total_pages"] == 25
    assert coverage["text_max_pages"] == 18
    assert coverage["text_pages_scanned"] == 18
    assert coverage["truncated_due_to_page_limit"] is True
    assert coverage["references_start_page"] == 10
    assert coverage["appendix_detected"] is True
    assert coverage["appendix_start_page"] == 20
    assert coverage["section_stop_reason"] == "references"
    assert coverage["section_stop_page"] == 10


def test_extract_appendix_index_reports_sections_and_captions(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    pages = [f"Page {index}" for index in range(1, 20)]
    pages.append(
        "\n".join(
            [
                "Appendix",
                "A. Additional Experiments",
                "Table A1. Extra ablation results",
                "B. Hyperparameters",
                "Figure A1: Qualitative examples",
            ]
        )
    )
    pages.extend(f"Appendix tail page {index}" for index in range(21, 26))
    fake_doc = FakePdfDoc(metadata={}, pages=pages)
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    coverage = pdf_coverage_summary(pdf_path, max_pages=18)
    index = extract_appendix_index(pdf_path, coverage)

    assert index["appendix_detected"] is True
    assert index["start_page"] == 20
    assert index["sections"][:2] == [
        {"title": "A. Additional Experiments", "page": 20},
        {"title": "B. Hyperparameters", "page": 20},
    ]
    assert index["table_captions"][:1] == [
        {"id": "Table A1", "caption": "Extra ablation results", "page_hint": "p.20"}
    ]
    assert index["figure_captions"][:1] == [
        {"id": "Figure A1", "caption": "Qualitative examples", "page_hint": "p.20"}
    ]


def test_extract_local_pdf_hints_prefers_pdf_metadata_title_and_doi(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        metadata={
            "title": "Identifying psychiatric manifestations in outpatients with depression and anxiety: a large language model-based approach",
            "subject": "npj Mental Health Research, doi:10.1038/s44184-025-00175-1",
        },
        pages=["Ignored fallback title"],
    )
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    hints = extract_local_pdf_hints(pdf_path)

    assert hints["title"] == "Identifying psychiatric manifestations in outpatients with depression and anxiety: a large language model-based approach"
    assert hints["doi"] == "10.1038/s44184-025-00175-1"


def test_extract_local_pdf_hints_falls_back_to_first_page_title(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        metadata={},
        pages=[
            "\n".join(
                [
                    "npj | mental health research Article",
                    "https://doi.org/10.1038/s44184-025-00175-1",
                    "LLaMA: Open and Efﬁcient Foundation Language Models",
                    "Hugo Touvron, Thibaut Lavril",
                ]
            )
        ],
    )
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    hints = extract_local_pdf_hints(pdf_path)

    assert hints["title"] == "LLaMA: Open and Efficient Foundation Language Models"
    assert hints["doi"] == "10.1038/s44184-025-00175-1"


def test_resolve_reference_local_pdf_uses_extracted_hints(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(
        "common.extract_local_pdf_hints",
        lambda path: {
            "title": "LLaMA: Open and Efficient Foundation Language Models",
            "doi": "10.48550/arXiv.2302.13971",
            "arxiv_id": "2302.13971",
        },
    )

    resolved = resolve_reference(str(pdf_path))

    assert resolved["source_type"] == "local_pdf"
    assert resolved["title"] == "LLaMA: Open and Efficient Foundation Language Models"
    assert resolved["doi"] == "10.48550/arXiv.2302.13971"
    assert resolved["arxiv_id"] == "2302.13971"


def test_resolve_note_output_mode_falls_back_to_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = {
        "obsidian_vault": "",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    mode, root = resolve_note_output_mode(config)
    assert mode == "workspace"
    assert root == tmp_path / "DeepPaperNote_output"


def test_resolve_obsidian_note_path_in_workspace_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = {
        "obsidian_vault": "",
        "workspace_output_dir": "DeepPaperNote_output",
        "papers_dir": "Research/Papers",
    }
    path = resolve_obsidian_note_path(config, title="My Test Paper")
    assert path == tmp_path / "DeepPaperNote_output" / "My_Test_Paper" / "My_Test_Paper.md"


def test_resolve_obsidian_note_path_in_vault_mode(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(config, title="My Test Paper", subdir="心理健康")
    assert path == vault / "Research/Papers" / "心理健康" / "My_Test_Paper" / "My_Test_Paper.md"


def test_resolve_obsidian_note_path_avoids_double_slug_when_subdir_already_contains_slug(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(
        config,
        title="My Test Paper",
        subdir="心理健康/My_Test_Paper",
    )
    assert path == vault / "Research/Papers" / "心理健康" / "My_Test_Paper" / "My_Test_Paper.md"


def test_resolve_obsidian_note_path_avoids_double_slug_when_subdir_is_papers_relative_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(
        config,
        title="My Test Paper",
        subdir="Research/Papers/心理健康/My_Test_Paper",
    )
    assert path == vault / "Research/Papers" / "心理健康" / "My_Test_Paper" / "My_Test_Paper.md"


def test_resolve_obsidian_note_path_avoids_double_folder_when_subdir_is_title_slug_but_filename_is_readable(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(
        config,
        title="SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
        subdir="Research/Papers/Benchmark/SWE_bench_Can_Language_Models_Resolve_Real_World_GitHub_Issues",
        filename="SWE-bench - Can Language Models Resolve Real-World GitHub Issues.md",
    )
    assert path == (
        vault
        / "Research/Papers"
        / "Benchmark"
        / "SWE_bench_Can_Language_Models_Resolve_Real_World_GitHub_Issues"
        / "SWE-bench - Can Language Models Resolve Real-World GitHub Issues.md"
    )


def test_existing_domain_dirs_excludes_root_level_paper_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "大模型").mkdir(parents=True)
    paper_dir = papers / "Attention_Is_All_You_Need"
    paper_dir.mkdir(parents=True)
    (paper_dir / "Attention_Is_All_You_Need.md").write_text("# note\n", encoding="utf-8")

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    assert existing_domain_dirs(config) == ["大模型"]


def test_resolve_domain_subdir_prefers_existing_domain(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "大模型").mkdir(parents=True)
    (papers / "心理健康").mkdir(parents=True)
    paper_dir = papers / "Attention_Is_All_You_Need"
    paper_dir.mkdir(parents=True)
    (paper_dir / "Attention_Is_All_You_Need.md").write_text("# note\n", encoding="utf-8")

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    resolved = resolve_domain_subdir(
        config,
        title="Seeing, Listening, Remembering, and Reasoning: A Multimodal Agent with Long-Term Memory",
        abstract="We present a multimodal large language model agent with long-term memory for reasoning over video and audio.",
    )
    assert resolved == "大模型"


def test_infer_domain_label_routes_clinical_llm_paper_to_application_domain() -> None:
    label = infer_domain_label(
        "Using a fine-tuned large language model for symptom-based depression evaluation",
        "We study clinical depression screening with patients and psychological symptom scales.",
    )
    assert label == "医疗健康"


def test_infer_domain_label_prefers_application_domain_for_legal_rag() -> None:
    label = infer_domain_label(
        "Retrieval-augmented generation for legal question answering",
        "We combine RAG with a large language model for contract and case law analysis.",
    )
    assert label == "法律"


def test_infer_domain_label_uses_method_fallback_for_moe_algorithm() -> None:
    label = infer_domain_label(
        "A new mixture-of-experts routing algorithm",
        "Sparse MoE routing improves transformer pretraining efficiency.",
    )
    assert label == "大模型"


def test_infer_domain_label_defaults_generic_ai_method_to_machine_learning() -> None:
    assert (
        infer_domain_label("A new optimization algorithm", "We improve model training.")
        == "机器学习"
    )


def test_resolve_domain_subdir_reuses_specialized_existing_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "心理健康").mkdir(parents=True)

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    resolved = resolve_domain_subdir(
        config,
        title="Large language models for depression screening",
        abstract=(
            "A clinical study with patients, symptom scales, therapy histories, "
            "and mental health outcomes."
        ),
    )
    label = infer_domain_label(
        "Large language models for depression screening",
        (
            "A clinical study with patients, symptom scales, therapy histories, "
            "and mental health outcomes."
        ),
    )
    assert label == "医疗健康"
    assert resolved == "心理健康"


def test_resolve_domain_subdir_keeps_robotics_ahead_of_method_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "大模型").mkdir(parents=True)

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    resolved = resolve_domain_subdir(
        config,
        title="Diffusion Policy for Robot Manipulation",
        abstract=(
            "We learn control policies for robotic manipulation and navigation "
            "from demonstrations."
        ),
    )
    assert resolved == "机器人"


def test_method_only_evidence_does_not_reuse_unrelated_application_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "金融").mkdir(parents=True)

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    title = "Efficient Transformer Scaling for Large Language Models"
    abstract = "We improve pre-training, instruction tuning, and reasoning for a foundation model."

    assert domain_name_score("金融", "大模型", title, abstract) == 0
    assert resolve_domain_subdir(config, title=title, abstract=abstract) == "大模型"


def test_incidental_application_keyword_does_not_reuse_unrelated_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    (papers / "金融").mkdir(parents=True)

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    title = "Large language models for depression screening"
    abstract = "A clinical patient study mentions risk factors and symptom screening."

    assert infer_domain_label(title, abstract) == "医疗健康"
    assert domain_name_score("金融", "医疗健康", title, abstract) == 0
    assert resolve_domain_subdir(config, title=title, abstract=abstract) == "医疗健康"


@pytest.mark.parametrize(
    ("title", "abstract", "expected"),
    [
        (
            "Sparse Transformers for Long Context Modeling",
            "We propose a new attention mechanism and evaluate ablations.",
            "AI_method",
        ),
        (
            "A Benchmark for Multimodal Reasoning",
            "The paper introduces a dataset, leaderboard, and evaluation suite.",
            "benchmark_or_dataset",
        ),
        (
            "Patient Anxiety Screening with Mobile Signals",
            "A clinical patient study measures depression and anxiety symptoms.",
            "clinical_or_psychology_empirical",
        ),
        (
            "Digital Labor and Platform Governance",
            "This paper develops a theoretical framing for a social science corpus.",
            "humanities_or_social_science",
        ),
        (
            "A Systematic Review of Retrieval-Augmented Generation",
            "We synthesize literature review evidence and summarize open problems.",
            "survey_or_review",
        ),
        (
            "A Review-Aware Optimizer for Neural Networks",
            "We propose a training method with ablation studies.",
            "AI_method",
        ),
        (
            "A Review of Optimizer Stability",
            "We propose a training method with ablation studies.",
            "AI_method",
        ),
    ],
)
def test_infer_paper_type_distinguishes_supported_types(title: str, abstract: str, expected: str) -> None:
    paper_type, _ = infer_paper_type(title, abstract)

    assert paper_type == expected


def test_resolve_domain_subdir_keeps_explicit_subdir_highest_priority(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    resolved = resolve_domain_subdir(
        config,
        title="Diffusion Policy for Robot Manipulation",
        abstract="Robotic manipulation and navigation.",
        subdir="Custom/Folder",
    )
    assert resolved == "Custom/Folder"


def test_domain_rules_are_loaded_from_user_editable_yaml(tmp_path: Path, monkeypatch) -> None:
    rules_path = tmp_path / "domain_rules.yaml"
    rules_path.write_text(
        """
domains:
  - label: 天文学
    aliases:
      - astronomy
    keywords:
      - galaxy survey
      - telescope
    methods:
      - transformer
fallback_domains:
  - label: 机器学习
    aliases:
      - machine learning
    keywords:
      - transformer
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(common, "DOMAIN_RULES_PATH", rules_path)

    assert infer_domain_label("Transformer analysis for galaxy survey data") == "天文学"


def test_domain_rules_missing_or_invalid_falls_back(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "DOMAIN_RULES_PATH", tmp_path / "missing.yaml")
    assert (
        infer_domain_label("Diffusion Policy for Robot Manipulation", "robotic control")
        == "机器人"
    )

    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text("domains:\n  - aliases:\n      - no label\n", encoding="utf-8")
    monkeypatch.setattr(common, "DOMAIN_RULES_PATH", invalid_path)
    assert (
        infer_domain_label("Diffusion Policy for Robot Manipulation", "robotic control")
        == "机器人"
    )


def test_env_config_value_falls_back_to_shell_file(tmp_path: Path, monkeypatch) -> None:
    shell_file = tmp_path / ".zshenv"
    shell_file.write_text(
        '\n# comment\nexport DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY="file_based_key"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.setattr("common.SHELL_CONFIG_FILES", [shell_file])

    assert env_config_value("DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY") == "file_based_key"
    assert semantic_scholar_headers()["x-api-key"] == "file_based_key"


def test_check_environment_reports_semantic_scholar_key_from_env(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY"] = "env_key"

    result = subprocess.run(
        [sys.executable, str(ENV_SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["python"]["executable"]
    assert payload["python"]["version"]
    assert isinstance(payload["python"]["fitz_installed"], bool)
    assert isinstance(payload["python"]["pytesseract_installed"], bool)
    assert isinstance(payload["python"]["pillow_installed"], bool)
    assert payload["metadata"]["semantic_scholar_api_key_configured"] is True


def test_extract_negative_claims_detects_unstable_ablation_sentence() -> None:
    text = (
        "Without the retrieval module, F1 drops by 3.2 points and training becomes unstable after 10k steps. "
        "Our full model improves AUROC by 1.1 points."
    )
    claims = extract_negative_claims(text)
    assert len(claims) == 1
    assert "drops by 3.2 points" in claims[0]


def test_extract_negative_claims_ignores_positive_without_sentence() -> None:
    text = "Without extra fine-tuning, the model still outperforms the strongest baseline by 2.0 points."
    claims = extract_negative_claims(text)
    assert claims == []


def test_extract_mechanism_flow_sentences_prefers_action_chain_language() -> None:
    text = (
        "The visual encoder extracts frame-level features and sends them to the projection layer. "
        "The fusion module concatenates audio tokens with visual tokens and compresses them into shared representations. "
        "The decoder then generates the final response."
    )
    claims = extract_mechanism_flow_sentences(text)
    assert len(claims) == 3
    assert "extracts frame-level features" in claims[0]


def test_fetch_arxiv_entries_returns_empty_on_http_error(monkeypatch) -> None:
    def raising_http_get_text(*args: object, **kwargs: object) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr("common.http_get_text", raising_http_get_text)

    assert fetch_arxiv_entries(search_query='ti:"test"', max_results=1) == []


def test_fetch_arxiv_entries_returns_empty_on_invalid_xml(monkeypatch) -> None:
    monkeypatch.setattr("common.http_get_text", lambda *args, **kwargs: "<not-xml")

    assert fetch_arxiv_entries(search_query='ti:"test"', max_results=1) == []


def test_resolve_reference_title_survives_arxiv_failure(monkeypatch) -> None:
    semantic_match = {
        "title": "Example Paper",
        "authors": ["Alice Example"],
        "abstract": "Strong abstract",
        "venue": "ExampleConf",
        "year": "2025",
        "metadata_sources": ["semantic_scholar"],
    }
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [semantic_match])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.fetch_arxiv_entries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("arxiv down")))

    resolved = resolve_reference("Example Paper")

    assert resolved["status"] == "ok"
    assert resolved["title"] == "Example Paper"
    assert "semantic_scholar" in (resolved.get("metadata_sources") or [])
    assert resolved["identity_confidence"] == "medium"
    assert "external_metadata_title_match" in resolved["identity_confidence_reasons"]


def test_resolve_reference_doi_sets_high_identity_confidence(monkeypatch) -> None:
    monkeypatch.setattr("common.fetch_crossref_by_doi", lambda *args, **kwargs: None)

    resolved = resolve_reference("10.1000/example")

    assert resolved["identity_confidence"] == "high"
    assert "doi_present" in resolved["identity_confidence_reasons"]


def test_resolve_reference_arxiv_id_sets_high_identity_confidence(monkeypatch) -> None:
    monkeypatch.setattr(
        "common.safe_fetch_arxiv_entries",
        lambda *args, **kwargs: [
            {
                "title": "Arxiv Paper",
                "arxiv_id": "2501.00001",
                "metadata_sources": ["arxiv"],
            }
        ],
    )

    resolved = resolve_reference("2501.00001")

    assert resolved["identity_confidence"] == "high"
    assert "arxiv_id_present" in resolved["identity_confidence_reasons"]


def test_resolve_reference_zotero_key_sets_high_identity_confidence() -> None:
    resolved = resolve_reference("ABCDEFGH")

    assert resolved["identity_confidence"] == "high"
    assert "zotero_key_present" in resolved["identity_confidence_reasons"]


def test_resolve_reference_local_pdf_with_extracted_doi_sets_high_identity_confidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        metadata={},
        pages=["A Strong Enough Paper Title For Testing\nhttps://doi.org/10.1234/test"],
    )
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    resolved = resolve_reference(str(pdf_path))

    assert resolved["identity_confidence"] == "high"
    assert "doi_present" in resolved["identity_confidence_reasons"]
    assert "first_page_title_used" in resolved["identity_confidence_reasons"]


def test_resolve_reference_local_pdf_artifact_stem_sets_low_identity_confidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "Touvron 等 - 2023 - LLaMA Open and Efficient Foundation Language Models-824666.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(metadata={}, pages=["Abstract\nshort"])
    monkeypatch.setattr("common.fitz", FakeFitz(fake_doc))

    resolved = resolve_reference(str(pdf_path))

    assert resolved["identity_confidence"] == "low"
    assert "local_pdf_artifact_title" in resolved["identity_confidence_reasons"]
    assert "local_pdf_stem_used" in resolved["identity_confidence_reasons"]


def test_enrich_metadata_survives_arxiv_failure(monkeypatch) -> None:
    semantic_match = {
        "title": "Example Paper",
        "authors": ["Alice Example", "Bob Example"],
        "abstract": "Strong abstract",
        "venue": "ExampleConf",
        "year": "2025",
        "doi": "10.1000/example",
        "metadata_sources": ["semantic_scholar"],
    }
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [semantic_match])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.fetch_arxiv_entries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("arxiv down")))

    enriched = enrich_metadata({"title": "Example Paper", "arxiv_id": "2501.00001", "metadata_sources": ["seed_record"]})

    assert enriched["title"] == "Example Paper"
    assert enriched["doi"] == "10.1000/example"
    assert enriched["venue"] == "ExampleConf"
    assert enriched["year"] == "2025"
    assert enriched["abstract"] == "Strong abstract"


def test_normalize_openalex_keeps_landing_page_out_of_pdf_url() -> None:
    normalized = common.normalize_openalex_work(
        {
            "display_name": "The Effectiveness of Crisis Line Services: A Systematic Review",
            "ids": {"doi": "https://doi.org/10.3389/fpubh.2019.00399"},
            "primary_location": {
                "landing_page_url": "https://doi.org/10.3389/fpubh.2019.00399",
                "source": {"display_name": "Frontiers in Public Health"},
            },
            "best_oa_location": {
                "landing_page_url": "https://doi.org/10.3389/fpubh.2019.00399",
            },
            "publication_year": 2020,
        }
    )

    assert normalized["pdf_url"] == ""
    assert normalized["source_url"] == "https://doi.org/10.3389/fpubh.2019.00399"


def test_enrich_metadata_local_pdf_corrects_artifact_title_and_fills_arxiv(monkeypatch) -> None:
    semantic_match = {
        "title": "LLaMA: Open and Efficient Foundation Language Models",
        "authors": ["Hugo Touvron", "Thibaut Lavril"],
        "venue": "arXiv.org",
        "year": "2023",
        "doi": "10.48550/arXiv.2302.13971",
        "arxiv_id": "2302.13971",
        "metadata_sources": ["semantic_scholar"],
        "source": "semantic_scholar",
        "source_type": "semantic_scholar",
        "source_url": "https://www.semanticscholar.org/paper/llama",
    }
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [semantic_match])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.safe_fetch_arxiv_entries", lambda *args, **kwargs: [])

    enriched = enrich_metadata(
        {
            "source_type": "local_pdf",
            "title": "Touvron 等 - 2023 - LLaMA Open and Efficient Foundation Language Models-824666",
            "local_pdf_path": "/tmp/llama.pdf",
            "metadata_sources": ["local_pdf"],
        }
    )

    assert enriched["title"] == "LLaMA: Open and Efficient Foundation Language Models"
    assert enriched["doi"] == "10.48550/arXiv.2302.13971"
    assert enriched["arxiv_id"] == "2302.13971"
    assert "semantic_scholar" in enriched["metadata_sources"]
    assert enriched["identity_confidence"] == "high"
    assert "arxiv_id_present" in enriched["identity_confidence_reasons"]


def test_enrich_metadata_local_pdf_corrected_title_sets_medium_identity_confidence(monkeypatch) -> None:
    semantic_match = {
        "title": "A Strong External Metadata Title For Testing",
        "authors": ["Alice Example"],
        "venue": "ExampleConf",
        "year": "2025",
        "metadata_sources": ["semantic_scholar"],
        "source": "semantic_scholar",
        "source_type": "semantic_scholar",
        "source_url": "https://www.semanticscholar.org/paper/example",
    }
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [semantic_match])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.safe_fetch_arxiv_entries", lambda *args, **kwargs: [])

    enriched = enrich_metadata(
        {
            "source_type": "local_pdf",
            "title": "Li 等 - 2025 - A Strong External Metadata Title For Testing-123456",
            "local_pdf_path": "/tmp/example.pdf",
            "metadata_sources": ["local_pdf"],
            "identity_confidence": "low",
            "identity_confidence_reasons": ["local_pdf_artifact_title", "local_pdf_stem_used"],
        }
    )

    assert enriched["title"] == "A Strong External Metadata Title For Testing"
    assert enriched["identity_confidence"] == "medium"
    assert "external_metadata_title_match" in enriched["identity_confidence_reasons"]


def test_enrich_metadata_local_pdf_prefers_published_doi_over_preprint(monkeypatch) -> None:
    published = {
        "title": "Identifying psychiatric manifestations in outpatients with depression and anxiety: a large language model-based approach",
        "authors": ["Shihao Xu"],
        "venue": "npj Mental Health Research",
        "year": "2025",
        "doi": "10.1038/s44184-025-00175-1",
        "metadata_sources": ["crossref"],
        "source": "crossref",
        "source_type": "crossref",
        "source_url": "https://doi.org/10.1038/s44184-025-00175-1",
    }
    preprint = {
        "title": "Identifying Psychiatric Manifestations in Outpatients with Depression and Anxiety: A Large Language Model-Based Approach",
        "authors": ["Shihao Xu"],
        "venue": "",
        "year": "2025",
        "doi": "10.1101/2025.01.03.24318117",
        "metadata_sources": ["crossref"],
        "source": "crossref",
        "source_type": "crossref",
        "source_url": "https://doi.org/10.1101/2025.01.03.24318117",
    }
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.safe_fetch_arxiv_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [preprint, published])

    enriched = enrich_metadata(
        {
            "source_type": "local_pdf",
            "title": "Xu 等 - 2025 - Identifying psychiatric manifestations in outpatients with depression and anxiety a large language-182952",
            "local_pdf_path": "/tmp/mental_health.pdf",
            "metadata_sources": ["local_pdf"],
        }
    )

    assert enriched["title"] == "Identifying psychiatric manifestations in outpatients with depression and anxiety: a large language model-based approach"
    assert enriched["doi"] == "10.1038/s44184-025-00175-1"
    assert enriched["venue"] == "npj Mental Health Research"


def test_enrich_metadata_backfills_arxiv_doi_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("common.safe_fetch_arxiv_entries", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_semantic_scholar", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_crossref_by_title", lambda *args, **kwargs: [])
    monkeypatch.setattr("common.search_openalex_by_title", lambda *args, **kwargs: [])
    enriched = enrich_metadata({"title": "Example Paper", "arxiv_id": "2302.13971", "metadata_sources": ["seed_record"]})
    assert enriched["doi"] == "10.48550/arXiv.2302.13971"


def test_resolve_reference_arxiv_id_survives_arxiv_failure(monkeypatch) -> None:
    monkeypatch.setattr("common.fetch_arxiv_entries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("arxiv down")))

    resolved = resolve_reference("2501.00001")

    assert resolved["status"] == "ok"
    assert resolved["source_type"] == "arxiv_id"
    assert resolved["arxiv_id"] == "2501.00001"
    assert resolved["paper_id"] == "arxiv:2501.00001"
    assert resolved["pdf_url"] == "https://arxiv.org/pdf/2501.00001.pdf"
    assert resolved["identity_confidence"] == "high"


def test_resolve_reference_arxiv_url_survives_arxiv_failure(monkeypatch) -> None:
    monkeypatch.setattr("common.fetch_arxiv_entries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("arxiv down")))

    resolved = resolve_reference("https://arxiv.org/abs/2501.00001")

    assert resolved["status"] == "ok"
    assert resolved["source_type"] == "arxiv_url"
    assert resolved["arxiv_id"] == "2501.00001"
    assert resolved["paper_id"] == "arxiv:2501.00001"
    assert resolved["pdf_url"] == "https://arxiv.org/pdf/2501.00001.pdf"
    assert resolved["identity_confidence"] == "high"
