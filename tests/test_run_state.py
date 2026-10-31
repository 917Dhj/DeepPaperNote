from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import _final_quality
import common
import plan_figure_table_decisions
import pytest
import run_pipeline
import run_state
from test_lint_grounding import grounded_note_plan, slim_bundle, source_manifest

SCRIPT = Path(run_state.__file__).resolve()


def dump(path: Path, record: dict) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stages(report: dict) -> dict:
    return {stage["id"]: stage for stage in report["stages"]}


def snapshot(path: Path) -> dict:
    return {
        str(item.relative_to(path)): (item.read_bytes(), item.stat().st_mtime_ns)
        for item in path.rglob("*")
        if item.is_file()
    }


@pytest.fixture
def completed_run(tmp_path: Path) -> tuple[Path, dict, dict[str, Path]]:
    workdir = tmp_path / "run with spaces"
    workdir.mkdir()
    paths = run_pipeline.pipeline_artifact_paths(workdir, "run")
    for key in run_state.LATE_ARTIFACTS:
        paths[key] = workdir / f"selected {key}.json"
    paths["draft"] = workdir / "selected draft.zh-CN.md"
    pdf = workdir / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\nsource bytes")
    dump(paths["resolve"], {"script": "resolve_paper.py", "status": "ok", "paper_id": "paper:test"})
    dump(
        paths["metadata"],
        {
            "script": "collect_metadata.py",
            "status": "ok",
            "title": "A paper",
            "doi": "10.1234/test",
            "paper_id": "paper:test",
        },
    )
    dump(
        paths["identity"],
        {
            "script": "build_identity_contract.py",
            "status": "ok",
            "schema_version": 2,
            "artifact_type": "canonical_identity",
            "identity_verdict": "accepted",
            "paper_id": "paper:test",
            "work_level_identity": {"title": "A paper", "doi": "10.1234/test"},
        },
    )
    dump(
        paths["fetch"],
        {"script": "fetch_pdf.py", "status": "ok", "pdf_path": str(pdf), "source_sha256": sha(pdf)},
    )
    manifest = source_manifest()
    manifest["paper_id"] = "paper:test"
    raw = []
    for section in manifest["sections"]:
        text = f"{section['title']} describes the method and its measured evidence."
        digest = hashlib.sha256(text.encode()).hexdigest()
        section["text_hash_sha256"] = digest
        raw.append({**section, "text": text})
    paths["raw_sections"].write_text("\n".join(json.dumps(item) for item in raw) + "\n")
    manifest.update(
        script="extract_source_text.py",
        status="ok",
        source_sha256=sha(pdf),
        pdf={"path": str(pdf)},
        raw_sections_path=str(paths["raw_sections"]),
    )
    dump(paths["source_manifest"], manifest)
    dump(paths["evidence"], {"script": "extract_evidence.py", "status": "ok", "evidence_pack": {}})
    dump(paths["assets"], {"script": "extract_pdf_assets.py", "status": "ok", "pdf_path": str(pdf)})
    dump(
        paths["figures"],
        {
            "script": "plan_figures.py",
            "status": "ok",
            "output_language": "zh-CN",
            "figure_plan": {"figures": []},
        },
    )
    dump(
        paths["figure_table_decisions"],
        {
            "script": "plan_figure_table_decisions.py",
            "status": "ok",
            "output_language": "zh-CN",
            "decisions": [],
        },
    )
    dump(paths["bundle"], {"script": "build_synthesis_bundle.py", "status": "ok", **slim_bundle()})
    dump(paths["note_plan"], grounded_note_plan())
    dump(
        paths["grounding_lint"],
        {
            "script": "lint_grounding.py",
            "status": "ok",
            "output_language": "zh-CN",
            "passes_grounding": True,
            "note_plan_sha256": sha(paths["note_plan"]),
            "source_manifest_sha256": sha(paths["source_manifest"]),
            "figure_decisions_sha256": sha(paths["figure_table_decisions"]),
        },
    )
    paths["draft"].write_bytes("# A paper\n\nA grounded final note.\n".encode())
    dump(
        paths["note_lint"],
        {
            "script": "lint_note.py",
            "status": "ok",
            "output_language": "zh-CN",
            "note_sha256": sha(paths["draft"]),
            "note_plan_sha256": sha(paths["note_plan"]),
            **dict.fromkeys(run_state.LINT_GATES, True),
            "warnings": ["one warning"],
        },
    )
    review = {
        "schema_version": 1,
        "output_language": "zh-CN",
        "verdict": "pass",
        "reviewed_note_sha256": sha(paths["draft"]),
        "reviewed_plan_sha256": sha(paths["note_plan"]),
        "checks": dict.fromkeys(_final_quality.QUALITY_CHECKS, True),
        "blocking_findings": [],
    }
    dump(paths["quality_review"], review)
    review_id = _final_quality.validate_quality(
        review,
        note_sha256=sha(paths["draft"]),
        plan_sha256=sha(paths["note_plan"]),
        plan=grounded_note_plan(),
        language="zh-CN",
    )
    dump(
        paths["quality_review"].with_suffix(".state.json"),
        _final_quality.advance_state(None, review, review_id, language="zh-CN"),
    )
    dump(
        paths["readability_review"],
        {
            "schema_version": 1,
            "output_language": "zh-CN",
            "verdict": "pass",
            "reviewed_note_sha256": sha(paths["draft"]),
        },
    )
    root = tmp_path / "Vault"
    note = root / "Papers" / "AI" / "A paper" / "note.zh-CN.md"
    note.parent.mkdir(parents=True)
    note.write_bytes(paths["draft"].read_bytes())
    dump(
        paths["save_receipt"],
        {
            "script": "write_obsidian_note.py",
            "status": "ok",
            "output_language": "zh-CN",
            "note_path": str(note),
            "title": "A paper",
            "output_mode": "obsidian",
            "base_output_root": str(root),
            "subdir": "Papers/AI",
            "source_sha256": sha(pdf),
            "materialized_figures": [],
            "final_quality_review": "pass",
            "final_readability_review": "pass",
            "reviewed_note_sha256": sha(paths["draft"]),
        },
    )
    bindings = {
        "schema_version": 1,
        "artifacts": {
            key: str(paths[key].relative_to(workdir)) for key in run_state.LATE_ARTIFACTS
        },
        "context": {"output_language": "zh-CN", "save_mode": "workspace", "papers_dir": "Papers"},
    }
    paths["admission"].unlink(missing_ok=True)
    bindings["artifacts"].pop("admission")
    return workdir, bindings, paths


def test_empty_query_is_successful_readonly_and_late_paths_are_unselected(tmp_path: Path) -> None:
    before = snapshot(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--workdir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert report["summary"]["saved_verified"] is False
    assert report["artifacts"]["draft"] == {"path": None, "selection": "unselected", "sha256": None}
    assert report["next_action"]["stage"] == "resolve"
    assert report["next_action"]["missing_context"] == ["paper_reference"]
    assert "argv" not in report["next_action"]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "arguments",
    [
        ["--workdir", "absent"],
        ["--workdir", ".", "--prefix", "../x"],
        ["--workdir", ".", "--prefix", "a\\b"],
        [],
    ],
)
def test_cli_rejects_invalid_inputs_without_creating_paths(tmp_path: Path, arguments: list) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "status", *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "error"
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"schema_version": True},
        {"schema_version": 1, "unknown": 2},
        {"schema_version": 1, "artifacts": {"newest": "x"}},
        {"schema_version": 1, "artifacts": {"quality_state": "x"}},
        {"schema_version": 1, "artifacts": {"draft": ""}},
        {"schema_version": 1, "context": {"output_language": "fr"}},
        {"schema_version": 1, "context": {"overwrite": "yes"}},
        {"schema_version": 1, "context": {"save_mode": "auto"}},
    ],
)
def test_bindings_are_closed_and_strict(tmp_path: Path, bad: dict) -> None:
    with pytest.raises(ValueError):
        run_state.inspect_run(tmp_path, bindings=bad)


@pytest.mark.parametrize(
    "text",
    [
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":1,"context":{"vault":NaN}}',
        '{"schema_version":1,"context":{"vault":1e999}}',
    ],
)
def test_cli_rejects_duplicate_and_nonfinite_bindings(tmp_path: Path, text: str) -> None:
    bindings = tmp_path / "bindings.json"
    bindings.write_text(text)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "status",
            "--workdir",
            str(tmp_path),
            "--bindings",
            str(bindings),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "error"


def test_selected_current_chain_verifies_save_and_never_calls_mutating_helpers(
    completed_run: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir, bindings, paths = completed_run
    vault = workdir.parent / "Vault"
    before = snapshot(workdir), snapshot(vault)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Status must not execute producers, read global config, or record reviews"
        )

    monkeypatch.setattr(common, "runtime_config", forbidden)
    monkeypatch.setattr(run_pipeline, "runtime_config", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(_final_quality, "advance_state", forbidden)
    report = run_state.inspect_run(workdir, bindings=bindings)
    current = stages(report)
    assert current["resolve"]["status"] == "present_unverified"
    assert current["identity"]["status"] == "passed"
    assert current["source_manifest"]["status"] == "passed"
    assert current["note_plan"]["status"] == "passed"
    assert current["quality_review"]["status"] == "passed"
    assert report["summary"] == {
        "saved_verified": True,
        "title": "A paper",
        "strong_identifier": "10.1234/test",
        "gate_verdicts": dict.fromkeys(
            ("grounding_lint", "note_lint", "quality_review", "readability_review"), "passed"
        ),
        "warning_count": 1,
        "figure_counts": {"insert": 0, "placeholder": 0},
        "saved_mode": "obsidian",
        "saved_path": str(vault / "Papers/AI/A paper/note.zh-CN.md"),
        "saved_domain": "AI",
        "saved_sha256_match": True,
    }
    assert report["next_action"]["kind"] == "manual_verification"
    assert report["provenance_gaps"]
    assert (snapshot(workdir), snapshot(vault)) == before


@pytest.mark.parametrize(
    "artifact,update,expected",
    [
        ("grounding_lint", {"passes_grounding": 1}, "failed"),
        ("grounding_lint", {"source_manifest_sha256": "a" * 64}, "stale"),
        ("note_lint", {"passes_style_gate": "true"}, "failed"),
        ("note_lint", {"note_plan_sha256": "a" * 64}, "stale"),
        ("note_lint", {"script": "other.py"}, "invalid"),
        ("note_lint", {"status": "error"}, "failed"),
        ("note_lint", {"output_language": "en"}, "invalid"),
        ("readability_review", {"reviewed_note_sha256": "a" * 64}, "stale"),
        ("quality_review", {"reviewed_plan_sha256": "a" * 64}, "stale"),
        ("quality_review", {"checks": {}}, "invalid"),
        ("save_receipt", {"note_path": "/outside/root.md"}, "invalid"),
        ("save_receipt", {"subdir": "../elsewhere"}, "invalid"),
    ],
)
def test_artifact_failure_does_not_hide_later_results(
    completed_run: tuple, artifact: str, update: dict, expected: str
) -> None:
    workdir, bindings, paths = completed_run
    record = json.loads(paths[artifact].read_text())
    record.update(update)
    dump(paths[artifact], record)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)[artifact]["status"] == expected
    assert len(report["stages"]) == len(run_state.STAGES)
    assert report["summary"]["saved_verified"] is False


def test_actual_byte_changes_are_detected_without_timestamp_freshness(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    (workdir / "source.pdf").write_bytes(b"changed PDF")
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["fetch"]["status"] == "stale"
    assert stages(report)["source_manifest"]["status"] == "stale"
    assert "source_manifest" in stages(report)["grounding_lint"]["unmet_dependencies"]
    assert report["summary"]["saved_verified"] is False
    assert report["next_action"]["stage"] == "fetch"


def test_raw_sections_hash_and_selected_corpus_are_checked(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    raw = paths["raw_sections"].read_text().replace("describes", "CHANGED")
    paths["raw_sections"].write_text(raw)
    assert (
        stages(run_state.inspect_run(workdir, bindings=bindings))["source_manifest"]["status"]
        == "stale"
    )
    other = workdir / "different.jsonl"
    other.write_text(raw)
    bindings["artifacts"]["raw_sections"] = str(other)
    result = stages(run_state.inspect_run(workdir, bindings=bindings))["source_manifest"]
    assert result["status"] == "invalid"
    assert any(item["code"] == "raw_sections_selection_mismatch" for item in result["issues"])


def test_changed_plan_decisions_and_draft_invalidate_bound_gates(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    paths["note_plan"].write_bytes(paths["note_plan"].read_bytes() + b" ")
    paths["figure_table_decisions"].write_bytes(paths["figure_table_decisions"].read_bytes() + b" ")
    paths["draft"].write_bytes(paths["draft"].read_bytes() + b"changed\n")
    report = run_state.inspect_run(workdir, bindings=bindings)
    for key in (
        "grounding_lint",
        "note_lint",
        "quality_review",
        "readability_review",
        "save_receipt",
    ):
        assert stages(report)[key]["status"] == "stale", key
    assert report["next_action"]["stage"] == "grounding_lint"


def test_missing_receipt_does_not_prove_no_save_and_missing_saved_note_fails(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    saved = Path(json.loads(paths["save_receipt"].read_text())["note_path"])
    paths["save_receipt"].unlink()
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert saved.is_file()
    assert report["summary"]["saved_verified"] is False
    assert any("does not prove" in item["message"] for item in report["provenance_gaps"])
    assert report["next_action"]["stage"] == "save_receipt"
    assert report["next_action"]["kind"] == "command"
    paths["save_receipt"].write_text("{")
    assert (
        stages(run_state.inspect_run(workdir, bindings=bindings))["save_receipt"]["status"]
        == "invalid"
    )


def test_quality_unrecorded_pass_and_fail_require_recording_before_revision(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    paths["quality_review"].with_suffix(".state.json").unlink()
    for verdict in ("pass", "fail"):
        review = json.loads(paths["quality_review"].read_text())
        review["verdict"] = verdict
        if verdict == "fail":
            review["checks"]["central_claims"] = False
            review["blocking_findings"] = [
                {
                    "check": "central_claims",
                    "plan_ref": "/central_claims/0",
                    "reason": "Evidence mismatch",
                    "required_revision": "Correct claim",
                }
            ]
        dump(paths["quality_review"], review)
        report = run_state.inspect_run(workdir, bindings=bindings)
        assert stages(report)["quality_review"]["status"] == "present_unverified"
        assert report["next_action"]["kind"] == "command"
        assert "--record-final-quality-review" in report["next_action"]["argv"]
        assert report["summary"]["saved_verified"] is False


def test_recorded_failure_budget_and_exhausted_changed_draft(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    review = json.loads(paths["quality_review"].read_text())
    review.update(
        verdict="fail",
        checks={**review["checks"], "central_claims": False},
        blocking_findings=[
            {
                "check": "central_claims",
                "plan_ref": "/central_claims/0",
                "reason": "Mismatch",
                "required_revision": "Correct claim",
            }
        ],
    )
    dump(paths["quality_review"], review)
    review_id = _final_quality.validate_quality(
        review,
        note_sha256=sha(paths["draft"]),
        plan_sha256=sha(paths["note_plan"]),
        plan=grounded_note_plan(),
        language="zh-CN",
    )
    state = _final_quality.advance_state(None, review, review_id, language="zh-CN")
    journal = paths["quality_review"].with_suffix(".state.json")
    dump(journal, state)
    report = run_state.inspect_run(workdir, bindings=bindings)
    result = stages(report)["quality_review"]
    assert result["status"] == "failed"
    assert result["details"]["revisions_remaining"] == 2
    assert report["next_action"]["kind"] == "model_action"
    state.update(revisions_used=2, exhausted_note_sha256=sha(paths["draft"]))
    dump(journal, state)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["next_action"]["kind"] == "user_action"
    paths["draft"].write_bytes(paths["draft"].read_bytes() + b"unauthorized third revision")
    result = stages(run_state.inspect_run(workdir, bindings=bindings))["quality_review"]
    assert result["details"]["revision_allowed"] is False
    assert any(item["code"] == "quality_revision_limit_exhausted" for item in result["issues"])


def test_old_review_replay_and_corrupt_journal_cannot_restore_pass(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    journal = paths["quality_review"].with_suffix(".state.json")
    state = json.loads(journal.read_text())
    old = state["last_review"]["review_id"]
    state["seen_review_ids"].append("b" * 64)
    state["last_review"]["review_id"] = "b" * 64
    dump(journal, state)
    report = run_state.inspect_run(workdir, bindings=bindings)
    result = stages(report)["quality_review"]
    assert result["status"] == "failed"
    assert result["details"]["review_id"] == old
    assert report["next_action"]["kind"] == "user_action"
    journal.write_text('{"schema_version":1,"schema_version":1}')
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["quality_review"]["status"] == "invalid"
    assert report["summary"]["saved_verified"] is False


def test_admission_is_historical_and_blocked_receipt_requires_user_action(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"]["save_mode"] = "obsidian"
    bindings["artifacts"]["admission"] = str(paths["admission"])
    receipt = {
        "script": "write_obsidian_note.py",
        "status": "blocked",
        "output_language": "zh-CN",
        "source_sha256": sha(workdir / "source.pdf"),
        "conflict_code": "note_exists",
    }
    dump(paths["admission"], receipt)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["admission"]["status"] == "failed"
    assert report["next_action"]["kind"] == "user_action"
    assert "argv" not in report["next_action"]
    receipt.update(status="ok", phase="save_target_admission", source_sha256="a" * 64)
    dump(paths["admission"], receipt)
    assert (
        stages(run_state.inspect_run(workdir, bindings=bindings))["admission"]["status"] == "stale"
    )


@pytest.mark.parametrize("raw", [b"\xef\xbb\xbf# Note\n", b"# Note\r\n", b"# Note\r"])
def test_windows_draft_normalization_is_lint_only_quality_requires_canonical_bytes(
    completed_run: tuple,
    raw: bytes,
) -> None:
    workdir, bindings, paths = completed_run
    paths["draft"].write_bytes(raw)
    lint = json.loads(paths["note_lint"].read_text())
    lint["note_sha256"] = hashlib.sha256(b"# Note\n").hexdigest()
    dump(paths["note_lint"], lint)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["note_lint"]["status"] == "passed"
    assert stages(report)["quality_review"]["status"] == "invalid"
    assert report["summary"]["saved_verified"] is False


def test_bindings_paths_and_json_cli_work_from_another_cwd_without_cross_prefix_mix(
    completed_run: tuple,
    tmp_path: Path,
) -> None:
    workdir, bindings, paths = completed_run
    bindings_file = tmp_path / "status bindings.json"
    dump(bindings_file, bindings)
    before = snapshot(workdir), snapshot(tmp_path / "Vault")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "status",
            "--workdir",
            str(workdir),
            "--bindings",
            bindings_file.name,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["summary"]["saved_verified"] is True
    assert (snapshot(workdir), snapshot(tmp_path / "Vault")) == before
    second = run_state.inspect_run(workdir, prefix="other")
    assert all(item["status"] == "missing" for item in second["stages"])
    assert second["artifacts"]["resolve"]["path"] == str(workdir / "other_resolve.json")
    absolute = copy.deepcopy(bindings)
    absolute["artifacts"] = {key: str(paths[key]) for key in bindings["artifacts"]}
    assert run_state.inspect_run(workdir, bindings=absolute)["summary"]["saved_verified"] is True


def test_resolve_recommendation_uses_real_argv_and_selected_context(tmp_path: Path) -> None:
    report = run_state.inspect_run(
        tmp_path,
        bindings={"schema_version": 1, "context": {"paper_reference": "a paper with spaces"}},
    )
    action = report["next_action"]
    assert action["kind"] == "command"
    assert action["argv"] == [
        sys.executable,
        str(SCRIPT.with_name("resolve_paper.py")),
        "--input",
        "a paper with spaces",
        "--output",
        str(tmp_path / "run_resolve.json"),
    ]
    assert action["cwd"] == str(tmp_path)


def test_optional_workspace_admission_does_not_gate_save_but_remains_visible(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    bindings["artifacts"]["admission"] = str(paths["admission"])
    dump(
        paths["admission"],
        {
            "script": "write_obsidian_note.py",
            "status": "blocked",
            "output_language": "zh-CN",
            "source_sha256": sha(workdir / "source.pdf"),
        },
    )
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["admission"]["status"] == "failed"
    assert stages(report)["admission"]["details"]["required"] is False
    assert report["summary"]["saved_verified"] is True
    assert report["next_action"]["kind"] == "manual_verification"


def test_saved_note_absence_and_changed_bytes_are_distinct(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    saved = Path(json.loads(paths["save_receipt"].read_text())["note_path"])
    saved.write_bytes(saved.read_bytes() + b"external change")
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["save_receipt"]["status"] == "stale"
    assert report["summary"]["saved_sha256_match"] is False
    saved.unlink()
    result = stages(run_state.inspect_run(workdir, bindings=bindings))["save_receipt"]
    assert result["status"] == "missing"
    assert result["issues"][0]["code"] == "saved_note_missing"


def test_unknown_save_mode_and_late_output_selection_require_context(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"].pop("save_mode")
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["next_action"]["missing_context"] == ["save_mode"]
    assert "argv" not in report["next_action"]
    bindings["context"]["save_mode"] = "workspace"
    bindings["artifacts"].pop("note_plan")
    report = run_state.inspect_run(workdir, bindings=bindings)
    action = report["next_action"]
    assert action["stage"] == "note_plan"
    assert action["kind"] == "model_action"
    assert action["output_path"] is None
    assert "artifacts.note_plan" in action["missing_context"]
    assert action["input_paths"]["raw_sections"] == str(paths["raw_sections"])


def test_missing_lint_gate_and_malformed_readability_are_rejected(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    lint = json.loads(paths["note_lint"].read_text())
    del lint["passes_plan_gate"]
    dump(paths["note_lint"], lint)
    readability = json.loads(paths["readability_review"].read_text())
    readability.update(verdict="fail", extra="not allowed")
    dump(paths["readability_review"], readability)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["note_lint"]["status"] == "failed"
    assert stages(report)["readability_review"]["status"] == "invalid"
    assert report["summary"]["saved_verified"] is False


def test_admission_precedes_preparation_in_canonical_next_action(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"].update(
        save_mode="obsidian", vault=str(workdir.parent / "Vault"), papers_dir="Papers"
    )
    bindings["artifacts"]["admission"] = str(paths["admission"])
    for key in ("evidence", "assets", "figures", "figure_table_decisions", "bundle"):
        paths[key].unlink()
    report = run_state.inspect_run(workdir, bindings=bindings)
    action = report["next_action"]
    assert stages(report)["source_manifest"]["status"] == "passed"
    assert action["stage"] == "admission"
    assert action["kind"] == "command"
    assert "--preflight" in action["argv"]
    assert "admission" in stages(report)["evidence"]["unmet_dependencies"]


def test_invalid_metadata_and_cross_paper_binding_do_not_supply_summary_identity(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    metadata = json.loads(paths["metadata"].read_text())
    metadata.update(script="other.py", title="Untrusted paper", doi="10.0/wrong")
    dump(paths["metadata"], metadata)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["summary"]["title"] is None
    assert report["summary"]["strong_identifier"] is None
    assert report["summary"]["saved_verified"] is False
    metadata.update(script="collect_metadata.py", paper_id="paper:other")
    dump(paths["metadata"], metadata)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["metadata"]["status"] == "present_unverified"
    assert report["summary"]["title"] == "A paper"
    assert report["summary"]["strong_identifier"] == "10.1234/test"
    fetch = json.loads(paths["fetch"].read_text())
    fetch["paper_id"] = "paper:other"
    dump(paths["fetch"], fetch)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["fetch"]["status"] == "invalid"
    assert any(item["code"] == "paper_id_mismatch" for item in stages(report)["fetch"]["issues"])
    assert report["summary"]["saved_verified"] is False


@pytest.mark.parametrize("subdir", ["AI", ""])
def test_obsidian_domain_comes_from_actual_path_when_receipt_omits_papers_prefix(
    completed_run: tuple,
    subdir: str,
) -> None:
    workdir, bindings, paths = completed_run
    receipt = json.loads(paths["save_receipt"].read_text())
    receipt["subdir"] = subdir
    dump(paths["save_receipt"], receipt)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["summary"]["saved_verified"] is True
    assert report["summary"]["saved_domain"] == "AI"


def test_obsidian_saved_domain_stays_unknown_without_selected_papers_root(
    completed_run: tuple,
) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"].pop("papers_dir")
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["summary"]["saved_verified"] is True
    assert report["summary"]["saved_domain"] is None
    assert any("papers_dir" in item["message"] for item in report["provenance_gaps"])


def test_current_visual_bytes_are_checked_and_counts_follow_decisions(completed_run: tuple) -> None:
    from formal_save_helpers import reviewed_insert_fields

    workdir, bindings, paths = completed_run
    image = workdir / "scientific figure.png"
    image.write_bytes(b"image bytes")
    decisions = json.loads(paths["figure_table_decisions"].read_text())
    decisions["decisions"] = [
        {
            "source_id": "Figure 1",
            "kind": "figure",
            "decision": "insert",
            "source_image_path": str(image),
            "visual_quality_status": "usable",
            **reviewed_insert_fields(image),
        },
        {"source_id": "Table 1", "kind": "table", "decision": "placeholder"},
    ]
    dump(paths["figure_table_decisions"], decisions)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["figure_table_decisions"]["status"] == "passed"
    assert report["summary"]["figure_counts"] == {"insert": 1, "placeholder": 1}
    image.write_bytes(b"changed image bytes")
    result = stages(run_state.inspect_run(workdir, bindings=bindings))["figure_table_decisions"]
    assert result["status"] == "stale"
    assert any(item["code"] == "figure_visual_review_stale" for item in result["issues"])


@pytest.mark.parametrize("save_mode", ["workspace", "obsidian"])
def test_decisions_command_uses_admitted_asset_subdir(completed_run: tuple, save_mode: str) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"]["save_mode"] = save_mode
    source_sha = json.loads(paths["source_manifest"].read_text())["source_sha256"]
    asset_subdir = "images" if save_mode == "workspace" else f"images/{source_sha}"
    if save_mode == "obsidian":
        bindings["artifacts"]["admission"] = str(paths["admission"])
        dump(
            paths["admission"],
            {
                "script": "write_obsidian_note.py",
                "status": "ok",
                "phase": "save_target_admission",
                "output_language": "zh-CN",
                "source_sha256": source_sha,
                "asset_subdir": asset_subdir,
            },
        )
    paths["figure_table_decisions"].unlink()
    action = run_state.inspect_run(workdir, bindings=bindings)["next_action"]
    assert action["stage"] == "figure_table_decisions"
    assert action["kind"] == "command"
    assert action["argv"][action["argv"].index("--asset-subdir") + 1] == asset_subdir
    parsed = plan_figure_table_decisions.parser().parse_args(action["argv"][2:])
    assert parsed.asset_subdir == asset_subdir


@pytest.mark.parametrize(
    "asset_subdir", [None, [], "", "../images", "images/../x", "assets", "images/" + "a" * 64]
)
def test_decisions_command_requires_valid_admission_asset_subdir(
    completed_run: tuple, asset_subdir: object
) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"]["save_mode"] = "obsidian"
    bindings["artifacts"]["admission"] = str(paths["admission"])
    receipt = {
        "script": "write_obsidian_note.py",
        "status": "ok",
        "phase": "save_target_admission",
        "output_language": "zh-CN",
        "source_sha256": json.loads(paths["source_manifest"].read_text())["source_sha256"],
    }
    if asset_subdir is not None:
        receipt["asset_subdir"] = asset_subdir
    dump(paths["admission"], receipt)
    paths["figure_table_decisions"].unlink()
    action = run_state.inspect_run(workdir, bindings=bindings)["next_action"]
    assert action["stage"] == "figure_table_decisions"
    assert action["kind"] == "missing_context"
    assert action["missing_context"] == ["admission.asset_subdir"]
    assert "argv" not in action


@pytest.mark.parametrize("language", [[], {}, None, True, 1])
def test_cli_reports_malformed_artifact_language_without_context(
    tmp_path: Path, language: object
) -> None:
    dump(
        tmp_path / "run_figures.json",
        {
            "script": "plan_figures.py",
            "status": "ok",
            "figure_plan": {},
            "output_language": language,
        },
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "status", "--workdir", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert stages(report)["figures"]["status"] == "invalid"
    assert "output_language" not in report["resolved_context"]


@pytest.mark.parametrize("language", [[], {}, None, True, 1])
def test_cli_rejects_malformed_explicit_language(tmp_path: Path, language: object) -> None:
    bindings = tmp_path / "bindings.json"
    dump(bindings, {"schema_version": 1, "context": {"output_language": language}})
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "status",
            "--workdir",
            str(tmp_path),
            "--bindings",
            str(bindings),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "error"


def test_valid_conflicting_languages_require_context(tmp_path: Path) -> None:
    dump(
        tmp_path / "run_figures.json",
        {"script": "plan_figures.py", "status": "ok", "figure_plan": {}, "output_language": "en"},
    )
    dump(
        tmp_path / "run_figure_table_decisions.json",
        {
            "script": "plan_figure_table_decisions.py",
            "status": "ok",
            "decisions": [],
            "output_language": "zh-CN",
        },
    )
    report = run_state.inspect_run(tmp_path)
    assert stages(report)["figures"]["status"] == "present_unverified"
    assert any(
        item["code"] == "language_context_missing" for item in stages(report)["figures"]["issues"]
    )


def test_json_receipt_extensions_do_not_change_language_inference(completed_run: tuple) -> None:
    workdir, bindings, paths = completed_run
    bindings["context"].pop("output_language")
    baseline = run_state.inspect_run(workdir, bindings=bindings)
    assert baseline["summary"]["saved_verified"] is True
    for key, path in paths.items():
        if path.suffix == ".json" and path.exists():
            record = json.loads(path.read_text())
            if "output_language" in record:
                renamed = path.with_suffix(".out")
                path.rename(renamed)
                bindings["artifacts"][key] = str(renamed)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert report["resolved_context"]["output_language"] == "zh-CN"
    assert report["summary"]["gate_verdicts"] == baseline["summary"]["gate_verdicts"]
    assert report["summary"]["saved_verified"] is True


@pytest.mark.parametrize("artifact", ["raw_sections", "draft"])
def test_text_artifact_with_json_suffix_remains_text(completed_run: tuple, artifact: str) -> None:
    workdir, bindings, paths = completed_run
    renamed = paths[artifact].with_suffix(".json")
    paths[artifact].rename(renamed)
    bindings["artifacts"][artifact] = str(renamed)
    if artifact == "raw_sections":
        manifest = json.loads(paths["source_manifest"].read_text())
        manifest["raw_sections_path"] = str(renamed)
        dump(paths["source_manifest"], manifest)
        grounding = json.loads(paths["grounding_lint"].read_text())
        grounding["source_manifest_sha256"] = sha(paths["source_manifest"])
        dump(paths["grounding_lint"], grounding)
    report = run_state.inspect_run(workdir, bindings=bindings)
    assert stages(report)["source_manifest"]["status"] == "passed"
    assert stages(report)["draft"]["status"] == "passed"
    assert report["summary"]["saved_verified"] is True
