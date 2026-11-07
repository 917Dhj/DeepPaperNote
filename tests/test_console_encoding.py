"""Scripts print to a console whose encoding may not cover Chinese, such as cp1252 on Windows."""

from __future__ import annotations

import ast
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


def _is_non_ascii_dumps(node: ast.AST) -> bool:
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, (ast.Attribute, ast.Name))
        and getattr(call.func, "attr", getattr(call.func, "id", "")) == "dumps"
        and any(
            keyword.arg == "ensure_ascii" and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in call.keywords
        )
        for call in ast.walk(node)
    )


def _is_stdout_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "print" and not any(keyword.arg == "file" for keyword in call.keywords)
    return (
        isinstance(func, ast.Attribute) and func.attr == "write"
        and isinstance(func.value, ast.Attribute) and func.value.attr == "stdout"
    )


def stdout_non_ascii_json(source: str) -> list[int]:
    """Lines that print `json.dumps(..., ensure_ascii=False)` output, directly or through a name."""
    lines = []
    for scope in ast.walk(ast.parse(source)):
        if not isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = {
            target.id
            for node in ast.walk(scope) if isinstance(node, ast.Assign) and _is_non_ascii_dumps(node.value)
            for target in node.targets if isinstance(target, ast.Name)
        }
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and _is_stdout_call(node):
                for arg in node.args:
                    used = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
                    if _is_non_ascii_dumps(arg) or used & names:
                        lines.append(node.lineno)
    return sorted(set(lines))


def test_the_stdout_check_finds_both_shapes():
    direct = "import json, sys\nsys.stdout.write(json.dumps({}, ensure_ascii=False))\n"
    named = "import json\ndef emit(p):\n    text = json.dumps(p, ensure_ascii=False)\n    print(text)\n"
    to_file = "import json\ndef emit(p, f):\n    text = json.dumps(p, ensure_ascii=False)\n    f.write(text)\n"
    assert stdout_non_ascii_json(direct) == [2]
    assert stdout_non_ascii_json(named) == [4]
    assert stdout_non_ascii_json(to_file) == []


def test_no_script_prints_non_ascii_json():
    offenders = {
        str(path.relative_to(PROJECT_ROOT)): lines
        for path in sorted((PROJECT_ROOT / "skills").glob("*/scripts/*.py"))
        if (lines := stdout_non_ascii_json(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, (
        "Print ASCII JSON to stdout (json.dumps without ensure_ascii=False); "
        f"a cp1252 console cannot encode the rest: {offenders}"
    )
