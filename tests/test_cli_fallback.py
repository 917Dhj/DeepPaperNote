from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import write_obsidian_note

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"
MATERIALIZE_SCRIPT = (
    PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "materialize_figure_asset.py"
)
ENV_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "check_environment.py"


def formal_save_args(
    tmp_path: Path,
    note_text: str,
    output_language: str = "zh-CN",
) -> list[str]:
    lint_path = tmp_path / "passing-lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": output_language,
                "note_sha256": hashlib.sha256(note_text.encode("utf-8")).hexdigest(),
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
            }
        ),
        encoding="utf-8",
    )
    decisions_path = tmp_path / "figure-decisions.json"
    decisions_path.write_text(
        json.dumps({"output_language": output_language, "decisions": []}),
        encoding="utf-8",
    )
    return ["--lint-json", str(lint_path), "--figure-decisions", str(decisions_path)]


def source_manifest_args(tmp_path: Path, source_sha256: str = "a" * 64) -> list[str]:
    source_manifest_path = tmp_path / "source-manifest.json"
    source_manifest_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "paper_id": "paper:test",
                "source_sha256": source_sha256,
            }
        ),
        encoding="utf-8",
    )
    return ["--source-manifest", str(source_manifest_path)]


def test_write_note_creates_language_variant_and_directory_sidecar(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# My Test Paper\n\nVault write admission test.\n"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "Benchmark",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    note_path = Path(payload["note_path"])
    sidecar_path = note_path.parent / ".deeppapernote.json"
    assert note_path.name == "My_Test_Paper.zh-CN.md"
    assert note_path.read_text(encoding="utf-8") == note_text
    assert json.loads(sidecar_path.read_text(encoding="utf-8")) == {
        "artifact_type": "deeppapernote_paper_directory",
        "schema_version": 1,
        "paper_id": "paper:test",
        "title": "My Test Paper",
        "source_sha256": "a" * 64,
        "note_stem": "My_Test_Paper",
        "notes": {
            "zh-CN": {
                "filename": "My_Test_Paper.zh-CN.md",
                "note_sha256": hashlib.sha256(note_text.encode("utf-8")).hexdigest(),
            }
        },
    }


def test_write_note_reuses_empty_same_name_directory_before_domain_routing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    existing_dir = vault / "LegacyArchive/My_Test_Paper"
    existing_dir.mkdir(parents=True)
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# My Test Paper\n\nReuse the empty directory.\n"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "NewDomain",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    note_path = Path(json.loads(result.stdout)["note_path"])
    assert note_path.parent == existing_dir.resolve()
    assert not (vault / "Research/Papers/NewDomain/My_Test_Paper").exists()


def test_write_note_reuses_source_directory_for_another_language(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    chinese_note = "# My Test Paper\n\n中文笔记。\n"
    english_note = "# My Test Paper\n\nEnglish note.\n"

    chinese_result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "ChineseDomain",
            "--content",
            chinese_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, chinese_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert chinese_result.returncode == 0, chinese_result.stderr
    chinese_path = Path(json.loads(chinese_result.stdout)["note_path"])

    english_result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "EnglishDomain",
            "--language",
            "en",
            "--content",
            english_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, english_note, "en"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert english_result.returncode == 0, english_result.stderr
    english_path = Path(json.loads(english_result.stdout)["note_path"])
    assert english_path.parent == chinese_path.parent
    assert english_path.name == "My_Test_Paper.en.md"
    sidecar = json.loads((english_path.parent / ".deeppapernote.json").read_text(encoding="utf-8"))
    assert set(sidecar["notes"]) == {"zh-CN", "en"}


def test_write_note_does_not_replace_another_language_note_image(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    def save_args(note_text: str, language: str, source_image: Path) -> list[str]:
        args = formal_save_args(tmp_path, note_text, language)
        decisions_path = Path(args[-1])
        digest = hashlib.sha256(source_image.read_bytes()).hexdigest()
        decisions_path.write_text(
            json.dumps(
                {
                    "output_language": language,
                    "decisions": [
                        {
                            "source_id": "Figure 1",
                            "decision": "insert",
                            "source_image_path": str(source_image),
                            "source_image_filename": "shared.png",
                            "source_image_sha256": digest,
                            "visual_review": {
                                "status": "pass",
                                "reviewed_asset_sha256": digest,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return args

    chinese_image = tmp_path / "chinese.png"
    english_image = tmp_path / "english.png"
    chinese_image.write_bytes(b"chinese-image")
    english_image.write_bytes(b"english-image")
    chinese_note = "# My Test Paper\n\n![Figure 1](images/shared.png)\n"
    english_note = "# My Test Paper\n\n![Figure 1](images/shared.png)\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            chinese_note,
            *source_manifest_args(tmp_path),
            *save_args(chinese_note, "zh-CN", chinese_image),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    directory = Path(json.loads(first.stdout)["note_path"]).parent

    second = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--language",
            "en",
            "--content",
            english_note,
            *source_manifest_args(tmp_path),
            *save_args(english_note, "en", english_image),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert second.returncode != 0
    assert "existing paper-local image has different bytes" in second.stderr
    assert (directory / "images/shared.png").read_bytes() == b"chinese-image"
    assert not (directory / "My_Test_Paper.en.md").exists()


def test_formal_save_rolls_back_when_sidecar_finalization_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    original_note = "# Rollback Paper\n\nOriginal body.\n"
    replacement_note = "# Rollback Paper\n\nReplacement body.\n"
    monkeypatch.setenv("DEEPPAPERNOTE_DISABLE_SHELL_CONFIG", "1")
    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "Rollback Paper",
            "--content",
            original_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, original_note),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    sidecar_path = note_path.parent / ".deeppapernote.json"
    original_sidecar = sidecar_path.read_bytes()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "Rollback Paper",
            "--content",
            replacement_note,
            "--overwrite-existing-note",
            "--expected-existing-note-sha256",
            hashlib.sha256(original_note.encode("utf-8")).hexdigest(),
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, replacement_note),
        ],
    )

    def fail_hidden(_path: Path) -> None:
        raise OSError("simulated Hidden attribute failure")

    monkeypatch.setattr(write_obsidian_note, "ensure_sidecar_hidden", fail_hidden)

    with pytest.raises(OSError, match="simulated Hidden attribute failure"):
        write_obsidian_note.main()

    assert note_path.read_text(encoding="utf-8") == original_note
    assert sidecar_path.read_bytes() == original_sidecar


def test_write_note_blocks_same_source_and_language_without_mutating_vault(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    original_note = "# My Test Paper\n\nOriginal note.\n"
    replacement_note = "# My Test Paper\n\nReplacement note.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "OriginalDomain",
            "--content",
            original_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, original_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    sidecar_path = note_path.parent / ".deeppapernote.json"
    original_sidecar = sidecar_path.read_bytes()

    second = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "DifferentDomain",
            "--content",
            replacement_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, replacement_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 2, second.stderr
    conflict = json.loads(second.stdout)
    assert conflict["status"] == "blocked"
    assert conflict["conflict_code"] == "same_language_note_exists"
    assert conflict["requires_user_confirmation"] is True
    assert conflict["existing_note_path"] == str(note_path)
    assert conflict["existing_note_sha256"] == hashlib.sha256(
        original_note.encode("utf-8")
    ).hexdigest()
    assert note_path.read_text(encoding="utf-8") == original_note
    assert sidecar_path.read_bytes() == original_sidecar
    assert not (vault / "Research/Papers/DifferentDomain").exists()


def test_write_note_overwrites_only_with_matching_existing_note_sha256(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    original_note = "# My Test Paper\n\nOriginal note.\n"
    replacement_note = "# My Test Paper\n\nApproved replacement.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            original_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, original_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    original_sha256 = hashlib.sha256(original_note.encode("utf-8")).hexdigest()

    overwrite = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            replacement_note,
            "--overwrite-existing-note",
            "--expected-existing-note-sha256",
            original_sha256,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, replacement_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert overwrite.returncode == 0, overwrite.stderr
    payload = json.loads(overwrite.stdout)
    assert payload["overwrote_existing_note"] is True
    assert Path(payload["note_path"]) == note_path
    assert note_path.read_text(encoding="utf-8") == replacement_note
    sidecar = json.loads((note_path.parent / ".deeppapernote.json").read_text(encoding="utf-8"))
    assert sidecar["notes"]["zh-CN"]["note_sha256"] == hashlib.sha256(
        replacement_note.encode("utf-8")
    ).hexdigest()


def test_write_note_blocks_overwrite_when_confirmed_hash_is_stale(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    original_note = "# My Test Paper\n\nOriginal note.\n"
    replacement_note = "# My Test Paper\n\nStale replacement.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            original_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, original_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])

    overwrite = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            replacement_note,
            "--overwrite-existing-note",
            "--expected-existing-note-sha256",
            "b" * 64,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, replacement_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert overwrite.returncode == 2, overwrite.stderr
    conflict = json.loads(overwrite.stdout)
    assert conflict["conflict_code"] == "stale_overwrite_confirmation"
    assert conflict["existing_note_sha256"] == hashlib.sha256(
        original_note.encode("utf-8")
    ).hexdigest()
    assert note_path.read_text(encoding="utf-8") == original_note


def test_write_note_blocks_same_name_directory_for_a_different_source(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    first_note = "# Shared Title\n\nFirst source.\n"
    second_note = "# Shared Title\n\nSecond source.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "Shared Title",
            "--subdir",
            "FirstDomain",
            "--content",
            first_note,
            *source_manifest_args(tmp_path, "a" * 64),
            *formal_save_args(tmp_path, first_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    first_path = Path(json.loads(first.stdout)["note_path"])
    archived_dir = vault / "ArchivedPapers" / first_path.parent.name
    archived_dir.parent.mkdir()
    first_path.parent.rename(archived_dir)
    first_path = archived_dir / first_path.name

    second = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "Shared Title",
            "--subdir",
            "SecondDomain",
            "--language",
            "en",
            "--content",
            second_note,
            *source_manifest_args(tmp_path, "b" * 64),
            *formal_save_args(tmp_path, second_note, "en"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 2, second.stderr
    conflict = json.loads(second.stdout)
    assert conflict["conflict_code"] == "same_name_different_source"
    assert conflict["target_directory"] == str(first_path.parent)
    assert first_path.read_text(encoding="utf-8") == first_note
    assert not (vault / "Research/Papers/SecondDomain").exists()


def test_write_note_freezes_directory_name_for_the_same_source_bytes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    chinese_note = "# First Metadata Title\n\n中文笔记。\n"
    english_note = "# Revised Metadata Title\n\nEnglish note.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "First Metadata Title",
            "--subdir",
            "FirstDomain",
            "--content",
            chinese_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, chinese_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    first_path = Path(json.loads(first.stdout)["note_path"])

    archived_dir = vault / "ArchivedSources" / first_path.parent.name
    archived_dir.parent.mkdir()
    first_path.parent.rename(archived_dir)
    first_path = archived_dir / first_path.name

    second = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "Revised Metadata Title",
            "--subdir",
            "SecondDomain",
            "--language",
            "en",
            "--content",
            english_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, english_note, "en"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 0, second.stderr
    second_path = Path(json.loads(second.stdout)["note_path"])
    assert second_path.parent == first_path.parent
    assert second_path.name == "First_Metadata_Title.en.md"
    assert not (vault / "Research/Papers/SecondDomain/Revised_Metadata_Title").exists()


def test_save_target_preflight_reuses_source_before_note_generation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    chinese_note = "# My Test Paper\n\n中文笔记。\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "OriginalDomain",
            "--content",
            chinese_note,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, chinese_note),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    directory = Path(json.loads(first.stdout)["note_path"]).parent

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "Changed Metadata Title",
            "--subdir",
            "MustNotBeUsed",
            "--language",
            "en",
            *source_manifest_args(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 0, preflight.stderr
    payload = json.loads(preflight.stdout)
    assert payload["status"] == "ok"
    assert payload["phase"] == "save_target_admission"
    assert payload["admission"] == "reuse_source_directory"
    assert payload["domain_routing_skipped"] is True
    assert payload["target_directory"] == str(directory)
    assert Path(payload["note_path"]).name == "My_Test_Paper.en.md"
    assert not Path(payload["note_path"]).exists()


def test_save_target_preflight_reports_same_language_conflict_without_lint(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# My Test Paper\n\nExisting note.\n"

    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            *source_manifest_args(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 2, preflight.stderr
    conflict = json.loads(preflight.stdout)
    assert conflict["conflict_code"] == "same_language_note_exists"
    assert conflict["requires_user_confirmation"] is True


def test_save_target_preflight_honors_recorded_language_note_filename(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# My Test Paper\n\nExisting note.\n"
    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    original_path = Path(json.loads(first.stdout)["note_path"])
    renamed_path = original_path.with_name("Custom Chinese Note.md")
    original_path.rename(renamed_path)
    sidecar_path = renamed_path.parent / ".deeppapernote.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["notes"]["zh-CN"]["filename"] = renamed_path.name
    updated_sidecar_path = sidecar_path.with_name(f"{sidecar_path.name}.tmp")
    updated_sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    os.replace(updated_sidecar_path, sidecar_path)

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            *source_manifest_args(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 2, preflight.stderr
    conflict = json.loads(preflight.stdout)
    assert conflict["conflict_code"] == "same_language_note_exists"
    assert conflict["existing_note_path"] == str(renamed_path)


def test_save_target_preflight_blocks_missing_recorded_language_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# My Test Paper\n\nExisting note.\n"
    first = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    note_path.unlink()

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            *source_manifest_args(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 2, preflight.stderr
    conflict = json.loads(preflight.stdout)
    assert conflict["conflict_code"] == "recorded_language_note_missing"
    assert conflict["target_directory"] == str(note_path.parent)


def test_save_target_preflight_blocks_unidentified_nonempty_same_name_directory(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    legacy_dir = vault / "Research/Papers/Legacy/My_Test_Paper"
    legacy_dir.mkdir(parents=True)
    legacy_note = legacy_dir / "My_Test_Paper.zh-CN.md"
    legacy_note.write_text("# 手工创建的中文笔记\n", encoding="utf-8")
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--language",
            "en",
            *source_manifest_args(tmp_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 2, preflight.stderr
    conflict = json.loads(preflight.stdout)
    assert conflict["conflict_code"] == "unidentified_same_name_directory"
    assert legacy_note.read_text(encoding="utf-8") == "# 手工创建的中文笔记\n"


def test_save_target_preflight_blocks_multiple_directories_for_the_same_source(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    source_sha256 = "a" * 64
    directories = [
        vault / "Research/Papers/One/First_Title",
        vault / "Research/Papers/Two/Second_Title",
    ]
    for index, directory in enumerate(directories, start=1):
        directory.mkdir(parents=True)
        (directory / ".deeppapernote.json").write_text(
            json.dumps(
                {
                    "artifact_type": "deeppapernote_paper_directory",
                    "schema_version": 1,
                    "paper_id": "paper:test",
                    "title": f"Title {index}",
                    "source_sha256": source_sha256,
                    "note_stem": directory.name,
                    "notes": {},
                }
            ),
            encoding="utf-8",
        )
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    preflight = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--preflight",
            "--vault",
            str(vault),
            "--title",
            "Any Title",
            *source_manifest_args(tmp_path, source_sha256),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert preflight.returncode == 2, preflight.stderr
    conflict = json.loads(preflight.stdout)
    assert conflict["conflict_code"] == "multiple_source_directories"
    assert set(conflict["matching_directories"]) == {str(path) for path in directories}


def test_write_note_falls_back_to_workspace(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# Fallback Output Test\n\nThis is a workspace fallback write test.\n"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Fallback Output Test",
            "--content",
            note_text,
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    note_path = Path(payload["note_path"])
    images_dir = Path(payload["images_dir"])
    assert payload["output_mode"] == "workspace"
    assert payload["subdir"] == "机器学习"
    assert note_path == tmp_path / "DeepPaperNote_output" / "机器学习" / "Fallback_Output_Test" / "Fallback_Output_Test.md"
    assert note_path.exists()
    assert images_dir == note_path.parent / "images"
    assert images_dir.exists() and images_dir.is_dir()


def test_write_note_rejects_asset_directory_outside_save_target(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    outside_asset_dir = tmp_path / "outside-assets"

    note_text = "# Unsafe Asset Directory\n"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Unsafe Asset Directory",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
            "--asset-subdir",
            str(outside_asset_dir),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "asset_subdir" in result.stderr
    assert not outside_asset_dir.exists()


def test_materialize_figure_rejects_asset_directory_outside_save_target(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    source_image = tmp_path / "figure.png"
    source_image.write_bytes(b"image")
    outside_asset_dir = tmp_path / "outside-assets"

    result = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZE_SCRIPT),
            "--source-image",
            str(source_image),
            "--title",
            "Unsafe Asset Directory",
            "--asset-subdir",
            str(outside_asset_dir),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "asset_subdir" in result.stderr
    assert not outside_asset_dir.exists()


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks requires extra privileges on Windows")
def test_materialize_figure_rejects_symlink_destination_outside_save_target(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_image = source_dir / "figure.png"
    source_image.write_bytes(b"replacement")
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"original")
    asset_dir = tmp_path / "DeepPaperNote_output/Benchmark/Symlink_Asset/images"
    asset_dir.mkdir(parents=True)
    (asset_dir / "figure.png").symlink_to(outside_image)

    result = subprocess.run(
        [
            sys.executable,
            str(MATERIALIZE_SCRIPT),
            "--source-image",
            str(source_image),
            "--title",
            "Symlink Asset",
            "--subdir",
            "Benchmark",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "asset path" in result.stderr
    assert outside_image.read_bytes() == b"original"


def test_check_environment_reports_workspace_fallback(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [sys.executable, str(ENV_SCRIPT)],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["workspace_fallback"]["available"] is True
    assert payload["workspace_fallback"]["workspace_output_dir"] == "DeepPaperNote_output"


def test_write_note_in_vault_mode_does_not_duplicate_paper_slug(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    note_text = "# My Test Paper\n\nVault write regression test.\n"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--vault",
            str(vault),
            "--title",
            "My Test Paper",
            "--subdir",
            "心理健康/My_Test_Paper",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    note_path = Path(payload["note_path"])
    assert note_path == (
        vault
        / "Research/Papers"
        / "心理健康"
        / "My_Test_Paper"
        / "My_Test_Paper.zh-CN.md"
    )
    assert note_path.exists()


def test_write_note_uses_ready_chinese_obsidian_configuration(
    tmp_path: Path, configured_user_home: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    configured_user_home.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "save_mode": "obsidian",
                "obsidian_vault": str(vault),
                "papers_dir": "Research/Papers",
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    for name in (
        "DEEPPAPERNOTE_OUTPUT_LANGUAGE",
        "DEEPPAPERNOTE_SAVE_MODE",
        "DEEPPAPERNOTE_OBSIDIAN_VAULT",
        "DEEPPAPERNOTE_PAPERS_DIR",
    ):
        env.pop(name, None)

    note_text = "# 配置驱动保存\n\n中文 Obsidian 保存测试。\n"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "配置驱动保存",
            "--subdir",
            "机器学习",
            "--content",
            note_text,
            *source_manifest_args(tmp_path),
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["output_language"] == "zh-CN"
    assert payload["output_mode"] == "obsidian"
    assert Path(payload["note_path"]).is_file()
    assert Path(payload["note_path"]).is_relative_to(vault)


def test_write_note_refuses_when_math_gate_fails(tmp_path: Path) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": False,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Math Gate Test",
            "--content",
            "# Math Gate Test\n\nBody.\n",
            "--lint-json",
            str(lint_path),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "math gate failed" in result.stderr


def test_write_note_rejects_legacy_lint_json_without_output_language_before_save(
    tmp_path: Path,
) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Legacy Lint Test",
            "--content",
            "# Legacy Lint Test\n\nBody.\n",
            "--lint-json",
            str(lint_path),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "lint artifact requires output_language" in result.stderr
    assert not (tmp_path / "DeepPaperNote_output").exists()


def test_write_note_rejects_note_edited_after_final_lint_before_save(
    tmp_path: Path,
) -> None:
    linted_note = "# Final Review Test\n\nLinted body.\n"
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "note_sha256": hashlib.sha256(linted_note.encode("utf-8")).hexdigest(),
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    decisions_args = formal_save_args(tmp_path, linted_note)[2:]

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Final Review Test",
            "--content",
            linted_note.replace("Linted", "Reviewed"),
            "--lint-json",
            str(lint_path),
            *decisions_args,
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "changed after Final Note Lint" in result.stderr
    assert not (tmp_path / "DeepPaperNote_output").exists()


def test_write_note_rejects_mismatched_figure_decisions_before_save_side_effects(
    tmp_path: Path,
) -> None:
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps({"output_language": "en", "decisions": []}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    note_text = "# Language Mismatch\n"
    lint_args = formal_save_args(tmp_path, note_text)[:2]

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Language Mismatch",
            "--content",
            note_text,
            *lint_args,
            "--figure-decisions",
            str(decisions_path),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "does not match resolved output_language zh-CN" in result.stderr
    assert not (tmp_path / "DeepPaperNote_output").exists()


def test_write_note_refuses_when_reference_hygiene_gate_fails(tmp_path: Path) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
                "passes_reference_hygiene_gate": False,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Reference Hygiene Gate Test",
            "--content",
            "# Reference Hygiene Gate Test\n\nBody.\n",
            "--lint-json",
            str(lint_path),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "reference hygiene gate failed" in result.stderr


def test_write_note_refuses_runtime_artifact_reference_without_lint_json(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    note_text = "# Direct Reference Hygiene Test\n\n## 引用\n\n- /private/tmp/dpn-test-runs/candidate/artifacts/llama_source_manifest.json\n"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Direct Reference Hygiene Test",
            "--content",
            note_text,
            *formal_save_args(tmp_path, note_text),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "reference hygiene gate failed" in result.stderr
    assert not (tmp_path / "DeepPaperNote_output").exists()


def test_write_note_requires_integrity_artifacts_before_save(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Missing Integrity Artifacts",
            "--content",
            "# Missing Integrity Artifacts\n",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Final Note Lint" in result.stderr
    assert not (tmp_path / "DeepPaperNote_output").exists()


def test_write_note_refuses_when_figure_gate_fails(tmp_path: Path) -> None:
    lint_path = tmp_path / "lint.json"
    lint_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "passes_basic_structure": True,
                "passes_style_gate": True,
                "passes_math_gate": True,
                "passes_figure_gate": False,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Figure Gate Test",
            "--content",
            "# Figure Gate Test\n\nBody.\n",
            "--lint-json",
            str(lint_path),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "figure gate failed" in result.stderr
