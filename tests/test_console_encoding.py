"""Scripts print to a console whose encoding may not cover Chinese, such as cp1252 on Windows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"
CP1252 = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}


def run_python(code: str, scripts: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, *args], capture_output=True, text=True, env=CP1252, cwd=scripts,
    )


def test_emit_prints_json_a_cp1252_console_can_read():
    result = run_python("import common; common.emit({'domain': '长视频理解'})", SCRIPTS)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"domain": "长视频理解"}


def test_glossary_emit_prints_json_a_cp1252_console_can_read():
    glossary = PROJECT_ROOT / "skills" / "paper-glossary" / "scripts"
    for code in (
        "import glossary_common; glossary_common.emit({'term': '注意力'})",
        "import configure_glossary; configure_glossary._emit({'term': '注意力'}, '')",
    ):
        result = run_python(code, glossary)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"term": "注意力"}


def test_run_state_prints_json_a_cp1252_console_can_read(tmp_path):
    workdir = tmp_path / "运行目录"
    workdir.mkdir()
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_state.py"), "status", "--workdir", str(workdir), "--prefix", "run"],
        capture_output=True, text=True, env=CP1252,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["workdir"] == str(workdir.resolve())


def test_pipeline_paths_print_as_utf8():
    result = subprocess.run(
        [sys.executable, "-c", "import run_pipeline; run_pipeline.print_outputs([('workdir', '/tmp/运行')])"],
        capture_output=True, env=CP1252, cwd=SCRIPTS,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.decode("utf-8").strip() == "workdir=/tmp/运行"
