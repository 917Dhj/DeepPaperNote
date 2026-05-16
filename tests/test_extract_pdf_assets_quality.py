from __future__ import annotations

from extract_pdf_assets import _classify_visual_quality, _other_caption_labels_for_crop


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


def test_quality_classification_rejects_table_with_paragraph_text_contamination() -> None:
    signals = _classify_visual_quality(
        kind="table",
        page_coverage_ratio=0.14,
        visual_rect_count=4,
        visual_body_ratio=0.18,
        paragraph_text_chars=620,
        table_body_rows=6,
        caption_text_chars=80,
    )

    assert signals["visual_quality_status"] == "reject"
    assert "table_text_contamination_suspected" in signals["quality_reason_codes"]


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


def test_other_caption_labels_for_crop_detects_substantial_overlap() -> None:
    current = {"label": "Table 7", "bbox": (10.0, 10.0, 80.0, 24.0)}
    other = {"label": "Table 8", "bbox": (12.0, 120.0, 82.0, 136.0)}

    labels = _other_caption_labels_for_crop([current, other], current, (0.0, 0.0, 100.0, 140.0))

    assert labels == ["Table 8"]


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
