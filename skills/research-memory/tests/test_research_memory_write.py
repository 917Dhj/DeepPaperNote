from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_research_memory.py"

CONTENT = {
    "directions": [{"text": "用大模型合成心理咨询对话数据", "details": ["正在关心的问题：共情评估"]}],
    "not_focus": [{"text": "目标检测"}],
    "observations": [{"text": "最近读的多是指令数据合成", "evidence": ["Self_Instruct.zh-CN"]}],
}


@pytest.fixture
def library(vault: Path, note) -> Path:
    note("AI/Self_Instruct", "Self_Instruct.zh-CN", title="Self-Instruct", frontmatter="tags: [papers/AI]\n")
    return vault


def memory(vault: Path) -> Path:
    return vault / "DeepPaperNote" / "research-memory.md"


def write(tmp_path: Path, vault: Path, mode: str, payload: dict, expected: str, *extra: str) -> subprocess.CompletedProcess:
    data = tmp_path / f"{mode}.json"
    data.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--vault", str(vault), f"--{mode}", str(data),
         "--expected-sha256", expected, "--today", "2026-11-06", *extra],
        capture_output=True, text=True,
        # cp1252 stands in for a Windows console, where non-ASCII output fails.
        env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"},
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_create_writes_the_file_with_resolved_evidence_titles(tmp_path: Path, library: Path) -> None:
    result = write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok" and payload["written"] is True
    text = memory(library).read_text(encoding="utf-8")
    assert "  - 依据：[[Self_Instruct.zh-CN|Self-Instruct]]\n" in text
    assert payload["sha256_after"] == sha(memory(library))


def test_dry_run_previews_without_writing(tmp_path: Path, library: Path) -> None:
    result = write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN", "--dry-run")
    payload = json.loads(result.stdout)
    assert result.returncode == 0 and payload["written"] is False
    assert "## 我的研究方向" in payload["text"] and "+- 用大模型合成心理咨询对话数据" in payload["diff"]
    assert not memory(library).exists()


def test_create_refuses_when_the_file_already_exists(tmp_path: Path, library: Path) -> None:
    write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    result = write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "refused"


def test_unknown_evidence_target_is_refused(tmp_path: Path, library: Path) -> None:
    content = {**CONTENT, "observations": [{"text": "x", "evidence": ["No_Such_Paper.zh-CN"]}]}
    result = write(tmp_path, library, "create", content, "absent", "--language", "zh-CN")
    assert result.returncode != 0
    assert "No_Such_Paper.zh-CN" in json.loads(result.stdout)["reason"]
    assert not memory(library).exists()


def test_update_applies_changes_when_the_hash_matches(tmp_path: Path, library: Path) -> None:
    write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    before = sha(memory(library))
    changes = {"operations": [{"op": "add", "section": "directions", "text": "指令数据的自动构造"}]}
    result = write(tmp_path, library, "update", changes, before)
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["sha256_before"] == before
    assert "+- 指令数据的自动构造" in payload["diff"]
    assert "- 指令数据的自动构造\n" in memory(library).read_text(encoding="utf-8")


def test_update_refuses_after_a_hand_edit_during_the_interview(tmp_path: Path, library: Path) -> None:
    write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    before = sha(memory(library))
    memory(library).write_text(memory(library).read_text(encoding="utf-8") + "\n我刚手动加的一行\n", encoding="utf-8")
    edited = memory(library).read_bytes()
    result = write(tmp_path, library, "update", {"operations": []}, before)
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "refused"
    assert memory(library).read_bytes() == edited


def test_update_with_a_bad_match_writes_nothing(tmp_path: Path, library: Path) -> None:
    write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    before_bytes = memory(library).read_bytes()
    changes = {"operations": [{"op": "remove", "section": "directions", "match": "没有这一条"}]}
    result = write(tmp_path, library, "update", changes, sha(memory(library)))
    assert result.returncode != 0
    assert memory(library).read_bytes() == before_bytes


def test_update_resolves_new_observation_evidence(tmp_path: Path, library: Path) -> None:
    write(tmp_path, library, "create", CONTENT, "absent", "--language", "zh-CN")
    changes = {"observations": [{"text": "新的观察", "evidence": ["Self_Instruct.zh-CN"]}]}
    result = write(tmp_path, library, "update", changes, sha(memory(library)))
    assert result.returncode == 0, result.stdout
    assert "- 新的观察\n  - 依据：[[Self_Instruct.zh-CN|Self-Instruct]]\n" in memory(library).read_text(encoding="utf-8")
