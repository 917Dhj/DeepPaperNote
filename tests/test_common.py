from __future__ import annotations

from pathlib import Path

from common import extract_arxiv_id, extract_doi, infer_source_type, resolve_note_output_mode, resolve_obsidian_note_path


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
