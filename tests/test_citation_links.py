from __future__ import annotations

from pathlib import Path

import build_synthesis_bundle
import citation_links
import vault_connections
from citation_links import extract_reference_candidates_from_pdf


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


def test_extracts_author_year_bibliography_between_heading_and_appendix(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(
        [
            "\n".join([
                "Limitations",
                "As recent studies have shown (Razeghi et al., 2022), tail phenomena matter.",
                "References",
                "Massih-Reza Amini, Vasilii Feofanov, Loic Pauletto,",
                "Emilie Devijver, and Yury Maximov. 2022. Self-",
                "training: A survey. arXiv preprint arXiv:2202.12040.",
                "Hyung Won Chung, Le Hou, Shayne Longpre, Barret",
                "Zoph, Yi Tay, William Fedus, Eric Li, Xuezhi Wang,",
                "Mostafa Dehghani, Siddhartha Brahma, et al. 2022.",
                "Scaling instruction-finetuned language models.",
                "arXiv preprint arXiv:2210.11416.",
            ]),
            "\n".join([
                "Timo Schick and Hinrich Schütze. 2021. Generating",
                "datasets with pretrained language models. In Con-",
                "ference on Empirical Methods in Natural Language",
                "Processing (EMNLP).",
                "Kevin Lin. 2020. A single author paper. In ACL.",
            ]),
            "\n".join([
                "Supplemental Material",
                "A",
                "Implementation Details",
                "1. Write the seed tasks.",
                "2. Sample 2022. Generate new instructions.",
            ]),
        ]
    )
    monkeypatch.setattr(citation_links, "fitz", FakeFitz(fake_doc))

    candidates = extract_reference_candidates_from_pdf(
        pdf_path, references_start_page=1, max_pages=30, max_items=400
    )

    assert [item["display_text"][:40] for item in candidates] == [
        "Massih-Reza Amini, Vasilii Feofanov, Loi",
        "Hyung Won Chung, Le Hou, Shayne Longpre,",
        "Timo Schick and Hinrich Schütze. 2021. G",
        "Kevin Lin. 2020. A single author paper. ",
    ]
    assert candidates[0]["arxiv_id"].endswith("2202.12040")
    assert candidates[2]["page_hint"] == "p. 2"


def test_lines_starting_with_a_year_are_not_numbered_references(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    fake_doc = FakePdfDoc(["\n".join([
        "References",
        "Ana Smith, Bo Li, and Cy Wu.",
        "2023. A paper whose year starts the line. In ACL.",
        "Dan Brown and Eve Stone. 2021. Another paper. In EMNLP.",
        "Fay Green, Gus Hall, and Hal King. 2020. Third paper. In NAACL.",
    ])])
    monkeypatch.setattr(citation_links, "fitz", FakeFitz(fake_doc))

    candidates = extract_reference_candidates_from_pdf(pdf_path, references_start_page=1)

    assert [item["display_text"][:12] for item in candidates] == ["Ana Smith, B", "Dan Brown an", "Fay Green, G"]


def recall(vault: Path, references: list[dict], full_text: str = "") -> dict:
    return vault_connections.connection_candidates(
        {"obsidian_vault": str(vault), "papers_dir": "Research/Papers"},
        references,
        full_text,
        "zh-CN",
    )


def cited_targets(vault: Path, references: list[dict]) -> list[tuple[str, str]]:
    return [(item["target"], item["match_reason"]) for item in recall(vault, references)["cited"]]


def papers_dir(tmp_path: Path) -> Path:
    papers = tmp_path / "vault" / "Research" / "Papers"
    papers.mkdir(parents=True)
    return papers


def test_cited_recall_matches_vault_stem_title_and_alias(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "bert_pretraining.md").write_text("---\naliases: []\n---\n# BERT Pretraining\n", encoding="utf-8")
    (papers / "attention_transformer.md").write_text(
        "---\naliases:\n  - Attention Is All You Need\n  - Transformer\n---\n# Transformer\n",
        encoding="utf-8",
    )
    references = [
        {"display_text": "Devlin et al. (2019). BERT Pretraining."},
        {"display_text": "Vaswani et al. (2017). Attention Is All You Need."},
    ]
    assert cited_targets(tmp_path / "vault", references) == [
        ("bert_pretraining", "title_or_alias"),
        ("attention_transformer", "title_or_alias"),
    ]


def test_cited_recall_indexes_only_frontmatter_notes(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "attention_without_frontmatter.md").write_text("# Attention Is All You Need\n", encoding="utf-8")
    assert cited_targets(tmp_path / "vault", [{"display_text": "Vaswani et al. (2017). Attention Is All You Need."}]) == []


def test_cited_recall_prioritizes_doi_over_text(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "doi_target.md").write_text("---\ndoi: 10.5555/example.doi\n---\n# DOI Target\n", encoding="utf-8")
    (papers / "text_target.md").write_text(
        "---\naliases:\n  - Confusing Text Match\n---\n# Text Target\n", encoding="utf-8"
    )
    references = [{"display_text": "Confusing Text Match. doi:10.5555/example.doi", "doi": "10.5555/example.doi"}]
    assert cited_targets(tmp_path / "vault", references) == [("doi_target", "doi")]


def test_cited_recall_matches_arxiv_from_note_doi(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "arxiv_doi_note.md").write_text(
        "---\ndoi: 10.48550/arXiv.2406.11161\n---\n# Arxiv DOI Note\n", encoding="utf-8"
    )
    references = [{"display_text": "Some paper. arXiv:2406.11161"}]
    assert cited_targets(tmp_path / "vault", references) == [("arxiv_doi_note", "arxiv_id")]


def test_cited_recall_drops_ambiguous_text_match(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "first_transformer.md").write_text(
        "---\ntitle: Shared Transformer Paper\n---\n# First\n", encoding="utf-8"
    )
    (papers / "second_transformer.md").write_text(
        "---\naliases:\n  - Shared Transformer Paper\n---\n# Second\n", encoding="utf-8"
    )
    assert cited_targets(tmp_path / "vault", [{"display_text": "A citation to Shared Transformer Paper."}]) == []


def test_cited_recall_ignores_short_acronym_aliases(tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "retrieval_augmented_generation.md").write_text(
        "---\naliases:\n  - RAG\n  - GSPO\n  - LoRA\n---\n# Retrieval Augmented Generation\n",
        encoding="utf-8",
    )
    references = [
        {"display_text": "RAG improves answers."},
        {"display_text": "GSPO is cited here."},
        {"display_text": "LoRA is cited here."},
    ]
    assert cited_targets(tmp_path / "vault", references) == []


def test_recall_without_a_vault_is_workspace_mode() -> None:
    result = vault_connections.connection_candidates(
        {"obsidian_vault": ""}, [{"display_text": "Attention Is All You Need."}], "", "zh-CN"
    )
    assert result == {"status": "workspace", "cited": [], "related": []}


def bundle_for(monkeypatch, tmp_path: Path, references: list[dict], *, admission: str = "") -> dict:
    vault = tmp_path / "vault"
    monkeypatch.setattr(
        build_synthesis_bundle,
        "runtime_config",
        lambda **_kwargs: {
            "output_language": "zh-CN",
            "save_mode": "obsidian",
            "obsidian_vault": str(vault),
            "papers_dir": "Research/Papers",
        },
    )
    full_text = tmp_path / "full_text.md"
    full_text.write_text("We evaluate on SuperNI.", encoding="utf-8")
    return build_synthesis_bundle.bundle(
        metadata={"title": "Citation Paper"},
        evidence_wrapper={"evidence_pack": {"reference_candidates": references}},
        figures_wrapper={"output_language": "zh-CN", "figure_plan": {}},
        assets_wrapper={},
        figure_decisions_wrapper={"output_language": "zh-CN", "decisions": []},
        source_manifest={
            "full_text_md_path": str(full_text),
            "identity_contract": {
                "artifact_type": "canonical_identity",
                "schema_version": 2,
                "paper_id": "paper:citation-test",
                "identity_verdict": "accepted",
                "work_level_identity": {"title": "Citation Paper"},
                "accepted_metadata": {"title": "Citation Paper"},
            },
        },
        own_directory=admission,
    )


def test_bundle_exposes_connection_candidates_and_no_bibliography(monkeypatch, tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    (papers / "AI" / "Transformer").mkdir(parents=True)
    (papers / "AI" / "Transformer" / "Transformer.zh-CN.md").write_text(
        "---\naliases: [Attention Is All You Need]\n---\n# Transformer\n", encoding="utf-8"
    )
    (papers / "AI" / "SuperNI").mkdir(parents=True)
    (papers / "AI" / "SuperNI" / "SuperNI.zh-CN.md").write_text(
        "---\ndatasets: [SuperNI]\n---\n# SuperNI\n", encoding="utf-8"
    )
    synthesis = bundle_for(
        monkeypatch, tmp_path,
        [{"raw_text": "[1] Vaswani et al. (2017). Attention Is All You Need.",
          "display_text": "Vaswani et al. (2017). Attention Is All You Need."}],
    )
    assert "references" not in synthesis
    recalled = synthesis["connection_candidates"]
    assert recalled["status"] == "ok"
    assert [item["target"] for item in recalled["cited"]] == ["Transformer.zh-CN"]
    assert [item["target"] for item in recalled["related"]] == ["SuperNI.zh-CN"]


def test_bundle_excludes_the_admitted_paper_directory(monkeypatch, tmp_path: Path) -> None:
    papers = papers_dir(tmp_path)
    own = papers / "AI" / "Citation_Paper"
    own.mkdir(parents=True)
    (own / "Citation_Paper.en.md").write_text("---\ndatasets: [SuperNI]\n---\n# Citation Paper\n", encoding="utf-8")
    synthesis = bundle_for(monkeypatch, tmp_path, [], admission=str(own))
    assert synthesis["connection_candidates"]["related"] == []


def test_admitted_target_directory_reads_the_preflight_payload(tmp_path: Path) -> None:
    admission = tmp_path / "admission.json"
    admission.write_text('{"status": "ok", "target_directory": "/vault/Papers/AI/X"}', encoding="utf-8")
    assert build_synthesis_bundle.admitted_target_directory(str(admission)) == "/vault/Papers/AI/X"
    assert build_synthesis_bundle.admitted_target_directory("") == ""
