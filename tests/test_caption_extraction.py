from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from common import caption_label_key, extract_caption_lines, normalize_caption_label
from plan_figure_table_decisions import matched_figure_asset
from plan_figures import _match_figure_asset, classify_caption_kind
from test_extract_pdf_assets_quality import EXTRACT_PDF_ASSETS_SCRIPT, write_fetch_input
from test_extract_source_text import run_extract_source
from test_paper_corpus import run_preparation

fitz = pytest.importorskip("fitz")

PROSE = "This paragraph is ordinary body text and it continues for a while without any label."
REFERENCE_PADDING = " and the reference keeps going so that it outruns the real caption"


def add_text(page, top: float, text: str, *, height: float = 60, **options: object) -> None:
    page.insert_textbox(fitz.Rect(72, top, 540, top + height), text, fontsize=10, **options)


def add_visual(page, top: float = 80, height: float = 120) -> None:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 200), False)
    pixmap.set_rect(pixmap.irect, (40, 120, 200))
    page.insert_image(fitz.Rect(150, top, 450, top + height), pixmap=pixmap)


def manifest_captions(tmp_path: Path, doc, *extra: str) -> dict:
    pdf_path = tmp_path / "paper.pdf"
    doc.save(pdf_path)
    input_path = tmp_path / "fetch.json"
    write_fetch_input(input_path, pdf_path, title="Caption Paper")
    return run_extract_source(input_path, tmp_path / "paper_source_manifest.json", *extra)[
        "captions"
    ]


def figure_assets(tmp_path: Path, doc) -> list[dict]:
    pdf_path = tmp_path / "paper.pdf"
    doc.save(pdf_path)
    input_path = tmp_path / "fetch.json"
    output_path = tmp_path / "assets.json"
    write_fetch_input(input_path, pdf_path, title="Caption Paper")
    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_PDF_ASSETS_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--assets-dir",
            str(tmp_path / "assets"),
        ],
        check=True,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))["figure_assets"]


def test_wrapped_caption_is_complete_and_stops_at_the_next_paragraph(tmp_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_text(
        page,
        200,
        "Figure 1: Accuracy of the proposed representa-\ntion on every benchmark dataset.",
    )
    add_text(page, 300, PROSE)
    captions = manifest_captions(tmp_path, doc)
    assert [(item["id"], item["caption"]) for item in captions["figures"]] == [
        ("Figure 1", "Accuracy of the proposed representation on every benchmark dataset.")
    ]


@pytest.mark.parametrize(
    ("caption", "expected_id", "kind", "reference"),
    [
        ("Figure 4. Training curves.", "Figure 4", "figures", "Fig. 4. First, the result flips"),
        ("Table 3: Zero-shot transfer.", "Table 3", "tables", "Table 3: recall at 50% precision"),
        ("Figure 17: Mask similarity.", "Figure 17", "figures", "Fig. 17, we show three examples"),
    ],
)
def test_reference_wrapped_inside_a_paragraph_loses_to_the_block_start_caption(
    tmp_path: Path, caption: str, expected_id: str, kind: str, reference: str
) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_text(page, 100, f"{PROSE}\n{reference}{REFERENCE_PADDING}\n{PROSE}")
    add_text(page, 300, caption)
    captions = manifest_captions(tmp_path, doc)
    assert [item["id"] for item in captions[kind]] == [expected_id]
    assert captions[kind][0]["caption"] == caption.split(maxsplit=2)[2]


def reference_before_caption_pages() -> fitz.Document:
    doc = fitz.open()
    first = doc.new_page()
    add_visual(first)
    add_text(first, 220, "Fig. 13 (left) plots the performance on cumulative data.\nMore prose.")
    second = doc.new_page()
    add_visual(second)
    add_text(second, 220, "Figure 13: Ablation studies.")
    return doc


def test_paragraph_opening_reference_on_an_earlier_page_loses_to_the_caption(
    tmp_path: Path,
) -> None:
    captions = manifest_captions(tmp_path, reference_before_caption_pages())
    assert [(item["id"], item["caption"], item["page"]) for item in captions["figures"]] == [
        ("Figure 13", "Ablation studies.", 2)
    ]


def test_weaker_reference_does_not_become_a_crop_anchor(tmp_path: Path) -> None:
    assets = figure_assets(tmp_path, reference_before_caption_pages())
    assert [(item["label"], item["page_number"]) for item in assets] == [("Figure 13", 2)]


def test_reference_beyond_a_truncated_caption_is_still_rejected(tmp_path: Path) -> None:
    captions = manifest_captions(tmp_path, reference_before_caption_pages(), "--max-pages", "1")
    assert captions["figures"] == []


def test_subpanel_prose_reference_is_not_a_caption(tmp_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_text(page, 100, "Figure 2: Accuracy overview.")
    add_text(page, 200, "Fig 2c shows additional baselines and others in the same setting.")
    captions = manifest_captions(tmp_path, doc)
    assert [item["id"] for item in captions["figures"]] == ["Figure 2"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Figure 1 Model overview", "Model overview"),
        ("Fig. 1 | Model overview", "Model overview"),
    ],
)
def test_title_and_journal_caption_styles_survive(tmp_path: Path, line: str, expected: str) -> None:
    doc = fitz.open()
    add_text(doc.new_page(), 100, line)
    captions = manifest_captions(tmp_path, doc)
    assert [item["caption"] for item in captions["figures"]] == [expected]


def test_label_on_its_own_block_takes_the_following_text_caption(tmp_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_text(page, 100, "Figure 5")
    add_text(page, 160, "Accuracy of every model.")
    captions = manifest_captions(tmp_path, doc)
    assert [item["caption"] for item in captions["figures"]] == ["Accuracy of every model."]


def test_cjk_captions_use_layout_and_join_without_spaces(tmp_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_visual(page)
    add_text(page, 220, "图 1：总体框架的第一行\n继续说明第二行。", fontname="china-s")
    add_visual(page, top=340)
    add_text(page, 480, "表 1 实验结果", fontname="china-s")
    captions = manifest_captions(tmp_path, doc)
    assert [(item["id"], item["caption"]) for item in captions["figures"]] == [
        ("图 1", "总体框架的第一行继续说明第二行。")
    ]
    assert [(item["id"], item["caption"]) for item in captions["tables"]] == [("表 1", "实验结果")]
    assets = figure_assets(tmp_path, doc)
    assert [(item["label"], item["kind"]) for item in assets] == [
        ("图 1", "figure"),
        ("表 1", "table"),
    ]


def test_equally_strong_continued_captions_keep_every_page(tmp_path: Path) -> None:
    doc = fitz.open()
    for suffix in ("Results.", "Results (continued)."):
        page = doc.new_page()
        add_visual(page)
        add_text(page, 220, f"Table 2: {suffix}")
    captions = manifest_captions(tmp_path, doc)
    assert [item["page"] for item in captions["tables"]] == [1, 2]
    assert [item["page_number"] for item in figure_assets(tmp_path, doc)] == [1, 2]


def test_text_fallback_prefers_a_short_caption_over_a_lowercase_reference() -> None:
    text = "Table 3: Zero-shot transfer.\nTable 3: recall at 50% precision is high at the cost"
    assert extract_caption_lines(text, "table") == [
        {"id": "Table 3", "caption": "Zero-shot transfer."}
    ]


@pytest.mark.parametrize(
    ("label", "caption", "kind"),
    [
        (
            "Table 6",
            "Classification error on the CIFAR-10 test set. All methods use data augmentation.",
            "table_result",
        ),
        (
            "Figure 4",
            "Segment Anything Model overview. It outputs valid masks and confidence scores.",
            "method_overview",
        ),
        (
            "Figure 9",
            "Point to mask evaluation on 23 datasets. (a) Per-dataset comparison with baselines.",
            "main_result",
        ),
        (
            "Figure 2",
            "The Model. Our architecture divides the image into an even grid.",
            "method_overview",
        ),
    ],
)
def test_full_captions_classify_by_their_title_sentence(
    label: str, caption: str, kind: str
) -> None:
    assert classify_caption_kind(label, caption)[0] == kind


@pytest.mark.parametrize(
    ("label", "normalized"),
    [("图１", "图 1"), ("图 １", "图 1"), ("表１２", "表 12"), ("图1", "图 1")],
)
def test_caption_labels_normalize_fullwidth_digits_and_spacing(label: str, normalized: str) -> None:
    assert normalize_caption_label(label) == normalized
    assert caption_label_key(label) == caption_label_key(normalized)


@pytest.mark.parametrize(
    ("caption_id", "asset_label"),
    [
        ("图 1", "图1"),
        ("图 1", "图１"),
        ("表 2", "表２"),
        ("Fig 3", "Figure 3"),
        ("Extended Data Fig 1", "Extended Data Fig. 1"),
        ("Fig S1", "Fig. S1"),
    ],
)
def test_figure_assets_match_their_normalized_caption_id(caption_id: str, asset_label: str) -> None:
    asset = {"label": asset_label}
    assert _match_figure_asset(caption_id, [asset]) == asset
    assert matched_figure_asset({"figure_assets": [asset]}, caption_id) == asset


@pytest.mark.parametrize(
    ("line", "source_id"),
    [("图1　便携式检测仪", "图 1"), ("图１　便携式检测仪", "图 1")],
)
def test_cjk_caption_crop_reaches_visual_review(tmp_path: Path, line: str, source_id: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    add_text(page, 72, PROSE)
    add_visual(page, top=160, height=240)
    add_text(page, 420, line, fontname="china-s")
    pdf_path = tmp_path / "paper.pdf"
    doc.save(pdf_path)
    run = run_preparation(pdf_path, tmp_path / "run", dict(os.environ))
    assert run["decisions"] == {source_id: "review_pending"}
