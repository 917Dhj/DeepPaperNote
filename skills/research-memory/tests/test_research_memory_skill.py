from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import memory_format

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
        "Read the vault", "Plan the interview", "Interview in rounds", "Preview, confirm, write", "Report",
    ]
    assert "--dry-run" in text and "--expected-sha256" in text


def test_contract_example_parses_with_the_real_parser() -> None:
    contract = (SKILL_DIR / "references" / "file-contract.md").read_text(encoding="utf-8")
    example = re.search(r"```md\n(.*?)```", contract, flags=re.DOTALL).group(1)
    parsed = memory_format.parse(example)
    assert parsed["language"] == "zh-CN"
    assert [item["text"] for item in parsed["directions"]] == ["用大模型合成心理咨询对话数据，关注数据质量评估"]
    assert [item["text"] for item in parsed["not_focus"]] == ["目标检测"]
    assert memory_format.OBSERVATIONS_NOTE["zh-CN"] in example
    for key, heading in memory_format.HEADINGS["en"].items():
        assert heading in contract
