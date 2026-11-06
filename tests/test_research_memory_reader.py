from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_synthesis_bundle
import research_memory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = PROJECT_ROOT / "skills" / "research-memory" / "references" / "file-contract.md"

ZH_MEMORY = """---
aliases: [研究记忆]
tags: [research-memory]
updated: 2026-11-06
---

# 研究记忆

## 我的研究方向

我自己补的一段说明。

- 用大模型合成心理咨询对话数据
  - 正在关心的问题：如何自动评估共情程度
- 指令数据的自动构造

## 不太关心的

- 目标检测

## 阅读观察

- 最近读的多是指令数据合成
"""


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    return root


def write_memory(vault: Path, text: str) -> Path:
    path = vault / "DeepPaperNote" / "research-memory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def config(vault: Path, mode: str = "obsidian") -> dict:
    return {"save_mode": mode, "obsidian_vault": str(vault), "papers_dir": "Papers"}


def test_directions_are_read_with_their_details(vault: Path) -> None:
    path = write_memory(vault, ZH_MEMORY)
    result = research_memory.read_research_memory(config(vault), "zh-CN")
    assert result["status"] == "ok"
    assert result["path"] == str(path.resolve())
    assert result["directions"] == [
        {"text": "用大模型合成心理咨询对话数据", "details": ["正在关心的问题：如何自动评估共情程度"]},
        {"text": "指令数据的自动构造", "details": []},
    ]
    assert result["suggested_reader_research_direction"] == (
        "用大模型合成心理咨询对话数据（正在关心的问题：如何自动评估共情程度）；指令数据的自动构造"
    )


def test_english_headings_and_suggestion(vault: Path) -> None:
    write_memory(vault, "# Research Memory\n\n## my research directions\n\n- LLM data synthesis\n  - Now: quality checks\n* Agents\n")
    result = research_memory.read_research_memory(config(vault), "en")
    assert [item["text"] for item in result["directions"]] == ["LLM data synthesis", "Agents"]
    assert result["suggested_reader_research_direction"] == "LLM data synthesis (Now: quality checks); Agents"


def test_only_the_directions_section_is_read(vault: Path) -> None:
    write_memory(vault, ZH_MEMORY)
    texts = {item["text"] for item in research_memory.read_research_memory(config(vault), "zh-CN")["directions"]}
    assert "目标检测" not in texts and "最近读的多是指令数据合成" not in texts


def test_missing_file(vault: Path) -> None:
    assert research_memory.read_research_memory(config(vault), "zh-CN") == {
        "status": "missing", "path": str((vault / "DeepPaperNote" / "research-memory.md").resolve()),
        "directions": [], "suggested_reader_research_direction": "",
    }


@pytest.mark.parametrize("text", ["# 研究记忆\n\n## 阅读观察\n\n- x\n", "# 研究记忆\n\n## 我的研究方向\n\n只有一段话，没有条目。\n"])
def test_no_direction_items_is_empty(vault: Path, text: str) -> None:
    write_memory(vault, text)
    result = research_memory.read_research_memory(config(vault), "zh-CN")
    assert (result["status"], result["directions"]) == ("empty", [])


def test_workspace_mode_reads_nothing(vault: Path) -> None:
    write_memory(vault, ZH_MEMORY)
    result = research_memory.read_research_memory(config(vault, "workspace"), "zh-CN")
    assert (result["status"], result["path"], result["directions"]) == ("workspace", "", [])


def test_unreadable_file_is_treated_as_empty(vault: Path) -> None:
    path = write_memory(vault, "")
    path.write_bytes(b"\xff\xfe\x00broken")
    assert research_memory.read_research_memory(config(vault), "zh-CN")["status"] == "empty"


def test_reader_agrees_with_the_skill_contract_example(vault: Path) -> None:
    example = re.search(r"```md\n(.*?)```", CONTRACT.read_text(encoding="utf-8"), flags=re.DOTALL).group(1)
    write_memory(vault, example)
    result = research_memory.read_research_memory(config(vault), "zh-CN")
    assert result["directions"] == [
        {"text": "用大模型合成心理咨询对话数据，关注数据质量评估", "details": ["正在关心的问题：如何自动评估共情程度"]}
    ]


def test_bundle_carries_research_memory(vault: Path, monkeypatch) -> None:
    write_memory(vault, ZH_MEMORY)
    monkeypatch.setattr(build_synthesis_bundle, "runtime_config", lambda **_: {**config(vault), "output_language": "zh-CN"})
    synthesis = build_synthesis_bundle.bundle(
        metadata={"title": "Paper"},
        evidence_wrapper={"evidence_pack": {}},
        figures_wrapper={"output_language": "zh-CN", "figure_plan": {}},
        assets_wrapper={},
        figure_decisions_wrapper={"output_language": "zh-CN", "decisions": []},
        source_manifest={
            "identity_contract": {
                "artifact_type": "canonical_identity", "schema_version": 2, "paper_id": "paper:x",
                "identity_verdict": "accepted", "work_level_identity": {"title": "Paper"},
                "accepted_metadata": {"title": "Paper"},
            },
        },
    )
    assert synthesis["research_memory"]["status"] == "ok"
    assert synthesis["research_memory"]["suggested_reader_research_direction"].startswith("用大模型合成心理咨询对话数据")
    takeaways = synthesis["writing_contract"]["takeaways_contract"]
    assert takeaways["reader_context_fallback"] == "research_memory.suggested_reader_research_direction"
