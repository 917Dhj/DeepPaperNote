from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DECISIONS_SCRIPT = PROJECT_ROOT / "scripts" / "plan_figure_table_decisions.py"


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def run_decisions(tmp_path: Path, source_manifest: dict, figures: dict) -> dict:
    source_path = write_json(tmp_path / "source_manifest.json", source_manifest)
    figures_path = write_json(tmp_path / "figures.json", figures)
    output_path = tmp_path / "figure_table_decisions.json"
    subprocess.run(
        [
            sys.executable,
            str(DECISIONS_SCRIPT),
            "--source-manifest",
            str(source_path),
            "--figures",
            str(figures_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


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


def test_figure_table_decisions_insert_usable_candidate(tmp_path: Path) -> None:
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
                        "path": "/tmp/images/page_002_fig_figure_1.png",
                        "candidate_status": "usable_candidate",
                        "quality_signals": {"visual_quality_status": "usable"},
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "insert"
    assert payload["summary"]["by_decision"]["insert"] == 1


def test_figure_table_decisions_dedupe_figure_and_fig_variants(tmp_path: Path) -> None:
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
                        "path": "/tmp/images/page_011_fig_figure_14.png",
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)

    assert payload["summary"]["total_items"] == 1
    assert payload["decisions"][0]["source_id"] == "Figure 14"
    assert payload["decisions"][0]["decision"] == "insert"


def test_figure_table_decisions_insert_selected_usable_figure_regardless_priority(
    tmp_path: Path,
) -> None:
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
                        "path": "/tmp/images/page_002_fig_figure_1.png",
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "insert"
    assert decision["plan_kind"] == "data_or_task"


def test_figure_table_decisions_insert_selected_usable_tables(tmp_path: Path) -> None:
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
                        "path": "/tmp/images/page_005_fig_table_2.png",
                        "candidate_status": "usable_candidate",
                    },
                }
            ]
        }
    }

    payload = run_decisions(tmp_path, source_manifest, figures)
    decision = payload["decisions"][0]

    assert decision["decision"] == "insert"
    assert decision["skip_reason"] == ""
