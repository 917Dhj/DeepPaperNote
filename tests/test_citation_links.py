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


def test_resolve_reference_links_matches_vault_basename_and_alias(tmp_path: Path) -> None:
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
    assert [item["match_reason"] for item in resolved] == ["basename", "alias"]


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
