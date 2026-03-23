from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "scripts" / "write_obsidian_note.py"
ENV_SCRIPT = PROJECT_ROOT / "scripts" / "check_environment.py"


def test_write_note_falls_back_to_workspace(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env.pop("READ_ARXIV_OBSIDIAN_VAULT", None)
    env["DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR"] = "DeepPaperNote_output"
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            str(WRITE_SCRIPT),
            "--title",
            "Fallback Output Test",
            "--content",
            "# Fallback Output Test\n\nThis is a workspace fallback write test.\n",
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


def test_check_environment_reports_workspace_fallback(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    env.pop("READ_ARXIV_OBSIDIAN_VAULT", None)
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
