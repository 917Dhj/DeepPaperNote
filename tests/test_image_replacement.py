"""Formal Save replaces a paper-local image whose bytes changed since the last save."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import write_obsidian_note
from formal_save_helpers import formal_save_args, reviewed_insert_fields
from test_cli_fallback import WRITE_SCRIPT, source_manifest_args

TITLE = "My Test Paper"
NOTE = "# My Test Paper\n\n![Figure 1](images/figure.png)\n"


@pytest.fixture(autouse=True)
def no_shell_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPPAPERNOTE_DISABLE_SHELL_CONFIG", "1")


def save_argv(tmp_path: Path, image_bytes: bytes, language: str, overwrite: Path | None) -> list[str]:
    image = tmp_path / f"crop-{hashlib.sha256(image_bytes).hexdigest()[:8]}.png"
    image.write_bytes(image_bytes)
    decisions_path = tmp_path / "insert-decisions.json"
    decisions_path.write_text(
        json.dumps({
            "output_language": language,
            "decisions": [{
                "source_id": "Figure 1",
                "decision": "insert",
                "source_image_path": str(image),
                "source_image_filename": image.name,
                "vault_image_filename": "figure.png",
                **reviewed_insert_fields(image),
            }],
        }),
        encoding="utf-8",
    )
    argv = [str(WRITE_SCRIPT), "--vault", str(tmp_path / "vault"), "--title", TITLE]
    if language != "zh-CN":
        argv += ["--language", language]
    if overwrite is not None:
        existing_sha256 = hashlib.sha256(overwrite.read_bytes()).hexdigest()
        argv += ["--overwrite-existing-note", "--expected-existing-note-sha256", existing_sha256]
    return [
        *argv,
        *source_manifest_args(tmp_path),
        *formal_save_args(tmp_path, NOTE, language, decisions_path=decisions_path),
    ]


def save(
    tmp_path: Path, image_bytes: bytes, language: str = "zh-CN", overwrite: Path | None = None
) -> dict:
    (tmp_path / "vault").mkdir(exist_ok=True)
    result = subprocess.run(
        [sys.executable, *save_argv(tmp_path, image_bytes, language, overwrite)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def leftover_backups(images_dir: Path) -> list[str]:
    return sorted(path.name for path in images_dir.iterdir() if path.name.endswith(".backup"))


def test_overwrite_replaces_an_image_only_this_note_embeds(tmp_path: Path) -> None:
    first = save(tmp_path, b"old crop")
    note_path = Path(first["note_path"])

    second = save(tmp_path, b"new crop", overwrite=note_path)

    images_dir = note_path.parent / "images"
    assert (images_dir / "figure.png").read_bytes() == b"new crop"
    assert second["replaced_images"] == [{"file": "images/figure.png", "also_embedded_by": []}]
    assert leftover_backups(images_dir) == []


def test_another_language_save_replaces_the_shared_image_and_names_the_sibling(
    tmp_path: Path,
) -> None:
    chinese = Path(save(tmp_path, b"chinese crop")["note_path"])

    english = save(tmp_path, b"english crop", language="en")

    assert Path(english["note_path"]).is_file()
    assert (chinese.parent / "images" / "figure.png").read_bytes() == b"english crop"
    assert english["replaced_images"] == [
        {"file": "images/figure.png", "also_embedded_by": [chinese.name]}
    ]


def test_an_unchanged_image_is_not_reported_as_replaced(tmp_path: Path) -> None:
    note_path = Path(save(tmp_path, b"same crop")["note_path"])

    second = save(tmp_path, b"same crop", overwrite=note_path)

    assert second["replaced_images"] == []


def test_a_failed_save_restores_the_replaced_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note_path = Path(save(tmp_path, b"old crop")["note_path"])
    original_note = note_path.read_bytes()
    monkeypatch.setattr(sys, "argv", save_argv(tmp_path, b"new crop", "zh-CN", note_path))

    def fail_hidden(_path: Path) -> None:
        raise OSError("simulated Hidden attribute failure")

    monkeypatch.setattr(write_obsidian_note, "ensure_sidecar_hidden", fail_hidden)

    with pytest.raises(OSError, match="simulated"):
        write_obsidian_note.main()

    images_dir = note_path.parent / "images"
    assert (images_dir / "figure.png").read_bytes() == b"old crop"
    assert note_path.read_bytes() == original_note
    assert leftover_backups(images_dir) == []
