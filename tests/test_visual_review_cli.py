from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import run_pipeline
from lint_grounding import validate_figure_decisions

fitz = pytest.importorskip("fitz")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"
DECISIONS_SCRIPT = SCRIPTS_DIR / "plan_figure_table_decisions.py"
EXTRACT_SCRIPT = SCRIPTS_DIR / "extract_pdf_assets.py"


def write_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        for _ in range(3):
            page = doc.new_page(width=200.0, height=400.0)
            page.draw_rect(fitz.Rect(20.0, 80.0, 180.0, 240.0), width=2.0)
        doc.save(path)
    finally:
        doc.close()


def source_manifest() -> dict:
    return {
        "paper_id": "paper:review",
        "captions": {
            "figures": [
                {"id": "Figure 1", "caption": "Architecture", "page": 1},
                {"id": "Figure 2", "caption": "Main result", "page": 2},
            ],
            "tables": [
                {"id": "Table 1", "caption": "Scores", "page": 2},
                {"id": "Table 2", "caption": "Ablation", "page": 3},
            ],
        },
    }


def crop(path: Path, payload: bytes) -> str:
    path.write_bytes(payload)
    return str(path)


def asset(tmp_path: Path, label: str, page: int, status: str, preview: Path) -> dict:
    name = f"page_{page:03d}_fig_{label.lower().replace(' ', '_')}.png"
    return {
        "label": label,
        "page_number": page,
        "bbox_pt": [20.0, 80.0, 180.0, 240.0],
        "path": crop(tmp_path / name, label.encode()),
        "filename": name,
        "page_preview_path": str(preview),
        "quality_signals": {"visual_quality_status": status},
    }


@pytest.fixture
def run(tmp_path: Path) -> dict[str, Path]:
    """Plan a run: Figure 1 selected, Figure 2 unselected, Table 1 no crop, Table 2 rejected."""
    pdf_path = tmp_path / "paper.pdf"
    write_pdf(pdf_path)
    previews = []
    for number in (1, 2, 3):
        preview = tmp_path / f"page_{number:03d}.png"
        preview.write_bytes(b"page-preview")
        previews.append(preview)
    figure_1 = asset(tmp_path, "Figure 1", 1, "usable", previews[0])
    assets = {
        "pdf_path": str(pdf_path),
        "images_dir": str(tmp_path),
        "page_assets": [
            {"page_number": number + 1, "page_preview_path": str(preview)}
            for number, preview in enumerate(previews)
        ],
        "figure_assets": [
            figure_1,
            asset(tmp_path, "Figure 2", 2, "usable", previews[1]),
            asset(tmp_path, "Table 2", 3, "reject", previews[2]),
        ],
    }
    figures = {
        "output_language": "zh-CN",
        "figure_plan": {
            "figures": [
                {
                    "id": "Figure 1",
                    "section": "方法主线",
                    "priority": 1,
                    "figure_asset_candidate": {
                        "filename": figure_1["filename"],
                        "path": figure_1["path"],
                        "candidate_status": "usable_candidate",
                    },
                },
                {
                    "id": "Table 2",
                    "section": "关键结果",
                    "priority": 2,
                    "figure_asset_candidate": {
                        "filename": "page_003_fig_table_2.png",
                        "path": str(tmp_path / "page_003_fig_table_2.png"),
                        "candidate_status": "reject_visual_quality",
                    },
                },
            ]
        },
    }
    paths = {
        "source": tmp_path / "source_manifest.json",
        "figures": tmp_path / "figures.json",
        "assets": tmp_path / "assets.json",
        "decisions": tmp_path / "decisions.json",
    }
    paths["source"].write_text(json.dumps(source_manifest()), encoding="utf-8")
    paths["figures"].write_text(json.dumps(figures), encoding="utf-8")
    paths["assets"].write_text(json.dumps(assets), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(DECISIONS_SCRIPT),
            "--source-manifest",
            str(paths["source"]),
            "--figures",
            str(paths["figures"]),
            "--assets",
            str(paths["assets"]),
            "--output",
            str(paths["decisions"]),
        ],
        check=True,
    )
    return paths


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DECISIONS_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def review(run: dict[str, Path], item: str, *args: str) -> subprocess.CompletedProcess[str]:
    return cli("review", "--decisions", str(run["decisions"]), "--item", item, *args)


def promote(run: dict[str, Path], item: str, *args: str) -> subprocess.CompletedProcess[str]:
    return cli(
        "promote",
        "--decisions",
        str(run["decisions"]),
        "--assets",
        str(run["assets"]),
        "--item",
        item,
        *args,
    )


def load(run: dict[str, Path]) -> dict:
    return json.loads(run["decisions"].read_text(encoding="utf-8"))


def entry(run: dict[str, Path], label: str) -> dict:
    return next(item for item in load(run)["decisions"] if item["source_id"] == label)


def gate_codes(run: dict[str, Path], label: str) -> list[str]:
    return [
        issue["code"]
        for issue in validate_figure_decisions(source_manifest(), load(run))
        if issue.get("source_id") == label
    ]


def test_pass_records_the_script_computed_hash_and_clears_the_gate(
    run: dict[str, Path],
) -> None:
    assert gate_codes(run, "Figure 1") == ["figure_visual_review_unresolved"]

    result = review(
        run, "Figure 1", "--verdict", "pass", "--preserved", "axes", "--preserved", "legend"
    )

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "insert"
    assert item["skip_reason"] == ""
    digest = hashlib.sha256(Path(item["source_image_path"]).read_bytes()).hexdigest()
    assert item["visual_review"]["status"] == "pass"
    assert item["visual_review"]["reviewed_asset_sha256"] == digest
    assert item["visual_review"]["preserved_scientific_elements"] == ["axes", "legend"]
    assert gate_codes(run, "Figure 1") == []
    assert load(run)["summary"]["by_decision"]["insert"] == 1
    assert load(run)["summary"]["by_decision"]["review_pending"] == 0


def test_item_lookup_accepts_label_variants(run: dict[str, Path]) -> None:
    result = review(run, "Fig. 1", "--verdict", "pass", "--preserved", "diagram")

    assert result.returncode == 0, result.stderr
    assert entry(run, "Figure 1")["decision"] == "insert"


def test_pass_requires_recorded_scientific_elements(run: dict[str, Path]) -> None:
    before = run["decisions"].read_bytes()

    result = review(run, "Figure 1", "--verdict", "pass")

    assert result.returncode != 0
    assert "--preserved" in result.stderr
    assert run["decisions"].read_bytes() == before


def test_review_refuses_a_candidate_changed_since_planning(run: dict[str, Path]) -> None:
    Path(entry(run, "Figure 1")["source_image_path"]).write_bytes(b"swapped")
    before = run["decisions"].read_bytes()

    result = review(run, "Figure 1", "--verdict", "pass", "--preserved", "diagram")

    assert result.returncode != 0
    assert "changed" in result.stderr
    assert run["decisions"].read_bytes() == before


def test_review_is_only_for_items_in_review(run: dict[str, Path]) -> None:
    result = review(run, "Figure 2", "--verdict", "pass", "--preserved", "diagram")

    assert result.returncode != 0
    assert "promote" in result.stderr


def test_unknown_item_is_refused(run: dict[str, Path]) -> None:
    result = review(run, "Figure 99", "--verdict", "pass", "--preserved", "diagram")

    assert result.returncode != 0
    assert "Figure 99" in result.stderr


def test_terminal_failure_records_a_visual_defect_the_gate_accepts(
    run: dict[str, Path],
) -> None:
    result = review(
        run,
        "Figure 1",
        "--verdict",
        "fail",
        "--failure",
        "identity_mismatch",
        "--notes",
        "Shows Figure 3 instead.",
    )

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "visual_defect"
    assert item["skip_reason"] == "identity_mismatch"
    assert item["visual_review"]["failure_reason"] == "identity_mismatch"
    assert item["visual_review"]["notes"] == "Shows Figure 3 instead."
    assert gate_codes(run, "Figure 1") == []


def test_repairable_failure_must_be_repaired_before_it_can_fail(
    run: dict[str, Path],
) -> None:
    result = review(run, "Figure 1", "--verdict", "fail", "--failure", "caption_contamination")

    assert result.returncode != 0
    assert "--verdict repair" in result.stderr


def test_repair_recrops_once_and_returns_to_review(run: dict[str, Path]) -> None:
    result = review(
        run,
        "Figure 1",
        "--verdict",
        "repair",
        "--failure",
        "caption_contamination",
        "--bbox",
        "0.1,0.2,0.9,0.6",
    )

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    repaired = Path(item["source_image_path"])
    assert repaired.name == "page_001_fig_figure_1_review_repair1.png"
    assert fitz.Pixmap(str(repaired)).width == 667
    assert fitz.Pixmap(str(repaired)).height == 667
    assert item["decision"] == "review_pending"
    assert item["visual_review"]["status"] == "pending"
    assert item["visual_review"]["repair_attempts"] == 1
    assert item["visual_review"]["revised_bbox"] == [0.1, 0.2, 0.9, 0.6]
    assert item["review_evidence"]["bbox_pt"] == [20.0, 80.0, 180.0, 240.0]
    assert item["source_image_sha256"] == hashlib.sha256(repaired.read_bytes()).hexdigest()

    result = review(run, "Figure 1", "--verdict", "pass", "--preserved", "diagram")

    assert result.returncode == 0, result.stderr
    assert gate_codes(run, "Figure 1") == []


def test_second_repair_fails_closed(run: dict[str, Path]) -> None:
    review_args = ("--verdict", "repair", "--failure", "caption_contamination")
    assert review(run, "Figure 1", *review_args, "--bbox", "0.1,0.2,0.9,0.6").returncode == 0

    result = review(run, "Figure 1", *review_args, "--bbox", "0.1,0.2,0.9,0.7")

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "visual_defect"
    assert item["skip_reason"] == "repair_limit_exhausted"
    assert item["visual_review"]["failure_reason"] == "repair_limit_exhausted"
    assert not list(Path(item["source_image_path"]).parent.glob("*_repair2.png"))
    assert gate_codes(run, "Figure 1") == []


@pytest.mark.parametrize(
    "bbox",
    ("0.1,0.1,0.8", "-0.1,0.1,0.8,0.8", "0.1,0.1,1.1,0.8", "0.8,0.1,0.2,0.8", "a,b,c,d"),
)
def test_repair_rejects_an_invalid_bbox(run: dict[str, Path], bbox: str) -> None:
    before = run["decisions"].read_bytes()

    result = review(
        run,
        "Figure 1",
        "--verdict",
        "repair",
        "--failure",
        "caption_contamination",
        f"--bbox={bbox}",
    )

    assert result.returncode != 0
    assert "bbox" in result.stderr
    assert run["decisions"].read_bytes() == before


def test_repair_needs_a_repairable_reason_and_a_bbox(run: dict[str, Path]) -> None:
    terminal = review(
        run, "Figure 1", "--verdict", "repair", "--failure", "identity_mismatch", "--bbox=0,0,1,1"
    )
    missing = review(run, "Figure 1", "--verdict", "repair", "--failure", "caption_contamination")

    assert terminal.returncode != 0
    assert "not repairable" in terminal.stderr
    assert missing.returncode != 0
    assert "--bbox" in missing.stderr


def test_promote_sends_an_unselected_crop_to_review(run: dict[str, Path]) -> None:
    assert entry(run, "Figure 2")["decision"] == "low_priority"

    result = promote(run, "Figure 2")

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 2")
    candidate = Path(item["source_image_path"])
    assert candidate.name == "page_002_fig_figure_2_review.png"
    assert fitz.Pixmap(str(candidate)).width == 667
    assert item["decision"] == "review_pending"
    assert item["promoted"] is True
    assert item["visual_quality_status"] == "usable_candidate"
    assert item["relative_markdown_embed"] == f"![Figure 2](images/{candidate.name})"
    assert item["review_evidence"]["source_page"] == 2
    assert item["review_evidence"]["render_dpi"] == 300
    assert item["visual_review"]["status"] == "pending"
    assert gate_codes(run, "Figure 2") == ["figure_visual_review_unresolved"]
    assert load(run)["summary"]["by_decision"]["review_pending"] == 2

    assert review(run, "Figure 2", "--verdict", "pass", "--preserved", "curve").returncode == 0
    assert gate_codes(run, "Figure 2") == []


def test_promote_without_a_crop_points_at_the_page_to_measure(run: dict[str, Path]) -> None:
    before = run["decisions"].read_bytes()

    result = promote(run, "Table 1")

    assert result.returncode != 0
    assert "--bbox" in result.stderr
    assert "page_002.png" in result.stderr
    assert run["decisions"].read_bytes() == before


def test_promote_with_a_bbox_renders_the_candidate_from_the_pdf(run: dict[str, Path]) -> None:
    result = promote(run, "Table 1", "--bbox", "0.1,0.2,0.9,0.6")

    assert result.returncode == 0, result.stderr
    item = entry(run, "Table 1")
    candidate = Path(item["source_image_path"])
    assert candidate.name == "page_002_fig_table_1_review.png"
    assert fitz.Pixmap(str(candidate)).width == 667
    assert item["decision"] == "review_pending"
    assert item["skip_reason"] == ""
    assert item["review_evidence"]["source_page"] == 2
    assert item["review_evidence"]["bbox_pt"] == [20.0, 80.0, 180.0, 240.0]
    assert item["review_evidence"]["normalized_bbox"] == [0.1, 0.2, 0.9, 0.6]
    assert item["review_evidence"]["page_preview_path"].endswith("page_002.png")

    assert review(run, "Table 1", "--verdict", "pass", "--preserved", "rows").returncode == 0
    assert gate_codes(run, "Table 1") == []


def test_promote_page_overrides_the_caption_page(run: dict[str, Path]) -> None:
    result = promote(run, "Table 1", "--page", "3", "--bbox", "0.1,0.2,0.9,0.6")

    assert result.returncode == 0, result.stderr
    item = entry(run, "Table 1")
    assert item["review_evidence"]["source_page"] == 3
    assert Path(item["source_image_path"]).name == "page_003_fig_table_1_review.png"


def test_promote_refuses_a_page_outside_the_pdf(run: dict[str, Path]) -> None:
    result = promote(run, "Table 1", "--page", "9", "--bbox", "0.1,0.2,0.9,0.6")

    assert result.returncode != 0
    assert "page 9" in result.stderr


def test_promote_requires_a_bbox_for_a_rejected_crop(run: dict[str, Path]) -> None:
    assert entry(run, "Table 2")["decision"] == "visual_defect"

    refused = promote(run, "Table 2")
    measured = promote(run, "Table 2", "--bbox", "0.1,0.2,0.9,0.6")

    assert refused.returncode != 0
    assert "--bbox" in refused.stderr
    assert measured.returncode == 0, measured.stderr
    assert entry(run, "Table 2")["decision"] == "review_pending"


def test_promote_cannot_reopen_a_reviewed_item(run: dict[str, Path]) -> None:
    assert (
        review(run, "Figure 1", "--verdict", "fail", "--failure", "identity_mismatch").returncode
        == 0
    )
    before = run["decisions"].read_bytes()

    result = promote(run, "Figure 1", "--bbox", "0.1,0.2,0.9,0.6")

    assert result.returncode != 0
    assert "already in Visual Review" in result.stderr
    assert run["decisions"].read_bytes() == before


def test_rerunning_the_planner_cannot_silently_drop_a_promotion(
    run: dict[str, Path],
) -> None:
    assert run_pipeline.has_review_work(load(run)) is False

    assert promote(run, "Figure 2").returncode == 0

    assert run_pipeline.has_review_work(load(run)) is True


def test_every_page_preview_carries_a_ten_percent_grid(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=600.0, height=800.0)
        page.draw_rect(fitz.Rect(72.0, 80.0, 520.0, 300.0), width=2.0)
        page.insert_text((72.0, 330.0), "Figure 1. A framed diagram used as a test.", fontsize=10)
        doc.new_page(width=600.0, height=800.0)
        doc.save(pdf_path)
    finally:
        doc.close()
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "fetch_pdf.py",
                "paper_id": "paper:test",
                "pdf_path": str(pdf_path),
                "identity_contract": {
                    "artifact_type": "canonical_identity",
                    "schema_version": 2,
                    "paper_id": "paper:test",
                    "identity_verdict": "accepted",
                    "work_level_identity": {"title": "Grid"},
                },
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "assets.json"
    subprocess.run(
        [
            sys.executable,
            str(EXTRACT_SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--assets-dir",
            str(tmp_path / "assets"),
        ],
        check=True,
    )

    pages = json.loads(output_path.read_text(encoding="utf-8"))["page_assets"]
    assert [bool(page["page_preview_path"]) for page in pages] == [True, True]
    blank = fitz.Pixmap(pages[1]["page_preview_path"])
    assert (blank.width, blank.height) == (800, 1067)
    white = (255, 255, 255)
    for fraction in (0.1, 0.5, 0.9):
        x, y = int(blank.width * fraction), int(blank.height * fraction)
        assert {blank.pixel(x - 1, 355), blank.pixel(x, 355)} != {white}
        assert {blank.pixel(267, y - 1), blank.pixel(267, y)} != {white}
    assert blank.pixel(440, 587) == white


REASON = "与 Figure 1 的主流程重复，笔记用不上"


def drop(run: dict[str, Path], item: str, *args: str) -> subprocess.CompletedProcess[str]:
    return review(run, item, "--verdict", "drop", *args)


def test_drop_records_the_reason_without_a_visual_failure(run: dict[str, Path]) -> None:
    result = drop(run, "Figure 1", "--reason", f"  {REASON}\n", "--notes", "Crop is clean.")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["skip_reason"] == REASON
    item = entry(run, "Figure 1")
    assert item["decision"] == "dropped"
    assert item["skip_reason"] == REASON
    review_record = item["visual_review"]
    assert review_record["status"] == "dropped"
    assert review_record["failure_reason"] == ""
    assert review_record["notes"] == "Crop is clean."
    assert (
        review_record["reviewed_asset_sha256"]
        == hashlib.sha256(Path(item["source_image_path"]).read_bytes()).hexdigest()
    )
    assert gate_codes(run, "Figure 1") == []


@pytest.mark.parametrize("reason", ["", "   ", "caption_contamination", "Identity_Mismatch"])
def test_drop_refuses_a_missing_reason_or_a_visual_failure(
    run: dict[str, Path], reason: str
) -> None:
    result = drop(run, "Figure 1", "--reason", reason)

    assert result.returncode != 0
    assert entry(run, "Figure 1")["decision"] == "review_pending"


@pytest.mark.parametrize(
    "extra",
    [
        ("--failure", "identity_mismatch"),
        ("--omitted", "legend"),
        ("--preserved", "panel a"),
        ("--bbox", "0.1,0.1,0.9,0.9"),
    ],
)
def test_drop_takes_no_review_findings(run: dict[str, Path], extra: tuple[str, str]) -> None:
    result = drop(run, "Figure 1", "--reason", REASON, *extra)

    assert result.returncode != 0
    assert entry(run, "Figure 1")["decision"] == "review_pending"


def test_reason_only_applies_to_drop(run: dict[str, Path]) -> None:
    result = review(
        run, "Figure 1", "--verdict", "pass", "--preserved", "axes", "--reason", REASON
    )

    assert result.returncode != 0
    assert entry(run, "Figure 1")["decision"] == "review_pending"


def test_drop_is_only_for_items_in_review(run: dict[str, Path]) -> None:
    result = drop(run, "Figure 2", "--reason", REASON)

    assert result.returncode != 0
    assert "promote" in result.stderr
    assert entry(run, "Figure 2")["decision"] == "low_priority"


def test_drop_refuses_a_candidate_changed_since_planning(run: dict[str, Path]) -> None:
    Path(entry(run, "Figure 1")["source_image_path"]).write_bytes(b"swapped")

    assert drop(run, "Figure 1", "--reason", REASON).returncode != 0
    assert entry(run, "Figure 1")["decision"] == "review_pending"


def test_a_promoted_item_can_be_dropped(run: dict[str, Path]) -> None:
    assert promote(run, "Figure 2").returncode == 0

    assert drop(run, "Figure 2", "--reason", REASON).returncode == 0
    assert entry(run, "Figure 2")["decision"] == "dropped"
    assert gate_codes(run, "Figure 2") == []


def test_a_dropped_item_stays_counted_and_cannot_be_replanned_away(
    run: dict[str, Path],
) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0

    wrapper = load(run)
    assert wrapper["summary"]["by_decision"]["dropped"] == 1
    assert wrapper["summary"]["total_items"] == len(wrapper["decisions"])
    assert run_pipeline.has_review_work(wrapper) is True


def test_a_later_verdict_replaces_a_drop(run: dict[str, Path]) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0

    result = review(run, "Figure 1", "--verdict", "pass", "--preserved", "axes")

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "insert"
    assert item["skip_reason"] == ""
    assert gate_codes(run, "Figure 1") == []


def test_repair_after_a_drop_clears_the_reason(run: dict[str, Path]) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0

    result = review(
        run,
        "Figure 1",
        "--verdict",
        "repair",
        "--failure",
        "caption_contamination",
        "--bbox",
        "0.1,0.2,0.9,0.5",
    )

    assert result.returncode == 0, result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "review_pending"
    assert item["skip_reason"] == ""


def rewrite_entry(run: dict[str, Path], label: str, **changes: object) -> None:
    wrapper = load(run)
    next(item for item in wrapper["decisions"] if item["source_id"] == label).update(changes)
    run["decisions"].write_text(json.dumps(wrapper), encoding="utf-8")


@pytest.mark.parametrize("reason", ["", "  ", "scientific_content_clipped"])
def test_gate_rejects_a_drop_without_a_real_reason(run: dict[str, Path], reason: str) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0

    rewrite_entry(run, "Figure 1", skip_reason=reason)

    assert gate_codes(run, "Figure 1") == ["figure_visual_review_drop_reason_invalid"]


def test_gate_rejects_a_drop_with_no_recorded_review(run: dict[str, Path]) -> None:
    rewrite_entry(run, "Figure 1", decision="dropped", skip_reason=REASON)

    assert gate_codes(run, "Figure 1") == ["figure_visual_review_stale"]


def test_gate_rejects_a_dropped_label_on_an_unreviewed_item(run: dict[str, Path]) -> None:
    rewrite_entry(run, "Figure 2", decision="dropped", skip_reason=REASON)

    assert "figure_visual_review_invalid" in gate_codes(run, "Figure 2")


def test_gate_rejects_a_drop_that_hides_a_visual_failure(run: dict[str, Path]) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0
    item = entry(run, "Figure 1")
    hidden = {**item["visual_review"], "failure_reason": "caption_inseparable"}

    rewrite_entry(run, "Figure 1", visual_review=hidden)

    assert gate_codes(run, "Figure 1") == ["figure_visual_review_invalid"]


def test_gate_goes_stale_when_a_dropped_crop_changes(run: dict[str, Path]) -> None:
    assert drop(run, "Figure 1", "--reason", REASON).returncode == 0

    Path(entry(run, "Figure 1")["source_image_path"]).write_bytes(b"swapped")

    assert gate_codes(run, "Figure 1") == ["figure_visual_review_stale"]


def test_an_unrecorded_placeholder_still_fails_the_gate(run: dict[str, Path]) -> None:
    rewrite_entry(run, "Figure 1", decision="placeholder", skip_reason=REASON)

    assert gate_codes(run, "Figure 1") == ["usable_insert_candidate_left_placeholder"]


def test_a_recorded_visual_failure_cannot_be_rewritten_as_a_drop(run: dict[str, Path]) -> None:
    assert (
        review(run, "Figure 1", "--verdict", "fail", "--failure", "identity_mismatch").returncode
        == 0
    )

    result = drop(run, "Figure 1", "--reason", REASON)

    assert result.returncode != 0
    assert "visual failure" in result.stderr
    item = entry(run, "Figure 1")
    assert item["decision"] == "visual_defect"
    assert item["visual_review"]["failure_reason"] == "identity_mismatch"
