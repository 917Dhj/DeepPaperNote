from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import domains_file

SKILL_DIR = Path(__file__).resolve().parents[1]
OWN_MODULES = {path.stem for path in (SKILL_DIR / "scripts").glob("*.py")}


def test_scripts_import_only_the_standard_library_and_each_other() -> None:
    for path in sorted((SKILL_DIR / "scripts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                assert name in OWN_MODULES or name in sys.stdlib_module_names or name == "__future__", (
                    f"{path.name} imports {name}"
                )


def test_skill_steps_stay_in_order() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    steps = re.findall(r"^## (\d)\. (.+)$", text, flags=re.MULTILINE)
    assert [title for _, title in steps] == [
        "Read the library", "Agree on the convention", "Plan the changes",
        "Preview, confirm, apply", "Report",
    ]
    assert "--expected-digest" in text and "undo --latest" in text


def test_contract_example_parses_and_renders_back() -> None:
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(encoding="utf-8")
    example = re.search(r"```md\n(.*?)```", contract, flags=re.DOTALL).group(1)
    parsed = domains_file.parse(example)
    assert parsed["language"] == "zh-CN"
    assert parsed["domains"]["长视频理解"]["excludes"] == "短视频动作识别（去 计算机视觉）。"
    rendered = domains_file.render(
        [{"name": "长视频理解", **parsed["domains"]["长视频理解"]}], "zh-CN", "2026-11-07",
    )
    assert rendered == example
    for label in domains_file.LABELS["en"].values():
        assert label in contract
    assert domains_file.NOTE_LINE["en"] in contract
