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

from extract_pdf_assets import (
    CAPTION_RE,
    _caption_match_is_inline_reference,
    _classify_caption_kind,
    _classify_visual_quality,
    _estimate_figure_bbox_above_caption,
    _find_caption_blocks,
    _grow_table_region,
    _looks_like_text_table_row,
    _other_caption_labels_for_crop,
    _restrict_row_to_caption_column,
    _row_is_table_like,
    _unique_figure_asset_filename,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_PDF_ASSETS_SCRIPT = PROJECT_ROOT / "scripts" / "extract_pdf_assets.py"


def write_test_pdf(path: Path, pages: list[str]) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for PDF asset integration tests.")
    doc = fitz.open()
    try:
        for text in pages:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


def test_extract_pdf_assets_emits_asset_coverage(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    write_test_pdf(pdf_path, ["Page 1", "Page 2", "Page 3"])
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "assets.json"
    input_path.write_text(
        json.dumps({"paper_id": "paper:test", "title": "Coverage Paper", "pdf_path": str(pdf_path)}),
        encoding="utf-8",
    )

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
            "--max-pages",
            "2",
        ],
        check=True,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["asset_coverage"] == {
        "total_pages": 3,
        "asset_max_pages": 2,
        "asset_pages_scanned": 2,
        "truncated_due_to_asset_page_limit": True,
    }


def test_extract_pdf_assets_default_scans_short_pdf_without_truncation(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    write_test_pdf(pdf_path, ["Page 1", "Page 2", "Page 3"])
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "assets.json"
    input_path.write_text(
        json.dumps({"paper_id": "paper:test", "title": "Coverage Paper", "pdf_path": str(pdf_path)}),
        encoding="utf-8",
    )

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

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["asset_coverage"] == {
        "total_pages": 3,
        "asset_max_pages": 40,
        "asset_pages_scanned": 3,
        "truncated_due_to_asset_page_limit": False,
    }


def test_extract_pdf_assets_default_truncates_after_40_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    write_test_pdf(pdf_path, [f"Page {index}" for index in range(1, 42)])
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "assets.json"
    input_path.write_text(
        json.dumps({"paper_id": "paper:test", "title": "Long Coverage Paper", "pdf_path": str(pdf_path)}),
        encoding="utf-8",
    )

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

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["asset_coverage"] == {
        "total_pages": 41,
        "asset_max_pages": 40,
        "asset_pages_scanned": 40,
        "truncated_due_to_asset_page_limit": True,
    }


def test_text_table_row_accepts_explicit_column_separators() -> None:
    assert _looks_like_text_table_row("Method | Strengths | Weaknesses") is True


def test_caption_re_supports_conservative_appendix_labels() -> None:
    assert CAPTION_RE.match("Fig. S1. Supplemental ablation.")
    assert CAPTION_RE.match("Figure A2: Appendix pipeline.")
    assert CAPTION_RE.match("Table S3 Extended results.")


def test_caption_re_supports_extended_scheme_algorithm_labels() -> None:
    assert CAPTION_RE.match("Extended Data Fig. 1. Extra examples.")
    assert CAPTION_RE.match("Extended Data Figure 1. Extra examples.")
    assert CAPTION_RE.match("Extended Data Table 1. Extra results.")
    assert CAPTION_RE.match("Scheme 2. Synthetic route.")
    assert CAPTION_RE.match("Algorithm 1 Training loop.")


def test_caption_re_rejects_caption_like_prose() -> None:
    assert CAPTION_RE.match("Figure out whether the method generalizes.") is None
    assert CAPTION_RE.match("Table stakes for evaluation are high.") is None
    assert CAPTION_RE.match("Figuratively speaking, this is not a caption.") is None


def test_caption_match_rejects_inline_table_reference() -> None:
    text = "Table 8 summarizes the results from this ablation study."
    match = CAPTION_RE.match(text)

    assert match is not None
    assert _caption_match_is_inline_reference(text, match) is True


def test_caption_match_accepts_title_style_caption_without_separator() -> None:
    text = "Figure 1 Model overview"
    match = CAPTION_RE.match(text)

    assert match is not None
    assert _caption_match_is_inline_reference(text, match) is False


def test_caption_match_accepts_punctuated_caption() -> None:
    text = "Table 8. Results from the ablation study."
    match = CAPTION_RE.match(text)

    assert match is not None
    assert _caption_match_is_inline_reference(text, match) is False


def test_caption_re_keeps_ambiguous_forms_out() -> None:
    assert CAPTION_RE.match("Figure 2.1. Hierarchical result.") is None
    assert CAPTION_RE.match("Figure 3(a). Subpanel detail.") is None


def test_supported_table_captions_classify_as_table() -> None:
    assert _classify_caption_kind("Supplementary Table 2") == "table"
    assert _classify_caption_kind("Extended Data Table 1") == "table"
    assert _classify_caption_kind("Supplementary Figure 1") == "figure"
    assert _classify_caption_kind("Extended Data Fig. 1") == "figure"
    assert _classify_caption_kind("Scheme 2") == "figure"
    assert _classify_caption_kind("Algorithm 1") == "figure"


def test_text_table_row_accepts_compact_text_comparison_row() -> None:
    assert _looks_like_text_table_row("BERT strong baseline poor interpretability") is True


def test_text_table_row_rejects_natural_language_sentence() -> None:
    text = "This method improves robustness because it uses a better training objective."

    assert _looks_like_text_table_row(text) is False


def test_row_is_table_like_accepts_single_line_text_table_row() -> None:
    row = {"members": [{"text": "Method | Strengths | Weaknesses"}], "text": "Method | Strengths | Weaknesses"}

    assert _row_is_table_like(row) is True


def test_restrict_row_to_caption_column_removes_opposite_column_cells() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    row = {
        "bbox": (70.0, 80.0, 550.0, 92.0),
        "members": [
            {"bbox": (70.0, 80.0, 210.0, 92.0), "text": "optimizer AdamW"},
            {"bbox": (330.0, 80.0, 410.0, 92.0), "text": "MAE"},
            {"bbox": (440.0, 80.0, 550.0, 92.0), "text": "ViT-H 76.6"},
        ],
        "text": "optimizer AdamW MAE ViT-H 76.6",
    }
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)

    restricted = _restrict_row_to_caption_column(row, (320.0, 120.0, 560.0, 150.0), page_rect)

    assert restricted is not None
    assert restricted["text"] == "MAE ViT-H 76.6"
    assert restricted["bbox"] == (330.0, 80.0, 550.0, 92.0)


def test_restrict_row_to_caption_column_ignores_tiny_midline_overlap() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    row = {
        "bbox": (50.0, 80.0, 530.0, 92.0),
        "members": [
            {"bbox": (50.0, 80.0, 286.0, 92.0), "text": "left-column prose barely touches band"},
            {"bbox": (330.0, 80.0, 410.0, 92.0), "text": "iNat 2017"},
            {"bbox": (440.0, 80.0, 530.0, 92.0), "text": "83.4 [55]"},
        ],
        "text": "left-column prose barely touches band iNat 2017 83.4 [55]",
    }
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)

    restricted = _restrict_row_to_caption_column(row, (308.0, 120.0, 545.0, 150.0), page_rect)

    assert restricted is not None
    assert restricted["text"] == "iNat 2017 83.4 [55]"
    assert restricted["bbox"] == (330.0, 80.0, 530.0, 92.0)


def test_restrict_row_to_caption_column_skips_opposite_column_row() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    row = {
        "bbox": (70.0, 80.0, 240.0, 92.0),
        "members": [
            {"bbox": (70.0, 80.0, 160.0, 92.0), "text": "optimizer"},
            {"bbox": (180.0, 80.0, 240.0, 92.0), "text": "AdamW"},
        ],
        "text": "optimizer AdamW",
    }
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)

    restricted = _restrict_row_to_caption_column(row, (320.0, 120.0, 560.0, 150.0), page_rect)

    assert restricted is None


def test_restrict_row_to_caption_column_skips_near_mid_opposite_row() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    row = {
        "bbox": (50.0, 80.0, 286.0, 92.0),
        "members": [
            {"bbox": (50.0, 80.0, 286.0, 92.0), "text": "left-column prose barely touches band"},
        ],
        "text": "left-column prose barely touches band",
    }
    page_rect = fitz.Rect(0.0, 0.0, 600.0, 800.0)

    restricted = _restrict_row_to_caption_column(row, (308.0, 120.0, 545.0, 150.0), page_rect)

    assert restricted is None


def test_figure_bbox_uses_caption_width_for_narrow_vector_figure() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for figure bbox tests.")
    doc = fitz.open()
    try:
        page = doc.new_page(width=600.0, height=800.0)
        page.draw_rect(fitz.Rect(115.0, 86.0, 175.0, 118.0))
        page.insert_text(
            (86.0, 154.0),
            "Figure 2. Residual learning: a building block.",
            fontsize=10,
        )
        page.insert_textbox(
            fitz.Rect(330.0, 80.0, 555.0, 220.0),
            "ImageNet test set results are described here in a nearby body paragraph.",
            fontsize=11,
        )
        anchor = [item for item in _find_caption_blocks(page) if item["label"] == "Figure 2"][0]

        bbox = _estimate_figure_bbox_above_caption(page, anchor, None, page.rect)

        assert bbox is not None
        assert bbox[0] <= anchor["bbox"][0]
        assert bbox[2] >= anchor["bbox"][2]
        assert bbox[2] < 300.0
    finally:
        doc.close()


def test_figure_bbox_clamps_visual_rects_below_caption() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for figure bbox tests.")
    doc = fitz.open()
    try:
        page = doc.new_page(width=600.0, height=800.0)
        page.draw_rect(fitz.Rect(0.0, -40.0, 600.0, 250.0))
        page.insert_text(
            (86.0, 154.0),
            "Figure 3. Model comparison.",
            fontsize=10,
        )
        anchor = [item for item in _find_caption_blocks(page) if item["label"] == "Figure 3"][0]

        bbox = _estimate_figure_bbox_above_caption(page, anchor, None, page.rect)

        assert bbox is not None
        assert bbox[3] < 190.0
    finally:
        doc.close()


def test_grow_table_region_allows_gap_between_header_and_data_rows() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    page = type("Page", (), {"rect": fitz.Rect(0.0, 0.0, 600.0, 800.0)})()
    caption = {"bbox": (312.0, 74.0, 540.0, 114.0)}
    rows = [
        {
            "bbox": (316.0, 121.0, 534.0, 128.0),
            "members": [{"bbox": (316.0 + i * 40.0, 121.0, 346.0 + i * 40.0, 128.0), "text": str(i)} for i in range(5)],
            "text": "Source Target A B C D",
        },
        {
            "bbox": (316.0, 148.0, 520.0, 155.0),
            "members": [{"bbox": (316.0 + i * 40.0, 148.0, 346.0 + i * 40.0, 155.0), "text": str(i)} for i in range(5)],
            "text": "CREMA-D 91.1 79.9 30.7 25.8",
        },
    ]

    accepted, data_rows = _grow_table_region(
        page,
        caption,
        rows,
        [],
        direction="down",
        upper_bound=0.0,
        lower_bound=400.0,
    )

    assert len(accepted) == 2
    assert data_rows == 2


def test_grow_table_region_stops_at_single_member_prose_after_data() -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for page rect construction.")
    page = type("Page", (), {"rect": fitz.Rect(0.0, 0.0, 600.0, 800.0)})()
    caption = {"bbox": (312.0, 74.0, 540.0, 114.0)}
    rows = [
        {
            "bbox": (316.0, 121.0, 534.0, 128.0),
            "members": [{"bbox": (316.0 + i * 40.0, 121.0, 346.0 + i * 40.0, 128.0), "text": str(i)} for i in range(5)],
            "text": "Source Target A B C D",
        },
        {
            "bbox": (316.0, 132.0, 520.0, 139.0),
            "members": [{"bbox": (316.0 + i * 40.0, 132.0, 346.0 + i * 40.0, 139.0), "text": str(i)} for i in range(5)],
            "text": "CREMA-D 91.1 79.9 30.7 25.8",
        },
        {
            "bbox": (312.0, 150.0, 540.0, 159.0),
            "members": [{"bbox": (312.0, 150.0, 540.0, 159.0), "text": "on CREMA-D, 86.6. The other corpus improves"}],
            "text": "on CREMA-D, 86.6. The other corpus improves",
        },
    ]

    accepted, data_rows = _grow_table_region(
        page,
        caption,
        rows,
        [(312.0, 150.0, 540.0, 220.0, "on CREMA-D, 86.6. The other corpus improves")],
        direction="down",
        upper_bound=0.0,
        lower_bound=400.0,
    )

    assert len(accepted) == 2
    assert data_rows == 2


def test_quality_classification_rejects_table_without_body_rows() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.12,
        visual_rect_count=2,
        visual_body_ratio=0.2,
        paragraph_text_chars=20,
        table_body_rows=0,
        caption_text_chars=80,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "table_body_missing" in signals["quality_reason_codes"]


def test_quality_classification_rejects_caption_only_crop() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.08,
        visual_rect_count=0,
        visual_body_ratio=0.01,
        paragraph_text_chars=0,
        table_body_rows=1,
        caption_text_chars=120,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "caption_only_suspected" in signals["quality_reason_codes"]


def test_quality_classification_accepts_dense_table_text_as_table_body() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.14,
        visual_rect_count=11,
        visual_body_ratio=0.029,
        paragraph_text_chars=1058,
        table_body_rows=22,
        caption_text_chars=80,
    )

    assert signals["visual_quality_status"] == "usable"
    assert "table_text_contamination_suspected" not in signals["quality_reason_codes"]


def test_quality_classification_rejects_weak_table_with_paragraph_text_contamination() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.14,
        visual_rect_count=2,
        visual_body_ratio=0.05,
        paragraph_text_chars=620,
        table_body_rows=1,
        caption_text_chars=30,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "table_text_contamination_suspected" in signals["quality_reason_codes"]


def test_quality_classification_rejects_table_with_dense_prose_contamination() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.09,
        visual_rect_count=0,
        visual_body_ratio=0.0,
        paragraph_text_chars=1074,
        table_body_rows=3,
        caption_text_chars=182,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "table_text_contamination_suspected" in signals["quality_reason_codes"]


def test_quality_classification_accepts_structured_table_with_long_cell_text() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.14,
        visual_rect_count=4,
        visual_body_ratio=0.18,
        paragraph_text_chars=620,
        table_body_rows=6,
        caption_text_chars=80,
    )

    assert signals["visual_quality_status"] == "usable"
    assert "table_text_contamination_suspected" not in signals["quality_reason_codes"]


def test_quality_classification_accepts_clean_wide_table_without_vector_lines() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.09,
        visual_rect_count=0,
        visual_body_ratio=0.0,
        paragraph_text_chars=523,
        table_body_rows=4,
        caption_text_chars=281,
    )

    assert signals["visual_quality_status"] == "usable"
    assert "table_text_contamination_suspected" not in signals["quality_reason_codes"]


def test_quality_classification_rejects_table_covering_other_caption() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.18,
        visual_rect_count=6,
        visual_body_ratio=0.22,
        paragraph_text_chars=40,
        table_body_rows=8,
        caption_text_chars=90,
        other_caption_labels=["Table 8"],
    )

    assert signals["visual_quality_status"] == "reject"
    assert signals["other_caption_labels"] == ["Table 8"]
    assert "multiple_caption_regions_suspected" in signals["quality_reason_codes"]


def test_quality_classification_rejects_figure_covering_other_caption() -> None:
    signals = _classify_visual_quality(
        kind="figure",
        page_coverage_ratio=0.22,
        visual_rect_count=8,
        visual_body_ratio=0.18,
        paragraph_text_chars=40,
        table_body_rows=0,
        caption_text_chars=80,
        other_caption_labels=["Figure 4"],
    )

    assert signals["visual_quality_status"] == "reject"
    assert signals["other_caption_labels"] == ["Figure 4"]
    assert "multiple_caption_regions_suspected" in signals["quality_reason_codes"]


def test_unique_figure_asset_filename_prevents_same_label_overwrite() -> None:
    used: set[str] = set()

    first = _unique_figure_asset_filename(5, "Figure 3", used)
    second = _unique_figure_asset_filename(5, "Figure 3", used)
    third = _unique_figure_asset_filename(5, "Figure 3", used)

    assert first == "page_005_fig_figure_3.png"
    assert second == "page_005_fig_figure_3_2.png"
    assert third == "page_005_fig_figure_3_3.png"
    assert used == {first, second, third}


def test_other_caption_labels_for_crop_detects_substantial_overlap() -> None:
    current = {"label": "Table 7", "bbox": (10.0, 10.0, 80.0, 24.0)}
    other = {"label": "Table 8", "bbox": (12.0, 120.0, 82.0, 136.0)}

    labels = _other_caption_labels_for_crop([current, other], current, (0.0, 0.0, 100.0, 140.0))

    assert labels == ["Table 8"]


def test_other_caption_labels_for_crop_detects_partial_label_line_overlap() -> None:
    current = {"label": "Figure 18", "bbox": (370.0, 190.0, 506.0, 200.0)}
    other = {
        "label": "Figure 16",
        "bbox": (54.0, 200.0, 294.0, 234.0),
        "label_bbox": (54.0, 200.0, 294.0, 210.0),
    }

    labels = _other_caption_labels_for_crop(
        [current, other],
        current,
        (60.0, 67.0, 554.0, 206.5),
    )

    assert labels == ["Figure 16"]


def test_quality_classification_accepts_clean_table_crop() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.16,
        visual_rect_count=5,
        visual_body_ratio=0.16,
        paragraph_text_chars=70,
        table_body_rows=7,
        caption_text_chars=70,
        other_caption_labels=[],
    )

    assert signals["visual_quality_status"] == "usable"
    assert signals["quality_reason_codes"] == []


def test_quality_classification_rejects_large_text_page_crop() -> None:
    signals = _classify_visual_quality(
        kind="figure",
        page_coverage_ratio=0.82,
        visual_rect_count=1,
        visual_body_ratio=0.02,
        paragraph_text_chars=900,
        table_body_rows=0,
        caption_text_chars=50,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "large_text_block_suspected" in signals["quality_reason_codes"]
    assert "oversized_page_crop" in signals["quality_reason_codes"]


def test_quality_classification_accepts_normal_chart_crop() -> None:
    signals = _classify_visual_quality(
        kind="figure",
        page_coverage_ratio=0.24,
        visual_rect_count=6,
        visual_body_ratio=0.28,
        paragraph_text_chars=30,
        table_body_rows=0,
        caption_text_chars=80,
    )

    assert signals["visual_quality_status"] == "usable"
    assert signals["quality_reason_codes"] == []


def test_quality_classification_accepts_visual_dense_figure_with_embedded_text() -> None:
    signals = _classify_visual_quality(
        kind="figure",
        page_coverage_ratio=0.24,
        visual_rect_count=27,
        visual_body_ratio=0.8,
        paragraph_text_chars=760,
        table_body_rows=0,
        caption_text_chars=460,
    )

    assert signals["visual_quality_status"] == "usable"
    assert "large_text_block_suspected" not in signals["quality_reason_codes"]
