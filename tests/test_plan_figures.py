from __future__ import annotations

from plan_figures import _normalize_label_for_match, attach_candidate_images, build_figure_items


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


def test_other_caption_label_does_not_promote_combined_crop_to_candidate() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Figure 4",
                "caption": "vLLM system overview.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 5,
                "image_count": 0,
                "figure_count": 1,
                "page_text": "The architecture of vLLM is shown in Fig. 4. Figure 4. vLLM system overview. Figure 5. PagedAttention algorithm.",
            }
        ],
        image_assets=[],
        figure_assets=[
            {
                "page_number": 5,
                "label": "Figure 5",
                "filename": "page_005_fig_figure_5.png",
                "path": "/tmp/images/page_005_fig_figure_5.png",
                "width": 1311,
                "height": 397,
                "size_bytes": 79035,
                "extraction_level": "figure",
                "quality_signals": {
                    "visual_quality_status": "usable",
                    "quality_reason_codes": [],
                    "other_caption_labels": ["Figure 4"],
                },
            }
        ],
    )

    assert "figure_asset_candidate" not in planned[0]
    assert planned[0]["candidate_pages"][0]["figure_assets"][0]["label"] == "Figure 5"


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


def test_benchmark_task_and_collection_figures_are_prioritized() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 1",
                    "caption": "A SWE-bench task instance with issue, repository and tests.",
                },
                {
                    "id": "Figure 2",
                    "caption": "Collection procedure for benchmark task instances.",
                },
            ],
            "table_captions": [],
        },
        limit=0,
    )

    by_id = {item["id"]: item for item in items}
    assert by_id["Figure 1"]["kind"] == "data_or_task_overview"
    assert by_id["Figure 1"]["priority"] == 2
    assert by_id["Figure 2"]["kind"] == "method_overview"
    assert by_id["Figure 2"]["priority"] == 1


def test_system_result_figure_is_prioritized_even_with_dataset_word() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 12",
                    "caption": "Single sequence generation with OPT models on the ShareGPT and Alpaca dataset.",
                }
            ],
            "table_captions": [],
        },
        limit=0,
    )

    assert items[0]["kind"] == "main_result"
    assert items[0]["section"] == "关键结果"
    assert items[0]["priority"] == 2


def test_parallel_generation_result_figure_is_prioritized() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 14",
                    "caption": "Parallel generation and beam search with OPT-13B on the Alpaca dataset.",
                }
            ],
            "table_captions": [],
        },
        limit=0,
    )

    assert items[0]["kind"] == "main_result"
    assert items[0]["section"] == "关键结果"
    assert items[0]["priority"] == 2


def test_result_claim_with_architecture_word_stays_result() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 8",
                    "caption": "The full generative agent architecture produces",
                }
            ],
            "table_captions": [],
        },
        limit=0,
    )

    assert items[0]["kind"] == "main_result"
    assert items[0]["section"] == "关键结果"
    assert items[0]["priority"] == 2


def test_prisma_flow_diagram_is_data_overview() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 1",
                    "caption": "PRISMA literature flow diagram.",
                }
            ],
            "table_captions": [],
        },
        limit=0,
    )

    assert items[0]["kind"] == "data_or_task_overview"
    assert items[0]["section"] == "数据与任务定义"
    assert items[0]["priority"] == 2


def test_method_detail_figures_are_kept_as_method_placeholders() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 5",
                    "caption": "Illustration of the PagedAttention algorithm.",
                },
                {
                    "id": "Figure 6",
                    "caption": "Block table translation in vLLM.",
                },
            ],
            "table_captions": [],
        },
        limit=0,
    )

    by_id = {item["id"]: item for item in items}
    assert by_id["Figure 5"]["kind"] == "method_detail"
    assert by_id["Figure 5"]["section"] == "方法主线"
    assert by_id["Figure 5"]["priority"] == 2
    assert by_id["Figure 6"]["kind"] == "method_detail"
    assert by_id["Figure 6"]["section"] == "方法主线"
    assert by_id["Figure 6"]["priority"] == 2


def test_figure_and_fig_caption_variants_are_deduped_in_plan() -> None:
    items = build_figure_items(
        {
            "figure_captions": [
                {
                    "id": "Figure 14",
                    "caption": "Parallel generation and beam search with OPT-13B on the Alpaca dataset.",
                },
                {
                    "id": "Fig 14",
                    "caption": "shows the results for beam search with different beam widths.",
                },
            ],
            "table_captions": [],
        },
        limit=0,
    )

    assert len(items) == 1
    assert items[0]["id"] == "Figure 14"
    assert items[0]["caption"].startswith("Parallel generation")


def test_limit_keeps_high_priority_result_figures_beyond_supporting_cap() -> None:
    support = [
        {"id": f"Figure {idx}", "caption": f"Auxiliary illustration {idx}."}
        for idx in range(1, 8)
    ]
    items = build_figure_items(
        {
            "figure_captions": support
            + [
                {
                    "id": "Figure 13",
                    "caption": "Average number of batched requests when serving OPT-13B traces.",
                }
            ],
            "table_captions": [],
        },
        limit=3,
    )

    ids = {item["id"] for item in items}
    assert "Figure 13" in ids
    assert len(items) == 3


def test_label_normalization_matches_appendix_figure_spellings() -> None:
    assert _normalize_label_for_match("Fig. S1") == "fig s1"
    assert _normalize_label_for_match("Figure A2") == "fig a2"
    assert _normalize_label_for_match("Table S3") == "table s3"


def test_label_normalization_matches_extended_scheme_algorithm_spellings() -> None:
    assert _normalize_label_for_match("Extended Data Fig. 1") == "extended data fig 1"
    assert _normalize_label_for_match("Extended Data Figure 1") == "extended data fig 1"
    assert _normalize_label_for_match("Extended Data Table 1") == "extended data table 1"
    assert _normalize_label_for_match("Scheme 2") == "scheme 2"
    assert _normalize_label_for_match("Algorithm 1") == "algorithm 1"


def test_extended_data_figure_asset_matches_figure_spelling() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Extended Data Figure 1",
                "caption": "Extra examples.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 8,
                "image_count": 0,
                "figure_count": 1,
                "page_text": "Extended Data Fig. 1. Extra examples.",
            }
        ],
        image_assets=[],
        figure_assets=[
            {
                "page_number": 8,
                "label": "Extended Data Fig. 1",
                "filename": "page_008_fig_extended_data_fig_1.png",
                "path": "/tmp/images/page_008_fig_extended_data_fig_1.png",
                "width": 640,
                "height": 320,
                "size_bytes": 1200,
                "extraction_level": "figure",
            }
        ],
    )

    assert planned[0]["figure_asset_candidate"]["label"] == "Extended Data Fig. 1"
    assert planned[0]["candidate_pages"][0]["page_number"] == 8


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


def test_no_match_does_not_fall_back_to_page_order() -> None:
    planned = attach_candidate_images(
        [
            {
                "id": "Figure 9",
                "caption": "Completely unrelated caption.",
                "insert_mode": "placeholder",
            }
        ],
        page_assets=[
            {
                "page_number": 7,
                "image_count": 1,
                "figure_count": 0,
                "page_text": "This page discusses assumptions and baseline setup details.",
                "text_preview": "This page discusses assumptions and baseline setup details.",
            }
        ],
        image_assets=[
            {
                "page_number": 7,
                "filename": "page_007_img_001.png",
                "path": "/tmp/images/page_007_img_001.png",
                "width": 400,
                "height": 300,
                "size_bytes": 1024,
            }
        ],
        figure_assets=[],
    )

    assert planned[0]["insert_mode"] == "placeholder"
    assert planned[0]["candidate_pages"] == []
    assert planned[0]["candidate_status"] == "no_match_found"
    assert planned[0]["matching_strategy"] == "no-match-found"


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
