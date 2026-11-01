from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import plan_figure_table_decisions
import pytest
import run_pipeline
from test_run_pipeline_manifest import RUN_PIPELINE_SCRIPT, WRITE_NOTE_SCRIPT, write_test_pdf

ACQUIRE_STEPS = [
    "resolve_paper.py",
    "collect_metadata.py",
    "build_identity_contract.py",
    "fetch_pdf.py",
    "extract_source_text.py",
]
PREPARE_STEPS = [
    "extract_evidence.py",
    "extract_pdf_assets.py",
    "plan_figures.py",
    "plan_figure_table_decisions.py",
    "build_synthesis_bundle.py",
]
SOURCE_SHA256 = "a" * 64


def dump(path: Path, record: dict) -> Path:
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


@pytest.fixture
def calls(monkeypatch) -> list[list[str]]:
    recorded: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        recorded.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_pipeline.subprocess, "run", fake_run)
    return recorded


def run_main(monkeypatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", *argv])
    run_pipeline.main()


def step_names(calls: list[list[str]]) -> list[str]:
    return [Path(cmd[1]).name for cmd in calls]


def flag_value(calls: list[list[str]], script: str, flag: str) -> str:
    call = next(cmd for cmd in calls if Path(cmd[1]).name == script)
    return call[call.index(flag) + 1]


def acquired_workdir(tmp_path: Path) -> Path:
    workdir = tmp_path / "run"
    workdir.mkdir()
    paths = run_pipeline.pipeline_artifact_paths(workdir, "paper")
    dump(paths["metadata"], {"title": "Paper"})
    dump(paths["fetch"], {"status": "ok"})
    dump(paths["source_manifest"], {"status": "ok", "source_sha256": SOURCE_SHA256})
    return workdir


def admission(tmp_path: Path, **overrides: object) -> Path:
    record = {
        "status": "ok",
        "script": "write_obsidian_note.py",
        "phase": "save_target_admission",
        "asset_subdir": "images",
        "source_sha256": SOURCE_SHA256,
        "output_language": "zh-CN",
    }
    return dump(tmp_path / "admission.json", {**record, **overrides})


def obsidian_flags(tmp_path: Path) -> tuple[str, ...]:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    return ("--save-mode", "obsidian", "--vault", str(vault))


def test_acquire_stops_at_the_source_manifest(tmp_path: Path, monkeypatch, calls, capsys) -> None:
    workdir = tmp_path / "run"

    run_main(monkeypatch, "acquire", "--input", "paper.pdf", "--workdir", str(workdir))

    assert step_names(calls) == ACQUIRE_STEPS
    printed = capsys.readouterr().out.splitlines()
    assert f"workdir={workdir.resolve()}" in printed
    assert f"source_manifest={workdir.resolve() / 'run_source_manifest.json'}" in printed
    assert not any(line.startswith("bundle=") for line in printed)


def test_acquire_needs_no_admission_in_obsidian_mode(tmp_path: Path, monkeypatch, calls) -> None:
    run_main(
        monkeypatch,
        "acquire",
        "--input",
        "paper.pdf",
        "--workdir",
        str(tmp_path / "run"),
        *obsidian_flags(tmp_path),
    )

    assert step_names(calls) == ACQUIRE_STEPS


def test_prepare_runs_offline_stages_with_workspace_images(
    tmp_path: Path, monkeypatch, calls, capsys
) -> None:
    workdir = acquired_workdir(tmp_path)

    run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--prefix", "paper")

    assert step_names(calls) == PREPARE_STEPS
    assert flag_value(calls, "plan_figure_table_decisions.py", "--asset-subdir") == "images"
    assert f"bundle={workdir.resolve() / 'paper_bundle.json'}" in capsys.readouterr().out


def test_prepare_carries_the_admitted_asset_subdir(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)
    receipt = admission(tmp_path, asset_subdir=f"images/{SOURCE_SHA256}")

    run_main(
        monkeypatch,
        "prepare",
        "--workdir",
        str(workdir),
        "--prefix",
        "paper",
        "--admission",
        str(receipt),
        *obsidian_flags(tmp_path),
    )

    assert step_names(calls) == PREPARE_STEPS
    assert (
        flag_value(calls, "plan_figure_table_decisions.py", "--asset-subdir")
        == f"images/{SOURCE_SHA256}"
    )


def test_obsidian_prepare_requires_an_admission(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)

    with pytest.raises(SystemExit, match="--admission"):
        run_main(
            monkeypatch,
            "prepare",
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
            *obsidian_flags(tmp_path),
        )

    assert calls == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "blocked"}, "Save Target Admission"),
        ({"phase": "formal_save"}, "Save Target Admission"),
        ({"source_sha256": "b" * 64}, "source_sha256"),
        ({"output_language": "en"}, "output_language"),
    ],
)
def test_prepare_rejects_an_unusable_admission(
    tmp_path: Path, monkeypatch, calls, overrides: dict, message: str
) -> None:
    workdir = acquired_workdir(tmp_path)

    with pytest.raises(SystemExit, match=message):
        run_main(
            monkeypatch,
            "prepare",
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
            "--admission",
            str(admission(tmp_path, **overrides)),
            *obsidian_flags(tmp_path),
        )

    assert calls == []


@pytest.mark.parametrize("value", ["None", "", "../outside", f"images/{SOURCE_SHA256[:12]}"])
def test_planner_rejects_what_prepare_passes_through(value: str) -> None:
    with pytest.raises(SystemExit, match="preflight"):
        plan_figure_table_decisions.checked_asset_subdir(value)


def test_prepare_rejects_an_unreadable_admission(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)
    receipt = tmp_path / "admission.json"
    receipt.write_text("[not json", encoding="utf-8")

    with pytest.raises(SystemExit, match="Save Target Admission"):
        run_main(
            monkeypatch,
            "prepare",
            "--workdir",
            str(workdir),
            "--prefix",
            "paper",
            "--admission",
            str(receipt),
            *obsidian_flags(tmp_path),
        )

    assert calls == []


def test_prepare_requires_an_acquired_source(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)
    run_pipeline.pipeline_artifact_paths(workdir, "paper")["source_manifest"].unlink()

    with pytest.raises(SystemExit, match="acquire"):
        run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--prefix", "paper")

    assert calls == []


def test_prepare_rejects_a_blocked_source_manifest(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)
    dump(
        run_pipeline.pipeline_artifact_paths(workdir, "paper")["source_manifest"],
        {"status": "blocked", "blocked_code": "unreadable_text"},
    )

    with pytest.raises(SystemExit, match="Source Manifest"):
        run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--prefix", "paper")

    assert calls == []


def test_prepare_takes_no_acquisition_arguments(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)

    with pytest.raises(SystemExit):
        run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--input", "other-paper")

    assert calls == []


def test_prepare_requires_a_named_workdir(monkeypatch, calls) -> None:
    with pytest.raises(SystemExit):
        run_main(monkeypatch, "prepare")

    assert calls == []


def test_one_shot_run_stops_before_side_effects_in_obsidian_mode(
    tmp_path: Path, monkeypatch, calls
) -> None:
    workdir = tmp_path / "must-not-exist"

    with pytest.raises(SystemExit, match="acquire"):
        run_main(
            monkeypatch,
            "--input",
            "paper.pdf",
            "--workdir",
            str(workdir),
            *obsidian_flags(tmp_path),
        )

    assert calls == []
    assert not workdir.exists()


def test_one_shot_run_carries_workspace_images(tmp_path: Path, monkeypatch, calls) -> None:
    run_main(monkeypatch, "--input", "paper.pdf", "--workdir", str(tmp_path / "run"))

    assert step_names(calls) == ACQUIRE_STEPS + PREPARE_STEPS
    assert flag_value(calls, "plan_figure_table_decisions.py", "--asset-subdir") == "images"


def reviewed_decisions() -> dict:
    return {"decisions": [{"visual_review": {"status": "pass"}}]}


def untouched_decisions() -> dict:
    return {"decisions": [{"visual_review": {"status": "pending"}}]}


@pytest.mark.parametrize("phase", ["prepare", "one-shot"])
def test_rebuilding_refuses_to_replace_reviewed_decisions(
    tmp_path: Path, monkeypatch, calls, phase: str
) -> None:
    workdir = acquired_workdir(tmp_path)
    decisions = run_pipeline.pipeline_artifact_paths(workdir, "paper")["figure_table_decisions"]
    dump(decisions, reviewed_decisions())
    original = decisions.read_bytes()
    argv = ["--workdir", str(workdir), "--prefix", "paper"]
    argv = ["prepare", *argv] if phase == "prepare" else ["--input", "paper.pdf", *argv]

    with pytest.raises(SystemExit, match="--discard-reviews"):
        run_main(monkeypatch, *argv)

    assert calls == []
    assert decisions.read_bytes() == original


def test_rebuilding_treats_unreadable_decisions_as_reviewed(
    tmp_path: Path, monkeypatch, calls
) -> None:
    workdir = acquired_workdir(tmp_path)
    decisions = run_pipeline.pipeline_artifact_paths(workdir, "paper")["figure_table_decisions"]
    decisions.write_text("{broken", encoding="utf-8")

    with pytest.raises(SystemExit, match="--discard-reviews"):
        run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--prefix", "paper")

    assert calls == []


def test_rebuilding_keeps_going_over_unreviewed_decisions(
    tmp_path: Path, monkeypatch, calls
) -> None:
    workdir = acquired_workdir(tmp_path)
    decisions = run_pipeline.pipeline_artifact_paths(workdir, "paper")["figure_table_decisions"]
    dump(decisions, untouched_decisions())

    run_main(monkeypatch, "prepare", "--workdir", str(workdir), "--prefix", "paper")

    assert step_names(calls) == PREPARE_STEPS


def test_discard_reviews_allows_the_rebuild(tmp_path: Path, monkeypatch, calls) -> None:
    workdir = acquired_workdir(tmp_path)
    decisions = run_pipeline.pipeline_artifact_paths(workdir, "paper")["figure_table_decisions"]
    dump(decisions, reviewed_decisions())

    run_main(
        monkeypatch,
        "prepare",
        "--workdir",
        str(workdir),
        "--prefix",
        "paper",
        "--discard-reviews",
    )

    assert step_names(calls) == PREPARE_STEPS


def test_default_workdir_leaves_the_current_directory_alone(
    tmp_path: Path, monkeypatch, calls, capsys
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(project)

    run_main(monkeypatch, "acquire", "--input", "10.5555/first")

    workdir = Path(flag_value(calls, "resolve_paper.py", "--output")).parent
    assert workdir.parent == home.resolve() / ".deeppapernote" / "runs"
    assert f"workdir={workdir}" in capsys.readouterr().out
    assert list(project.iterdir()) == []


def test_default_workdir_keeps_each_paper_apart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    first = run_pipeline.default_workdir("10.5555/first")

    assert first == run_pipeline.default_workdir("  10.5555/first ")
    assert first != run_pipeline.default_workdir("10.5555/second")


def test_default_workdir_separates_same_named_local_pdfs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    workdirs = []
    for name in ("first", "second"):
        project = tmp_path / name
        project.mkdir()
        (project / "paper.pdf").write_bytes(b"%PDF")
        monkeypatch.chdir(project)
        workdirs.append(run_pipeline.default_workdir("paper.pdf"))

    assert workdirs[0] != workdirs[1]


def test_default_workdir_accepts_a_reference_too_long_for_a_path() -> None:
    name = run_pipeline.default_workdir("a very long title " * 100).name

    assert name.startswith("a_very_long_title")
    assert len(name) <= run_pipeline.WORKDIR_NAME_LENGTH + 9


@pytest.mark.parametrize(
    ("reference", "readable"),
    [
        ("10.1109/CVPR.2016.90", "10_1109_CVPR_2016_90"),
        ("arXiv:1512.03385", "arXiv_1512_03385"),
        ("Deep Residual Learning", "Deep_Residual_Learning"),
        ("残差学习 综述", "残差学习_综述"),
        ("???", "paper"),
    ],
)
def test_default_workdir_can_be_found_by_reference(reference: str, readable: str) -> None:
    name, digest = run_pipeline.default_workdir(reference).name.rsplit("-", 1)

    assert name == readable
    assert len(digest) == 8


def test_default_workdir_names_a_local_pdf_by_its_stem(tmp_path: Path) -> None:
    pdf = tmp_path / "resnet.final.pdf"
    pdf.write_bytes(b"%PDF")

    assert run_pipeline.default_workdir(str(pdf)).name.startswith("resnet_final-")


def test_two_phases_run_through_a_real_admission(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    write_test_pdf(pdf)
    workdir = tmp_path / "run"
    receipt = workdir / "admission.json"
    manifest = workdir / "run_source_manifest.json"
    obsidian = obsidian_flags(tmp_path)

    def run_script(*argv: str) -> None:
        result = subprocess.run(
            [sys.executable, *argv], check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_script(
        str(RUN_PIPELINE_SCRIPT),
        "acquire",
        "--input",
        str(pdf),
        "--workdir",
        str(workdir),
        "--zotero-mode",
        "off",
        *obsidian,
    )
    assert not (workdir / "run_evidence.json").exists()
    source = json.loads(manifest.read_text(encoding="utf-8"))

    run_script(
        str(WRITE_NOTE_SCRIPT),
        "--preflight",
        "--title",
        source["title"],
        "--source-manifest",
        str(manifest),
        "--output",
        str(receipt),
        *obsidian,
    )
    run_script(
        str(RUN_PIPELINE_SCRIPT),
        "prepare",
        "--workdir",
        str(workdir),
        "--admission",
        str(receipt),
        *obsidian,
    )

    decisions = json.loads((workdir / "run_figure_table_decisions.json").read_text("utf-8"))
    bundle = json.loads((workdir / "run_bundle.json").read_text("utf-8"))
    assert decisions["asset_subdir"] == "images"
    assert decisions["output_language"] == bundle["output_language"] == "zh-CN"
