from __future__ import annotations

from plan_figures import _normalize_label_for_match, attach_candidate_images


def test_matching_figure_asset_is_candidate_and_keeps_placeholder_mode() -> None:
    items = [
        {
            "id": "Fig. 1",
            "caption": "System overview.",
            "insert_mode": "placeholder",
        }
    ]
    figure_assets = [
        {
            "page_number": 2,
            "label": "Figure 1",
            "filename": "page_002_fig_figure_1.png",
            "path": "/tmp/images/page_002_fig_figure_1.png",
            "width": 640,
            "height": 320,
            "size_bytes": 1200,
            "extraction_level": "figure",
            "quality_signals": {
                "visual_quality_status": "usable",
                "quality_reason_codes": [],
            },
        }
    ]

    planned = attach_candidate_images(
        items,
        page_assets=[
            {
                "page_number": 2,
                "image_count": 0,
                "figure_count": 1,
                "page_text": "Figure 1. System overview.",
            }
        ],
        image_assets=[],
        figure_assets=figure_assets,
    )

    assert planned[0]["insert_mode"] == "placeholder"
    assert planned[0]["figure_asset_candidate"] == {
        "filename": "page_002_fig_figure_1.png",
        "path": "/tmp/images/page_002_fig_figure_1.png",
        "width": 640,
        "height": 320,
        "size_bytes": 1200,
        "label": "Figure 1",
        "extraction_level": "figure",
        "quality_signals": {
            "visual_quality_status": "usable",
            "quality_reason_codes": [],
        },
        "candidate_status": "usable_candidate",
    }


def test_figure_only_page_is_candidate_and_exposes_figure_assets() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Figure 2",
                "caption": "Ablation result.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 4,
                "image_count": 0,
                "figure_count": 1,
                "page_text": "Figure 2. Ablation result.",
            }
        ],
        image_assets=[],
        figure_assets=[
            {
                "page_number": 4,
                "label": "Figure 2",
                "filename": "page_004_fig_figure_2.png",
                "path": "/tmp/images/page_004_fig_figure_2.png",
                "width": 720,
                "height": 360,
                "size_bytes": 2048,
                "extraction_level": "figure",
                "quality_signals": {
                    "visual_quality_status": "reject",
                    "quality_reason_codes": ["caption_only_suspected"],
                },
            }
        ],
    )

    candidate = planned[0]["candidate_pages"][0]
    assert candidate["page_number"] == 4
    assert candidate["images"] == []
    assert candidate["figure_assets"] == [
        {
            "filename": "page_004_fig_figure_2.png",
            "path": "/tmp/images/page_004_fig_figure_2.png",
            "width": 720,
            "height": 360,
            "size_bytes": 2048,
            "label": "Figure 2",
            "extraction_level": "figure",
            "quality_signals": {
                "visual_quality_status": "reject",
                "quality_reason_codes": ["caption_only_suspected"],
            },
            "candidate_status": "reject_visual_quality",
        }
    ]


def test_label_normalization_matches_common_figure_spellings() -> None:
    assert _normalize_label_for_match("Fig. 1") == "fig 1"
    assert _normalize_label_for_match("Figure 1") == "fig 1"
    assert _normalize_label_for_match("Figure. 1") == "fig 1"


def test_legacy_image_assets_still_populate_candidate_page_images() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Figure 3",
                "caption": "Training setup.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 5,
                "image_count": 1,
                "figure_count": 0,
                "page_text": "Figure 3. Training setup.",
            }
        ],
        image_assets=[
            {
                "page_number": 5,
                "filename": "page_005_img_001.png",
                "path": "/tmp/images/page_005_img_001.png",
                "width": 400,
                "height": 300,
                "size_bytes": 1024,
            }
        ],
        figure_assets=[],
    )

    assert planned[0]["candidate_pages"][0]["images"] == [
        {
            "filename": "page_005_img_001.png",
            "path": "/tmp/images/page_005_img_001.png",
            "width": 400,
            "height": 300,
            "size_bytes": 1024,
        }
    ]


def test_missing_quality_signals_need_visual_check_and_keep_placeholder_mode() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Figure 4",
                "caption": "Overview.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 6,
                "image_count": 0,
                "figure_count": 1,
                "page_text": "Figure 4. Overview.",
            }
        ],
        image_assets=[],
        figure_assets=[
            {
                "page_number": 6,
                "label": "Figure 4",
                "filename": "page_006_fig_figure_4.png",
                "path": "/tmp/images/page_006_fig_figure_4.png",
                "width": 640,
                "height": 320,
                "size_bytes": 1200,
                "extraction_level": "figure",
            }
        ],
    )

    assert planned[0]["insert_mode"] == "placeholder"
    assert planned[0]["figure_asset_candidate"]["candidate_status"] == "needs_visual_quality_check"
    assert planned[0]["candidate_pages"][0]["figure_assets"][0]["candidate_status"] == "needs_visual_quality_check"
