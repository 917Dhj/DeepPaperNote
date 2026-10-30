from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "skills/deeppapernote/scripts"
FINAL_GATES = (
    "passes_basic_structure",
    "passes_style_gate",
    "passes_math_gate",
    "passes_figure_gate",
    "passes_plan_gate",
    "passes_substantive_content",
    "passes_reference_hygiene_gate",
)
NOTE = "# Formal Save Gate\n\nThe current evidence supports this reading.\n"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_inputs(tmp_path: Path) -> dict[str, Path]:
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("plan", "source", "decisions", "lint", "grounding")
    }
    write_json(paths["plan"], {"output_language": "en", "paper_type": "AI_method"})
    write_json(paths["source"], {
        "status": "ok", "paper_id": "paper:formal-save", "source_sha256": "a" * 64,
        "captions": {"figures": [], "tables": []},
    })
    write_json(paths["decisions"], {"output_language": "en", "decisions": []})
    write_json(paths["lint"], {
        "status": "ok", "script": "lint_note.py", "output_language": "en",
        "note_sha256": hashlib.sha256(NOTE.encode()).hexdigest(),
        "note_plan_sha256": digest(paths["plan"]),
        **dict.fromkeys(FINAL_GATES, True),
    })
    write_json(paths["grounding"], {
        "status": "ok", "script": "lint_grounding.py", "output_language": "en",
        "passes_grounding": True,
        "note_plan_sha256": digest(paths["plan"]),
        "source_manifest_sha256": digest(paths["source"]),
        "figure_decisions_sha256": digest(paths["decisions"]),
    })
    return paths


def run_save(
    tmp_path: Path, paths: dict[str, Path], *, mode: str = "workspace",
    omit: tuple[str, ...] = (), bound: bool = True, preflight: bool = False,
) -> subprocess.CompletedProcess[str]:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    command = [
        sys.executable, str(SCRIPTS / "write_obsidian_note.py"),
        "--title", "Formal Save Gate", "--language", "en", "--save-mode", mode,
        "--subdir", "Papers/Formal Save Gate", "--content", NOTE,
    ]
    if mode == "obsidian":
        command += ["--vault", str(vault)]
    flags = {
        "lint": "--lint-json", "decisions": "--figure-decisions",
        "source": "--source-manifest",
    }
    if bound:
        flags.update(plan="--plan-file", grounding="--grounding-lint-json")
    if preflight:
        command.append("--preflight")
    for name, flag in flags.items():
        if name not in omit:
            command += [flag, str(paths[name])]
    return subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "DEEPPAPERNOTE_DISABLE_SHELL_CONFIG": "1",
             "DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR": "saved"},
    )


def assert_no_save(tmp_path: Path, result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 0, result.stdout
    assert not (tmp_path / "saved").exists()
    assert list((tmp_path / "vault").iterdir()) == []


@pytest.mark.parametrize("mode", ["workspace", "obsidian"])
def test_formal_save_refuses_legacy_unbound_reports(tmp_path: Path, mode: str) -> None:
    paths = save_inputs(tmp_path)
    write_json(paths["decisions"], {
        "output_language": "en",
        "decisions": [{"source_id": "Figure 1", "decision": "review_pending"}],
    })
    lint = json.loads(paths["lint"].read_text())
    for gate in FINAL_GATES[3:]:
        lint.pop(gate)
    write_json(paths["lint"], lint)

    result = run_save(tmp_path, paths, mode=mode, bound=False)

    assert_no_save(tmp_path, result)


@pytest.mark.parametrize("mode", ["workspace", "obsidian"])
def test_formal_save_accepts_current_bound_reports(tmp_path: Path, mode: str) -> None:
    result = run_save(tmp_path, save_inputs(tmp_path), mode=mode)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert Path(report["note_path"]).read_text() == NOTE


@pytest.mark.parametrize("missing", ["grounding", "plan", "source"])
def test_formal_save_requires_current_inputs(tmp_path: Path, missing: str) -> None:
    result = run_save(tmp_path, save_inputs(tmp_path), omit=(missing,))

    assert_no_save(tmp_path, result)
    assert {"grounding": "Grounding", "plan": "Note Plan", "source": "Source Manifest"}[
        missing
    ] in result.stderr


@pytest.mark.parametrize("gate", FINAL_GATES)
def test_formal_save_requires_every_final_lint_gate(tmp_path: Path, gate: str) -> None:
    paths = save_inputs(tmp_path)
    lint = json.loads(paths["lint"].read_text())
    lint.pop(gate)
    write_json(paths["lint"], lint)

    result = run_save(tmp_path, paths)

    assert_no_save(tmp_path, result)
    assert "gate failed" in result.stderr


@pytest.mark.parametrize("report,field,value", [
    ("lint", "passes_math_gate", False),
    ("lint", "passes_math_gate", "true"),
    ("lint", "passes_math_gate", 1),
    ("grounding", "passes_grounding", False),
    ("grounding", "passes_grounding", "true"),
    ("grounding", "passes_grounding", 1),
    ("lint", "script", "lint_grounding.py"),
    ("grounding", "script", "lint_note.py"),
    ("lint", "status", "error"),
    ("grounding", "status", "error"),
    ("lint", "output_language", "zh-CN"),
    ("grounding", "output_language", "zh-CN"),
])
def test_formal_save_rejects_invalid_reports(
    tmp_path: Path, report: str, field: str, value: object,
) -> None:
    paths = save_inputs(tmp_path)
    payload = json.loads(paths[report].read_text())
    payload[field] = value
    write_json(paths[report], payload)

    assert_no_save(tmp_path, run_save(tmp_path, paths))


@pytest.mark.parametrize("report", ["lint", "grounding"])
def test_formal_save_rejects_nonobject_reports(tmp_path: Path, report: str) -> None:
    paths = save_inputs(tmp_path)
    write_json(paths[report], [])

    result = run_save(tmp_path, paths)

    assert_no_save(tmp_path, result)
    assert "JSON object" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("name", ["plan", "source", "decisions"])
def test_formal_save_rejects_changed_grounding_inputs(tmp_path: Path, name: str) -> None:
    paths = save_inputs(tmp_path)
    paths[name].write_bytes(paths[name].read_bytes() + b"\n")

    result = run_save(tmp_path, paths)

    assert_no_save(tmp_path, result)
    assert "SHA-256" in result.stderr


def test_formal_save_requires_lints_to_bind_the_same_plan(tmp_path: Path) -> None:
    paths = save_inputs(tmp_path)
    lint = json.loads(paths["lint"].read_text())
    lint["note_plan_sha256"] = "b" * 64
    write_json(paths["lint"], lint)

    result = run_save(tmp_path, paths)

    assert_no_save(tmp_path, result)
    assert "Note Plan" in result.stderr


@pytest.mark.parametrize("decision", ["review_pending", "insert"])
def test_formal_save_revalidates_current_figure_decisions(tmp_path: Path, decision: str) -> None:
    paths = save_inputs(tmp_path)
    image = tmp_path / "figure.png"
    image.write_bytes(b"figure")
    write_json(paths["decisions"], {"output_language": "en", "decisions": [{
        "source_id": "Figure 1", "decision": decision,
        "source_image_path": str(image), "source_image_sha256": digest(image),
        "visual_review": {
            "status": "pass", "reviewed_asset_sha256": digest(image),
            "preserved_scientific_elements": ["complete figure"],
            "omitted_scientific_elements": [], "notes": "Caption-free body.",
            "failure_reason": "", "repair_attempts": 0, "revised_bbox": [],
        },
    }]})
    grounding = json.loads(paths["grounding"].read_text())
    grounding["figure_decisions_sha256"] = digest(paths["decisions"])
    write_json(paths["grounding"], grounding)

    result = run_save(tmp_path, paths)

    assert_no_save(tmp_path, result)
    expected = "figure_visual_review_unresolved" if decision == "review_pending" else (
        "figure_visual_review_evidence_invalid"
    )
    assert expected in result.stderr


def test_preflight_stays_independent_of_formal_save_artifacts(tmp_path: Path) -> None:
    paths = save_inputs(tmp_path)
    result = run_save(
        tmp_path, paths, mode="obsidian", bound=False,
        omit=("lint", "decisions"), preflight=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["phase"] == "save_target_admission"
    assert list((tmp_path / "vault").iterdir()) == []


def test_final_lint_records_exact_plan_and_normalized_note_hashes(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_bytes(b"\xef\xbb\xbf" + NOTE.replace("\n", "\r\n").encode())
    plan = tmp_path / "note.plan.json"
    plan.write_bytes(b'{\r\n  "output_language": "en"\r\n}\r\n')
    result = subprocess.run([
        sys.executable, str(SCRIPTS / "lint_note.py"), "--language", "en",
        "--input", str(note), "--plan-file", str(plan),
    ], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["note_plan_sha256"] == digest(plan)
    assert report["note_sha256"] == hashlib.sha256(NOTE.encode()).hexdigest()
