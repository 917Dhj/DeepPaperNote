from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_final_quality_review import plan_payload, review_payload


WRITER = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts/write_obsidian_note.py"
NOTE = b"# Final Quality Gate\n\nRecorded states explain the measured improvement.\n"
GATES = (
    "passes_basic_structure", "passes_style_gate", "passes_math_gate", "passes_figure_gate",
    "passes_plan_gate", "passes_substantive_content", "passes_reference_hygiene_gate",
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {name: tmp_path / f"{name}.json" for name in (
        "plan", "source", "decisions", "lint", "grounding", "quality", "readability",
    )}
    paths["note"] = tmp_path / "note.md"
    paths["note"].write_bytes(NOTE)
    write_json(paths["plan"], plan_payload())
    write_json(paths["source"], {"status": "ok", "source_sha256": "a" * 64, "paper_id": "paper:quality"})
    write_json(paths["decisions"], {"output_language": "en", "decisions": []})
    write_json(paths["lint"], {
        "status": "ok", "script": "lint_note.py", "output_language": "en",
        "note_sha256": digest(paths["note"]), "note_plan_sha256": digest(paths["plan"]),
        **dict.fromkeys(GATES, True),
    })
    write_json(paths["grounding"], {
        "status": "ok", "script": "lint_grounding.py", "output_language": "en",
        "passes_grounding": True, "note_plan_sha256": digest(paths["plan"]),
        "source_manifest_sha256": digest(paths["source"]),
        "figure_decisions_sha256": digest(paths["decisions"]),
    })
    refresh_review(paths)
    return paths


def refresh_review(paths: dict[str, Path], *, failed: str = "") -> None:
    write_json(paths["quality"], review_payload(digest(paths["note"]), digest(paths["plan"]), failed=failed))
    write_json(paths["readability"], {
        "schema_version": 1, "output_language": "en", "verdict": "pass",
        "reviewed_note_sha256": digest(paths["note"]),
    })


def execute(tmp_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRITER), *args], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "DEEPPAPERNOTE_DISABLE_SHELL_CONFIG": "1",
             "DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR": "saved"},
    )


def record(tmp_path: Path, paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    return execute(tmp_path, [
        "--record-final-quality-review", "--language", "en", "--content-file", str(paths["note"]),
        "--plan-file", str(paths["plan"]), "--final-quality-review", str(paths["quality"]),
    ])


def save(tmp_path: Path, paths: dict[str, Path], *, mode: str = "workspace",
         reviews: bool = True, omit: str = "") -> subprocess.CompletedProcess[str]:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    args = ["--language", "en", "--title", "Final Quality Gate", "--save-mode", mode]
    if mode == "obsidian":
        args += ["--vault", str(vault)]
    flags = {
        "note": "--content-file", "plan": "--plan-file", "source": "--source-manifest",
        "decisions": "--figure-decisions", "lint": "--lint-json", "grounding": "--grounding-lint-json",
    }
    if reviews:
        flags.update(quality="--final-quality-review", readability="--final-readability-review")
    for name, flag in flags.items():
        if name != omit:
            args += [flag, str(paths[name])]
    return execute(tmp_path, args)


def assert_no_save(tmp_path: Path, result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 0, result.stdout
    assert not (tmp_path / "saved").exists()
    assert list((tmp_path / "vault").iterdir()) == []


@pytest.mark.parametrize("mode", ["workspace", "obsidian"])
def test_formal_save_refuses_missing_quality_and_readability_even_when_both_lints_pass(
    tmp_path: Path, mode: str,
) -> None:
    result = save(tmp_path, inputs(tmp_path), mode=mode, reviews=False)
    assert_no_save(tmp_path, result)


@pytest.mark.parametrize("mode", ["workspace", "obsidian"])
def test_recorded_quality_and_readability_save_identical_reviewed_bytes(tmp_path: Path, mode: str) -> None:
    paths = inputs(tmp_path)
    recorded = record(tmp_path, paths)
    assert recorded.returncode == 0, recorded.stderr
    assert not (tmp_path / "saved").exists()
    result = save(tmp_path, paths, mode=mode)
    assert result.returncode == 0, result.stderr
    target = Path(json.loads(result.stdout)["note_path"])
    assert target.read_bytes() == NOTE
    assert list(target.parent.glob("*.state.json")) == []
    assert not (target.parent / "quality.json").exists()


def test_record_phase_needs_no_configuration_title_or_vault(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    result = subprocess.run([
        sys.executable, str(WRITER), "--record-final-quality-review", "--language", "en",
        "--content-file", str(paths["note"]), "--plan-file", str(paths["plan"]),
        "--final-quality-review", str(paths["quality"]),
    ], cwd=tmp_path, capture_output=True, text=True,
       env={**os.environ, "DEEPPAPERNOTE_CONFIG_PATH": str(tmp_path / "absent-config.json")})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["revisions_used"] == 0
    assert not (tmp_path / "saved").exists()
    assert not (tmp_path / "vault").exists()


@pytest.mark.parametrize("omit", ["quality", "readability", "note"])
def test_formal_save_requires_explicit_review_inputs(tmp_path: Path, omit: str) -> None:
    paths = inputs(tmp_path)
    assert record(tmp_path, paths).returncode == 0
    assert_no_save(tmp_path, save(tmp_path, paths, omit=omit))


def test_passing_quality_must_have_been_recorded(tmp_path: Path) -> None:
    assert_no_save(tmp_path, save(tmp_path, inputs(tmp_path)))


@pytest.mark.parametrize("raw", [b"\xef\xbb\xbf" + NOTE, NOTE.replace(b"\n", b"\r\n"), b"\xff"])
def test_review_recording_refuses_noncanonical_draft_bytes(tmp_path: Path, raw: bytes) -> None:
    paths = inputs(tmp_path)
    paths["note"].write_bytes(raw)
    refresh_review(paths)
    result = record(tmp_path, paths)
    assert result.returncode != 0
    assert "UTF-8" in result.stderr or "canonical" in result.stderr
    assert not paths["quality"].with_suffix(".state.json").exists()


def test_invalid_and_stale_attempts_leave_journal_unchanged(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    refresh_review(paths, failed="central_claims")
    result = record(tmp_path, paths)
    assert result.returncode == 1
    assert json.loads(result.stdout)["revision_allowed"] is True
    state_path = paths["quality"].with_suffix(".state.json")
    previous = state_path.read_bytes()
    paths["note"].write_bytes(NOTE + b"Changed after review.\n")
    assert record(tmp_path, paths).returncode != 0
    assert state_path.read_bytes() == previous
    paths["quality"].write_text('{"verdict":"fail","verdict":"pass"}')
    assert record(tmp_path, paths).returncode != 0
    assert state_path.read_bytes() == previous


def test_two_revisions_and_replan_cannot_be_bypassed_by_a_later_pass(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    for revision in range(3):
        paths["note"].write_bytes(NOTE + f"Revision {revision}.\n".encode())
        paths["plan"].write_bytes(paths["plan"].read_bytes() + b"\n")
        refresh_review(paths, failed="central_claims")
        result = record(tmp_path, paths)
        assert result.returncode == 1, result.stderr
        report = json.loads(result.stdout)
        assert report["revisions_used"] == revision
    assert report["revision_allowed"] is False
    state_path = paths["quality"].with_suffix(".state.json")
    previous = state_path.read_bytes()
    paths["note"].write_bytes(NOTE + b"Third revision that claims to pass.\n")
    refresh_review(paths)
    rejected = record(tmp_path, paths)
    assert rejected.returncode != 0
    assert "revision" in rejected.stderr
    assert state_path.read_bytes() == previous


def test_readability_edit_invalidates_previous_quality_and_receipt(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    assert record(tmp_path, paths).returncode == 0
    paths["note"].write_bytes(NOTE + b"A readability edit.\n")
    lint = json.loads(paths["lint"].read_text())
    lint["note_sha256"] = digest(paths["note"])
    write_json(paths["lint"], lint)
    assert_no_save(tmp_path, save(tmp_path, paths))
    refresh_review(paths)
    assert record(tmp_path, paths).returncode == 0
    receipt = json.loads(paths["readability"].read_text())
    receipt["reviewed_note_sha256"] = "f" * 64
    write_json(paths["readability"], receipt)
    assert_no_save(tmp_path, save(tmp_path, paths))


def test_corrupt_journal_is_not_reinitialized(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    state_path = paths["quality"].with_suffix(".state.json")
    state_path.write_text("{}")
    result = record(tmp_path, paths)
    assert result.returncode != 0
    assert state_path.read_text() == "{}"


def test_preflight_does_not_require_final_reviews(tmp_path: Path) -> None:
    paths = inputs(tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    result = execute(tmp_path, [
        "--preflight", "--vault", str(vault), "--title", "Preflight Quality",
        "--language", "en", "--source-manifest", str(paths["source"]),
    ])
    assert result.returncode == 0, result.stderr
    assert list(vault.iterdir()) == []


def test_preflight_and_record_phase_cannot_be_combined(tmp_path: Path) -> None:
    result = execute(tmp_path, ["--preflight", "--record-final-quality-review"])
    assert result.returncode != 0
