from __future__ import annotations

from pathlib import Path

import citation_links
import build_synthesis_bundle
from build_synthesis_bundle import bundle
from citation_links import extract_reference_candidates_from_pdf, resolve_reference_links


class FakePdfPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self.text


class FakePdfDoc:
    def __init__(self, pages: list[str]) -> None:
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


def test_extract_reference_candidates_from_pdf_parses_references_section(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        [
            "Introduction\nThe paper cites prior work.",
            "\n".join(
                [
                    "References",
                    "[1] Vaswani et al. (2017). Attention Is All You Need.",
                    "[2] Devlin et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers.",
                ]
            ),
        ]
    )
    monkeypatch.setattr(citation_links, "fitz", FakeFitz(fake_doc))

    candidates = extract_reference_candidates_from_pdf(pdf_path, references_start_page=2)

    assert [
        {
            "display_text": item["display_text"],
            "page_hint": item["page_hint"],
            "wikilink": item["wikilink"],
            "match_status": item["match_status"],
            "match_reason": item["match_reason"],
        }
        for item in candidates
    ] == [
        {
            "display_text": "Vaswani et al. (2017). Attention Is All You Need.",
            "page_hint": "p. 2",
            "wikilink": "",
            "match_status": "no_vault_match",
            "match_reason": "none",
        },
        {
            "display_text": "Devlin et al. (2019). BERT: Pre-training of Deep Bidirectional Transformers.",
            "page_hint": "p. 2",
            "wikilink": "",
            "match_status": "no_vault_match",
            "match_reason": "none",
        },
    ]


def test_resolve_reference_links_matches_vault_stem_title_and_alias(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "bert_pretraining.md").write_text(
        "---\naliases: []\n---\n# BERT Pretraining\n",
        encoding="utf-8",
    )
    (papers / "attention_transformer.md").write_text(
        "---\naliases:\n  - Attention Is All You Need\n  - Transformer\n---\n# Transformer\n",
        encoding="utf-8",
    )
    candidates = [
        {"display_text": "Devlin et al. (2019). BERT Pretraining.", "source": "pdf_references"},
        {"display_text": "Vaswani et al. (2017). Attention Is All You Need.", "source": "pdf_references"},
    ]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert [item["wikilink"] for item in resolved] == [
        "[[bert_pretraining|Devlin et al. (2019). BERT Pretraining.]]",
        "[[attention_transformer|Vaswani et al. (2017). Attention Is All You Need.]]",
    ]
    assert [item["vault_target"] for item in resolved] == ["bert_pretraining", "attention_transformer"]
    assert [item["match_status"] for item in resolved] == ["vault_match", "vault_match"]
    assert [item["match_reason"] for item in resolved] == [
        "basename_or_title_or_alias",
        "basename_or_title_or_alias",
    ]


def test_resolve_reference_links_indexes_only_yaml_frontmatter_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "attention_without_frontmatter.md").write_text(
        "# Attention Is All You Need\n",
        encoding="utf-8",
    )
    candidates = [{"display_text": "Vaswani et al. (2017). Attention Is All You Need."}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "no_vault_match"
    assert resolved[0]["match_reason"] == "none"
    assert resolved[0]["wikilink"] == ""
    assert resolved[0]["vault_target"] == ""


def test_resolve_reference_links_prioritizes_doi_over_text(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "doi_target.md").write_text(
        "---\ndoi: 10.5555/example.doi\naliases: []\n---\n# DOI Target\n",
        encoding="utf-8",
    )
    (papers / "text_target.md").write_text(
        "---\naliases:\n  - Confusing Text Match\n---\n# Text Target\n",
        encoding="utf-8",
    )
    candidates = [
        {
            "display_text": "Confusing Text Match. doi:10.5555/example.doi",
            "doi": "10.5555/example.doi",
        }
    ]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "vault_match"
    assert resolved[0]["match_reason"] == "doi"
    assert resolved[0]["vault_target"] == "doi_target"
    assert resolved[0]["wikilink"] == "[[doi_target|Confusing Text Match. doi:10.5555/example.doi]]"


def test_resolve_reference_links_matches_arxiv_from_note_doi(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "arxiv_doi_note.md").write_text(
        "---\ndoi: 10.48550/arXiv.2406.11161\naliases: []\n---\n# Arxiv DOI Note\n",
        encoding="utf-8",
    )
    candidates = [{"display_text": "Some paper. arXiv:2406.11161"}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "vault_match"
    assert resolved[0]["match_reason"] == "arxiv_id"
    assert resolved[0]["vault_target"] == "arxiv_doi_note"


def test_resolve_reference_links_reports_ambiguous_text_match(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "first_transformer.md").write_text(
        "---\ntitle: Shared Transformer Paper\naliases: []\n---\n# First\n",
        encoding="utf-8",
    )
    (papers / "second_transformer.md").write_text(
        "---\naliases:\n  - Shared Transformer Paper\n---\n# Second\n",
        encoding="utf-8",
    )
    candidates = [{"display_text": "A citation to Shared Transformer Paper."}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "ambiguous_match"
    assert resolved[0]["match_reason"] == "basename_or_title_or_alias"
    assert resolved[0]["wikilink"] == ""
    assert resolved[0]["vault_target"] == ""
    assert [item["vault_target"] for item in resolved[0]["match_candidates"]] == [
        "first_transformer",
        "second_transformer",
    ]


def test_resolve_reference_links_reports_ambiguous_doi_match(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "first_doi_note.md").write_text(
        "---\ndoi: 10.5555/duplicate\naliases: []\n---\n# First DOI Note\n",
        encoding="utf-8",
    )
    (papers / "second_doi_note.md").write_text(
        "---\ndoi: 10.5555/duplicate\naliases: []\n---\n# Second DOI Note\n",
        encoding="utf-8",
    )
    candidates = [{"display_text": "Duplicate DOI reference.", "doi": "10.5555/duplicate"}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "ambiguous_match"
    assert resolved[0]["match_reason"] == "doi"
    assert resolved[0]["wikilink"] == ""
    assert resolved[0]["vault_target"] == ""
    assert [item["vault_target"] for item in resolved[0]["match_candidates"]] == [
        "first_doi_note",
        "second_doi_note",
    ]


def test_resolve_reference_links_ignores_short_acronym_aliases(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    papers = vault / "Research" / "Papers"
    papers.mkdir(parents=True)
    (papers / "retrieval_augmented_generation.md").write_text(
        "---\naliases:\n  - RAG\n  - GSPO\n  - LoRA\n---\n# Retrieval Augmented Generation\n",
        encoding="utf-8",
    )
    candidates = [
        {"display_text": "RAG improves answers."},
        {"display_text": "GSPO is cited here."},
        {"display_text": "LoRA is cited here."},
    ]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert [item["match_status"] for item in resolved] == ["no_vault_match"] * 3
    assert [item["wikilink"] for item in resolved] == [""] * 3


def test_resolve_reference_links_uses_plain_text_when_no_vault_match(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "Research" / "Papers").mkdir(parents=True)
    candidates = [{"display_text": "Unknown Future Paper.", "source": "pdf_references"}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": str(vault)})

    assert resolved[0]["match_status"] == "no_vault_match"
    assert resolved[0]["match_reason"] == "none"
    assert resolved[0]["wikilink"] == ""
    assert resolved[0]["vault_target"] == ""


def test_resolve_reference_links_reports_no_vault_without_guessing_wikilinks() -> None:
    candidates = [{"display_text": "Attention Is All You Need.", "source": "pdf_references"}]

    resolved = resolve_reference_links(candidates, {"obsidian_vault": ""})

    assert resolved[0]["match_status"] == "vault_unavailable"
    assert resolved[0]["match_reason"] == "none"
    assert resolved[0]["wikilink"] == ""
    assert resolved[0]["vault_target"] == ""


def test_bundle_exposes_reference_candidates_under_references(monkeypatch) -> None:
    monkeypatch.setattr(
        build_synthesis_bundle,
        "runtime_config",
        lambda: {"obsidian_vault": "", "papers_dir": "Research/Papers"},
    )

    synthesis = bundle(
        metadata={"title": "Citation Paper"},
        evidence_wrapper={
            "evidence_pack": {
                "reference_candidates": [
                    {
                        "raw_text": "[1] Vaswani et al. (2017). Attention Is All You Need.",
                        "display_text": "Vaswani et al. (2017). Attention Is All You Need.",
                    }
                ]
            }
        },
        figures_wrapper={},
        assets_wrapper={},
    )

    candidates = synthesis["references"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["display_text"] == "Vaswani et al. (2017). Attention Is All You Need."
    assert candidates[0]["match_status"] == "vault_unavailable"
    assert candidates[0]["wikilink"] == ""
