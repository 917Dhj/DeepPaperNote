from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from common import (
    clean_local_pdf_stem,
    extract_local_pdf_hints,
    env_config_value,
    existing_domain_dirs,
    extract_arxiv_id,
    extract_doi,
    extract_mechanism_flow_sentences,
    extract_negative_claims,
    infer_domain_label,
    infer_source_type,
    fetch_arxiv_entries,
    enrich_metadata,
    normalize_pdf_text_artifacts,
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


def test_infer_source_type_for_local_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    assert infer_source_type(str(pdf_path)) == "local_pdf"


def test_clean_local_pdf_stem_removes_zotero_style_noise() -> None:
    stem = "Xu 等 - 2025 - Identifying psychiatric manifestations in outpatients with depression and anxiety a large language-182952"
    assert clean_local_pdf_stem(stem) == "Identifying psychiatric manifestations in outpatients with depression and anxiety a large language"


def test_normalize_pdf_text_artifacts_expands_ligatures() -> None:
    assert normalize_pdf_text_artifacts("Efﬁcient ﬂow oﬀers aﬃne aﬄuent") == "Efficient flow offers affine affluent"


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


def test_infer_domain_label_defaults_to_psychology_when_relevant() -> None:
    label = infer_domain_label(
        "Using a fine-tuned large language model for symptom-based depression evaluation",
        "We study clinical depression screening with patients and psychological symptom scales.",
    )
    assert label == "心理健康"


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
    assert resolved["source_type"] == "title_query"
    assert resolved["title"] == "2501.00001"


def test_resolve_reference_arxiv_url_survives_arxiv_failure(monkeypatch) -> None:
    monkeypatch.setattr("common.fetch_arxiv_entries", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("arxiv down")))

    resolved = resolve_reference("https://arxiv.org/abs/2501.00001")

    assert resolved["status"] == "ok"
    assert resolved["source_type"] == "title_query"
    assert resolved["title"] == "https://arxiv.org/abs/2501.00001"
