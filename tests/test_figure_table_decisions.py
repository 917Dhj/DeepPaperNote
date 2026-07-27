from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "plan_figure_table_decisions.py"


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def write_raw_sections(path: Path) -> Path:
    record = {
        "section_id": "sec:method",
        "title": "Method",
        "page_start": 1,
        "page_end": 3,
        "text": "Figure 1. Overview.\n\nTable 1. Main results.",
    }
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_decisions(
    tmp_path: Path,
    source_manifest: dict,
    figures: dict,
    assets: dict | None = None,
) -> dict:
    source_path = write_json(tmp_path / "source_manifest.json", source_manifest)
    figures_path = write_json(tmp_path / "figures.json", figures)
    output_path = tmp_path / "figure_table_decisions.json"
    command = [
            sys.executable,
            str(DECISIONS_SCRIPT),
            "--source-manifest",
            str(source_path),
            "--figures",
            str(figures_path),
            "--output",
            str(output_path),
        ]
    if assets is not None:
        assets_path = write_json(tmp_path / "assets.json", assets)
        command.extend(["--assets", str(assets_path)])
    subprocess.run(command, check=True)
    return json.loads(output_path.read_text(encoding="utf-8"))


def run_review_decisions(
    tmp_path: Path,
    decisions: dict,
    *,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    decisions_path = write_json(tmp_path / "review_decisions.json", decisions)
    output_path = tmp_path / "reviewed_decisions.json"
    result = subprocess.run(
        [
            sys.executable,
            str(DECISIONS_SCRIPT),
            "--review-decisions",
            str(decisions_path),
            "--output",
            str(output_path),
        ],
        check=check,
        capture_output=True,
        text=True,
    )
    payload = (
        json.loads(output_path.read_text(encoding="utf-8"))
        if output_path.is_file()
        else None
    )
    return result, payload


def test_figure_table_decisions_cover_every_caption(tmp_path: Path) -> None:
    source_manifest = {
        "paper_id": "paper:figures",
        "captions": {
            "figures": [
                {"id": "Figure 1", "caption": "Overview", "page": 3, "section_id": "sec:method"},
                {
                    "id": "Figure 2",
                    "caption": "Extra analysis",
                    "page": 8,
                    "section_id": "sec:analysis",
                },
            ],
            "tables": [
                {
                    "id": "Table 1",
                    "caption": "Main results",
                    "page": 7,
                    "section_id": "sec:experiment",
                }
            ],
        },
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 1",
                    "kind": "method_overview",
                    "section": "方法主线",
                    "reason": "method overview",
                    "priority": 1,
                    "figure_asset_candidate": {"candidate_status": "usable_candidate"},
                },
                {
                    "id": "Table 1",
                    "section": "关键结果",
                    "reason": "main result table",
                    "priority": 2,
                },
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decisions = {item["source_id"]: item for item in payload["decisions"]}

    assert set(decisions) == {"Figure 1", "Figure 2", "Table 1"}
    assert decisions["Figure 1"]["decision"] == "placeholder"
    assert decisions["Figure 1"]["target_section"] == "方法主线"
    assert decisions["Table 1"]["decision"] == "placeholder"
    assert decisions["Figure 2"]["decision"] == "low_priority"
    assert payload["summary"]["total_items"] == 3


def test_figure_table_decisions_cover_source_corpus_captions(tmp_path: Path) -> None:
    write_raw_sections(tmp_path / "raw_sections.jsonl")
    source_manifest = {
        "paper_id": "paper:source-corpus-figures",
        "raw_sections_path": "raw_sections.jsonl",
        "coverage": {"total_pages": 3},
        "sections": [
            {
                "section_id": "sec:method",
                "title": "Method",
                "page_start": 1,
                "page_end": 3,
            }
        ],
        "pages": [{"page": 1, "section_ids": ["sec:method"]}],
        "captions": {
            "figures": [
                {"id": "Figure 1", "caption": "Overview", "page": 1, "section_id": "sec:method"}
            ],
            "tables": [
                {"id": "Table 1", "caption": "Main results", "page": 2, "section_id": "sec:method"}
            ],
        },
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Fig. 1",
                    "kind": "method_overview",
                    "section": "方法主线",
                    "reason": "method overview",
                    "priority": 1,
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decisions = {item["source_id"]: item for item in payload["decisions"]}

    assert set(decisions) == {"Figure 1", "Table 1"}
    assert decisions["Figure 1"]["target_section"] == "方法主线"
    assert decisions["Table 1"]["decision"] == "low_priority"
    assert decisions["Table 1"]["reason"] == "caption_detected_but_not_selected_by_figure_plan"


def test_figure_table_decisions_fail_closed_on_visual_defect(tmp_path: Path) -> None:
    source_manifest = {
        "captions": {
            "figures": [{"id": "Fig. 3", "caption": "Architecture", "page": 4}],
            "tables": [],
        }
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 3",
                    "section": "方法主线",
                    "priority": 1,
                    "figure_asset_candidate": {"candidate_status": "reject_visual_quality"},
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "visual_defect"
    assert decision["skip_reason"] == "visual_quality_gate_rejected_candidate"


def test_figure_table_decisions_require_visual_review_for_usable_candidate(
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "page_002_fig_figure_1.png"
    source_image.write_bytes(b"candidate-image")
    source_manifest = {
        "paper_id": "paper:figures",
        "captions": {
            "figures": [
                {
                    "id": "Figure 1",
                    "caption": "System overview",
                    "page": 2,
                    "section_id": "sec:method",
                }
            ],
            "tables": [],
        },
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 1",
                    "kind": "method_overview",
                    "section": "方法主线",
                    "reason": "system overview",
                    "priority": 1,
                    "figure_asset_candidate": {
                        "filename": "page_002_fig_figure_1.png",
                        "path": str(source_image),
                        "candidate_status": "usable_candidate",
                        "quality_signals": {"visual_quality_status": "usable"},
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "review_pending"
    assert decision["source_image_sha256"] == hashlib.sha256(b"candidate-image").hexdigest()
    assert decision["visual_review"]["status"] == "pending"
    assert decision["visual_review"]["reviewed_asset_sha256"] == ""
    assert payload["summary"]["by_decision"]["review_pending"] == 1


def test_figure_table_decisions_rerender_selected_candidate_at_300_dpi(
    tmp_path: Path,
) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for selected-candidate rendering.")
    pdf_path = tmp_path / "paper.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=200.0, height=300.0)
        page.draw_rect(fitz.Rect(20.0, 30.0, 180.0, 130.0), width=2.0)
        doc.save(pdf_path)
    finally:
        doc.close()

    preview_path = tmp_path / "page_001.png"
    preview_path.write_bytes(b"page-preview")
    low_res_path = tmp_path / "page_001_fig_figure_1.png"
    low_res_path.write_bytes(b"low-res-candidate")
    source_manifest = {
        "captions": {
            "figures": [{"id": "Figure 1", "caption": "Architecture", "page": 1}],
            "tables": [],
        }
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 1",
                    "kind": "method_overview",
                    "section": "方法主线",
                    "priority": 1,
                    "figure_asset_candidate": {
                        "filename": low_res_path.name,
                        "path": str(low_res_path),
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }
    assets = {
        "pdf_path": str(pdf_path),
        "figure_assets": [
            {
                "label": "Figure 1",
                "page_number": 1,
                "bbox_pt": [20.0, 30.0, 180.0, 130.0],
                "path": str(low_res_path),
                "page_preview_path": str(preview_path),
            }
        ],
    }

    payload = run_decisions(tmp_path, source_manifest, figures, assets)
    decision = payload["decisions"][0]
    reviewed_path = Path(decision["source_image_path"])

    assert reviewed_path.name == "page_001_fig_figure_1_review.png"
    assert reviewed_path.is_file()
    pixmap = fitz.Pixmap(str(reviewed_path))
    assert pixmap.width == 667
    assert pixmap.height == 417
    assert decision["review_evidence"] == {
        "candidate_path": str(reviewed_path),
        "page_preview_path": str(preview_path),
        "source_pdf_path": str(pdf_path),
        "source_page": 1,
        "caption": "Architecture",
        "bbox_pt": [20.0, 30.0, 180.0, 130.0],
        "normalized_bbox": [0.1, 0.1, 0.9, 0.433333],
        "render_dpi": 300,
    }


def test_figure_table_decisions_apply_one_normalized_bbox_repair(
    tmp_path: Path,
) -> None:
    if fitz is None:
        pytest.skip("PyMuPDF is required for bounded crop repair.")
    pdf_path = tmp_path / "paper.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=200.0, height=400.0)
        page.draw_rect(fitz.Rect(20.0, 80.0, 180.0, 240.0), width=2.0)
        doc.save(pdf_path)
    finally:
        doc.close()
    source_image = tmp_path / "candidate.png"
    source_image.write_bytes(b"caption-contaminated")
    digest = hashlib.sha256(b"caption-contaminated").hexdigest()
    decisions = {
        "status": "ok",
        "decisions": [
            {
                "source_id": "Figure 1",
                "kind": "figure",
                "decision": "review_pending",
                "source_image_path": str(source_image),
                "source_image_filename": source_image.name,
                "source_image_sha256": digest,
                "review_evidence": {
                    "candidate_path": str(source_image),
                    "page_preview_path": str(tmp_path / "page.png"),
                    "source_pdf_path": str(pdf_path),
                    "source_page": 1,
                    "caption": "Architecture",
                    "bbox_pt": [0.0, 0.0, 200.0, 300.0],
                    "normalized_bbox": [0.0, 0.0, 1.0, 0.75],
                    "render_dpi": 300,
                },
                "visual_review": {
                    "status": "repair_requested",
                    "reviewed_asset_sha256": digest,
                    "preserved_scientific_elements": ["diagram"],
                    "omitted_scientific_elements": [],
                    "notes": "Remove external caption below the diagram.",
                    "failure_reason": "caption_contamination",
                    "repair_attempts": 0,
                    "revised_bbox": [0.1, 0.2, 0.9, 0.6],
                },
            }
        ],
    }

    _, payload = run_review_decisions(tmp_path, decisions)
    assert payload is not None
    decision = payload["decisions"][0]
    repair_path = Path(decision["source_image_path"])

    assert repair_path.name == "candidate_repair1.png"
    assert repair_path.is_file()
    pixmap = fitz.Pixmap(str(repair_path))
    assert pixmap.width == 667
    assert pixmap.height == 667
    assert decision["decision"] == "review_pending"
    assert decision["visual_review"]["status"] == "pending"
    assert decision["visual_review"]["repair_attempts"] == 1
    assert decision["visual_review"]["revised_bbox"] == [0.1, 0.2, 0.9, 0.6]
    assert decision["review_evidence"]["bbox_pt"] == [20.0, 80.0, 180.0, 240.0]
    assert decision["source_image_sha256"] == hashlib.sha256(
        repair_path.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    "bbox",
    (
        [],
        [-0.1, 0.1, 0.8, 0.8],
        [0.1, 0.1, 1.1, 0.8],
        [0.8, 0.1, 0.2, 0.8],
        [0.1, 0.8, 0.8, 0.2],
    ),
)
def test_figure_table_decisions_reject_invalid_normalized_bbox(
    tmp_path: Path,
    bbox: list[float],
) -> None:
    source_image = tmp_path / "candidate.png"
    source_image.write_bytes(b"candidate")
    digest = hashlib.sha256(b"candidate").hexdigest()
    decisions = {
        "decisions": [
            {
                "decision": "review_pending",
                "source_image_path": str(source_image),
                "source_image_sha256": digest,
                "visual_review": {
                    "status": "repair_requested",
                    "reviewed_asset_sha256": digest,
                    "preserved_scientific_elements": [],
                    "omitted_scientific_elements": [],
                    "notes": "",
                    "failure_reason": "caption_contamination",
                    "repair_attempts": 0,
                    "revised_bbox": bbox,
                },
            }
        ]
    }

    result, payload = run_review_decisions(tmp_path, decisions, check=False)

    assert result.returncode != 0
    assert payload is None
    assert "revised_bbox" in result.stderr


def test_figure_table_decisions_fail_closed_after_repair_limit(
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "candidate_repair1.png"
    source_image.write_bytes(b"still-contaminated")
    digest = hashlib.sha256(b"still-contaminated").hexdigest()
    decisions = {
        "decisions": [
            {
                "source_id": "Figure 1",
                "decision": "review_pending",
                "source_image_path": str(source_image),
                "source_image_sha256": digest,
                "visual_review": {
                    "status": "repair_requested",
                    "reviewed_asset_sha256": digest,
                    "preserved_scientific_elements": ["diagram"],
                    "omitted_scientific_elements": [],
                    "notes": "Caption remains after the first repair.",
                    "failure_reason": "caption_contamination",
                    "repair_attempts": 1,
                    "revised_bbox": [0.1, 0.1, 0.9, 0.7],
                },
            }
        ]
    }

    _, payload = run_review_decisions(tmp_path, decisions)
    assert payload is not None
    decision = payload["decisions"][0]

    assert decision["decision"] == "visual_defect"
    assert decision["skip_reason"] == "repair_limit_exhausted"
    assert decision["visual_review"]["status"] == "fail"
    assert decision["visual_review"]["failure_reason"] == "repair_limit_exhausted"


def test_figure_table_decisions_dedupe_figure_and_fig_variants(tmp_path: Path) -> None:
    source_image = tmp_path / "page_011_fig_figure_14.png"
    source_image.write_bytes(b"figure-14")
    source_manifest = {
        "paper_id": "paper:figures",
        "captions": {
            "figures": [
                {
                    "id": "Figure 14",
                    "caption": "Parallel generation and beam search with OPT-13B on the Alpaca dataset.",
                    "page": 11,
                    "section_id": "sec:experiment",
                },
                {
                    "id": "Fig 14",
                    "caption": "shows the results for beam search with different beam widths.",
                    "page": 11,
                    "section_id": "sec:experiment",
                },
            ],
            "tables": [],
        },
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 14",
                    "kind": "main_result",
                    "section": "关键结果",
                    "reason": "main result",
                    "priority": 2,
                    "figure_asset_candidate": {
                        "filename": "page_011_fig_figure_14.png",
                        "path": str(source_image),
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)

    assert payload["summary"]["total_items"] == 1
    assert payload["decisions"][0]["source_id"] == "Figure 14"
    assert payload["decisions"][0]["decision"] == "review_pending"


def test_figure_table_decisions_insert_selected_usable_figure_regardless_priority(
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "page_002_fig_figure_1.png"
    source_image.write_bytes(b"figure-1")
    source_manifest = {
        "captions": {
            "figures": [{"id": "Figure 1", "caption": "Auxiliary distribution", "page": 2}],
            "tables": [],
        }
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 1",
                    "kind": "data_or_task",
                    "section": "数据与任务定义",
                    "priority": 3,
                    "figure_asset_candidate": {
                        "filename": "page_002_fig_figure_1.png",
                        "path": str(source_image),
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "review_pending"
    assert decision["plan_kind"] == "data_or_task"


def test_figure_table_decisions_insert_selected_usable_tables(tmp_path: Path) -> None:
    source_image = tmp_path / "page_005_fig_table_2.png"
    source_image.write_bytes(b"table-2")
    source_manifest = {
        "captions": {
            "figures": [],
            "tables": [{"id": "Table 2", "caption": "Main results", "page": 5}],
        }
    }
    figures = {
        "figure_plan": {
            "figures": [
                {
                    "id": "Table 2",
                    "section": "关键结果",
                    "priority": 1,
                    "figure_asset_candidate": {
                        "filename": "page_005_fig_table_2.png",
                        "path": str(source_image),
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "review_pending"
    assert decision["skip_reason"] == ""
