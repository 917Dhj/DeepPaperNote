from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from organize_helpers import PAPERS, note_text, write

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A small vault with every layout the scan and the plan must handle."""
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    papers = vault / PAPERS
    write(papers / "长视频理解/LVBench/LVBench.zh-CN.md", note_text("LVBench", ["papers/长视频理解"]))
    write(papers / "长视频理解/LVBench/.deeppapernote.json", json.dumps({"title": "LVBench: Long Video"}))
    write(
        papers / "长视频理解/Video_Agent/Video_Agent.md",
        note_text("VideoAgent", ["papers/大模型", "papers/多模态", "video"]),
    )
    write(papers / "长视频理解/TimeSpot/TimeSpot.md", note_text("TimeSpot", ["papers/大模型"]))
    write(papers / "长视频理解/TimeSpot/images/index.md", "index\n")
    (papers / "长视频理解/TimeSpot/images/fig.png").write_bytes(b"png")
    (papers / "长视频理解/Face_Human_Bench.pdf").write_bytes(b"%PDF loose")
    write(
        papers / "大模型/Social_Code/Social_Code.md",
        note_text(
            "Social Code",
            ["papers/大模型"],
            "![[Research/Papers/大模型/Social_Code/images/f.png]]\n"
            "![f](Research/Papers/大模型/Social_Code/images/f%201.png)\n",
        ),
    )
    (papers / "大模型/Social_Code/images").mkdir(parents=True)
    write(papers / "多智能体/Debate/Debate.md", note_text("Debate", None))
    write(
        papers / "LLM智能体/AgentRL/AgentRL.md",
        note_text(
            "AgentRL",
            ["papers/LLM智能体"],
            "See [[Social_Code]] and [[Research/Papers/大模型/Social_Code/Social_Code|Social Code]].\n",
        ),
    )
    write(papers / "Benchmark/SWE_bench/SWE-bench inner/SWE-bench.md", note_text("SWE-bench", ["papers/Benchmark"]))
    (papers / "Benchmark/PDFOnly").mkdir(parents=True)
    (papers / "Benchmark/PDFOnly/paper.pdf").write_bytes(b"%PDF")
    write(papers / "Benchmark/PDFOnly/.deeppapernote.json", json.dumps({"title": "PDF Only Paper"}))
    write(papers / "RootPaper/RootPaper.md", note_text("Root Paper", ["papers/Root"]))
    write(vault / "Daily/today.md", "![[Research/Papers/长视频理解/TimeSpot/images/fig.png]]\n")
    write(
        vault / "DeepPaperNote/research-memory.md",
        "---\ntags: [research-memory]\n---\n\n# 研究记忆\n\n## 我的研究方向\n\n- 长视频理解的记忆机制\n"
        "  - 正在关心的问题：流式记忆\n\n## 不太关心的\n\n- 目标检测\n",
    )
    return vault


@pytest.fixture
def run(tmp_path: Path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_language": "zh-CN", "papers_dir": PAPERS}), encoding="utf-8")

    def invoke(script: str, *args: str, vault: Path | None = None) -> tuple[int, dict]:
        command = [sys.executable, str(SCRIPTS_DIR / script), *args]
        if vault is not None:
            command += ["--vault", str(vault)]
        result = subprocess.run(
            command, capture_output=True, text=True,
            env={"DEEPPAPERNOTE_CONFIG_PATH": str(config), "PATH": "/usr/bin:/bin"},
        )
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = {"stdout": result.stdout, "stderr": result.stderr}
        return result.returncode, payload

    return invoke
