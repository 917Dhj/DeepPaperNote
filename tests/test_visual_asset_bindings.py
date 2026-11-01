from __future__ import annotations

import shutil
from pathlib import Path

import lint_grounding
import pytest
import write_obsidian_note
from formal_save_helpers import reviewed_insert_fields
from test_lint_grounding import grounded_note_plan, run_lint_grounding, slim_bundle, source_manifest

OUTDATED_SHA256 = "0" * 64
NOTE_TEXT = "![Figure 1](images/figure.png)\n"


def figure_candidate(tmp_path: Path) -> Path:
    image = tmp_path / "figure.png"
    image.write_bytes(b"figure")
    return image


def insert_decision(image: Path, **overrides: object) -> dict:
    return {
        "source_id": "Figure 1",
        "kind": "figure",
        "decision": "insert",
        "visual_quality_status": "usable_candidate",
        "source_image_path": str(image),
        "source_image_filename": image.name,
        **reviewed_insert_fields(image),
        **overrides,
    }


def grounding_codes(tmp_path: Path, decision: dict) -> set[str]:
    manifest = source_manifest()
    manifest["captions"] = {
        "figures": [{"id": "Figure 1", "caption": "Architecture", "page": 4}],
        "tables": [],
    }
    result = run_lint_grounding(
        tmp_path, grounded_note_plan(), manifest, slim_bundle(), {"decisions": [decision]}
    )
    return {issue["code"] for issue in result["issues"]}


def test_grounding_binds_an_insert_to_its_review_hash(tmp_path: Path) -> None:
    decision = insert_decision(figure_candidate(tmp_path), source_image_sha256=OUTDATED_SHA256)

    assert "figure_visual_review_stale" not in grounding_codes(tmp_path, decision)


def test_grounding_binds_a_visual_failure_to_its_review_hash(tmp_path: Path) -> None:
    decision = insert_decision(
        figure_candidate(tmp_path), decision="visual_defect", source_image_sha256=OUTDATED_SHA256
    )
    decision["visual_review"].update(status="fail", failure_reason="identity_mismatch")

    assert lint_grounding.final_visual_failure_is_valid(decision)


def test_grounding_reports_a_malformed_review_once(tmp_path: Path) -> None:
    decision = insert_decision(figure_candidate(tmp_path))
    decision["visual_review"]["notes"] = None

    codes = grounding_codes(tmp_path, decision)

    assert "figure_visual_review_invalid" in codes
    assert "figure_visual_review_stale" not in codes


def test_grounding_reports_a_review_both_malformed_and_outdated(tmp_path: Path) -> None:
    image = figure_candidate(tmp_path)
    decision = insert_decision(image)
    decision["visual_review"]["notes"] = None
    image.write_bytes(b"changed-after-review")

    codes = grounding_codes(tmp_path, decision)

    assert {"figure_visual_review_invalid", "figure_visual_review_stale"} <= codes


def test_grounding_still_rejects_an_asset_changed_after_review(tmp_path: Path) -> None:
    image = figure_candidate(tmp_path)
    decision = insert_decision(image)
    image.write_bytes(b"changed-after-review")

    assert "figure_visual_review_stale" in grounding_codes(tmp_path, decision)


def materialize(tmp_path: Path, decision: dict) -> list[dict]:
    return write_obsidian_note.materialize_insert_decisions(
        NOTE_TEXT, tmp_path / "paper" / "note.md", {"decisions": [decision]}, "images"
    )


def test_save_binds_an_insert_to_its_review_hash(tmp_path: Path) -> None:
    decision = insert_decision(figure_candidate(tmp_path), source_image_sha256=OUTDATED_SHA256)

    assert len(materialize(tmp_path, decision)) == 1
    assert (tmp_path / "paper" / "images" / "figure.png").read_bytes() == b"figure"


def test_save_still_rejects_an_asset_changed_after_review(tmp_path: Path) -> None:
    image = figure_candidate(tmp_path)
    decision = insert_decision(image)
    image.write_bytes(b"changed-after-review")

    with pytest.raises(SystemExit, match="reviewed asset SHA-256"):
        materialize(tmp_path, decision)


def test_save_hashes_an_existing_image_once(tmp_path: Path, monkeypatch) -> None:
    decision = insert_decision(figure_candidate(tmp_path))
    existing = tmp_path / "paper" / "images" / "figure.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"figure")
    hashed: list[Path] = []
    real_file_sha256 = write_obsidian_note.file_sha256

    def counting_file_sha256(path: Path) -> str:
        hashed.append(Path(path))
        return real_file_sha256(path)

    monkeypatch.setattr(write_obsidian_note, "file_sha256", counting_file_sha256)

    assert len(materialize(tmp_path, decision)) == 1
    assert hashed.count(existing) == 1


def test_save_still_refuses_a_different_existing_image(tmp_path: Path) -> None:
    decision = insert_decision(figure_candidate(tmp_path))
    existing = tmp_path / "paper" / "images" / "figure.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"other figure")

    with pytest.raises(SystemExit, match="different bytes"):
        materialize(tmp_path, decision)

    assert existing.read_bytes() == b"other figure"


def test_save_verifies_the_bytes_it_copies(tmp_path: Path, monkeypatch) -> None:
    decision = insert_decision(figure_candidate(tmp_path))

    def truncated_copy(source: Path, destination: Path) -> None:
        Path(destination).write_bytes(b"fig")

    monkeypatch.setattr(shutil, "copy2", truncated_copy)

    with pytest.raises(SystemExit, match="Materialized image bytes"):
        materialize(tmp_path, decision)
