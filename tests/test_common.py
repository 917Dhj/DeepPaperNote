from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from common import (
    env_config_value,
    existing_domain_dirs,
    extract_arxiv_id,
    extract_doi,
    infer_domain_label,
    infer_source_type,
    resolve_domain_subdir,
    resolve_note_output_mode,
    resolve_obsidian_note_path,
    semantic_scholar_headers,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_SCRIPT = PROJECT_ROOT / "scripts" / "check_environment.py"


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
        "papers_dir": "20_Research/Papers",
    }
    path = resolve_obsidian_note_path(config, title="My Test Paper")
    assert path == tmp_path / "DeepPaperNote_output" / "My_Test_Paper" / "My_Test_Paper.md"


def test_resolve_obsidian_note_path_in_vault_mode(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "20_Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    path = resolve_obsidian_note_path(config, title="My Test Paper", subdir="心理健康")
    assert path == vault / "20_Research/Papers" / "心理健康" / "My_Test_Paper" / "My_Test_Paper.md"


def test_existing_domain_dirs_excludes_root_level_paper_folder(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "20_Research" / "Papers"
    (papers / "大模型").mkdir(parents=True)
    paper_dir = papers / "Attention_Is_All_You_Need"
    paper_dir.mkdir(parents=True)
    (paper_dir / "Attention_Is_All_You_Need.md").write_text("# note\n", encoding="utf-8")

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "20_Research/Papers",
        "workspace_output_dir": "DeepPaperNote_output",
    }
    assert existing_domain_dirs(config) == ["大模型"]


def test_resolve_domain_subdir_prefers_existing_domain(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "20_Research" / "Papers"
    (papers / "大模型").mkdir(parents=True)
    (papers / "心理健康").mkdir(parents=True)
    paper_dir = papers / "Attention_Is_All_You_Need"
    paper_dir.mkdir(parents=True)
    (paper_dir / "Attention_Is_All_You_Need.md").write_text("# note\n", encoding="utf-8")

    config = {
        "obsidian_vault": str(vault),
        "papers_dir": "20_Research/Papers",
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
