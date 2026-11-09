from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from organize_helpers import PAPERS, snapshot

PLAN = {
    "language": "zh-CN",
    "domains": [
        {"name": "长视频理解", "definition": "理解长视频的模型与基准。", "includes": "长视频问答。",
         "excludes": "短视频动作识别（去 计算机视觉）。", "representative_papers": ["长视频理解/LVBench"]},
        {"name": "LLM智能体", "definition": "大模型智能体。", "includes": "单智能体与多智能体。",
         "excludes": "机器人控制。", "representative_papers": ["LLM智能体/AgentRL", "多智能体/Debate"]},
        {"name": "社会智能", "definition": "模型的社会推理。", "includes": "社会情境理解。",
         "excludes": "情感识别（去 情感计算）。", "representative_papers": ["大模型/Social_Code"]},
        {"name": "Benchmark", "definition": "评测基准。", "includes": "通用基准。", "excludes": "无。",
         "representative_papers": []},
    ],
    "renames": [{"from": "多智能体", "to": "LLM智能体"}],
    "moves": [
        {"paper": "大模型/Social_Code", "to": "社会智能"},
        {"paper": "长视频理解/Face_Human_Bench", "to": "Benchmark"},
        {"paper": "RootPaper", "to": "Benchmark"},
    ],
    "flatten": [{"paper": "Benchmark/SWE_bench"}],
    "wrap": [{"file": "长视频理解/Face_Human_Bench.pdf", "folder": "Face_Human_Bench"}],
    "retag": [{"paper": "长视频理解/Video_Agent"}, {"paper": "长视频理解/TimeSpot"}],
}


def plan_file(tmp_path: Path, plan: dict) -> str:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return str(path)


def preview(run, library, tmp_path, plan=PLAN) -> tuple[int, dict]:
    return run("organize.py", "preview", "--plan", plan_file(tmp_path, plan), vault=library)


def apply(run, library, tmp_path, plan=PLAN, digest: str | None = None) -> tuple[int, dict]:
    if digest is None:
        code, payload = preview(run, library, tmp_path, plan)
        assert code == 0, payload
        digest = payload["plan_digest"]
    return run(
        "organize.py", "apply", "--plan", plan_file(tmp_path, plan), "--expected-digest", digest,
        vault=library,
    )


def tags_of(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").split("---\n")[1].splitlines()
    start = lines.index("tags:")
    tags = []
    for line in lines[start + 1:]:
        if not line.startswith("  - "):
            break
        tags.append(line[4:])
    return tags


def without_logs(files: dict) -> dict:
    return {key: value for key, value in files.items() if "organize-log" not in key}


def test_preview_lists_the_changes_and_writes_nothing(run, library, tmp_path):
    before = snapshot(library)
    code, payload = preview(run, library, tmp_path)
    assert code == 0, payload
    assert payload["status"] == "ok"
    assert len(payload["plan_digest"]) == 64
    summary = payload["summary"]
    assert summary["domains_created"] == ["社会智能"]
    assert sorted(summary["domains_removed"]) == ["多智能体", "大模型"]
    assert summary["moves"] == 4 and summary["flattens"] == 1 and summary["wraps"] == 1
    moves = {item["paper"]: item for item in payload["moves"]}
    assert moves["多智能体/Debate"]["to"] == "LLM智能体/Debate"
    edits = {item["path"]: item["kinds"] for item in payload["edits"]}
    assert edits[f"{PAPERS}/LLM智能体/AgentRL/AgentRL.md"] == ["links"]
    assert "tags" in edits[f"{PAPERS}/社会智能/Social_Code/Social_Code.md"]
    assert "## 社会智能" in payload["domains_file"]["text"]
    assert payload["domains_file"]["exists"] is False
    assert snapshot(library) == before


def test_apply_moves_retags_relinks_and_writes_the_convention(run, library, tmp_path):
    papers = library / PAPERS
    lvbench_before = (papers / "长视频理解/LVBench/LVBench.zh-CN.md").read_bytes()
    debate_before = (papers / "多智能体/Debate/Debate.md").read_bytes()
    code, payload = apply(run, library, tmp_path)
    assert code == 0, payload
    assert payload["verify"]["status"] == "ok", payload["verify"]
    assert not (papers / "大模型").exists() and not (papers / "多智能体").exists()

    social = papers / "社会智能/Social_Code/Social_Code.md"
    assert tags_of(social) == ["papers/社会智能"]
    text = social.read_text(encoding="utf-8")
    assert "![[Research/Papers/社会智能/Social_Code/images/f.png]]" in text
    assert "](Research/Papers/社会智能/Social_Code/images/f%201.png)" in text

    agent = (papers / "LLM智能体/AgentRL/AgentRL.md").read_text(encoding="utf-8")
    assert "[[Social_Code]]" in agent
    assert "[[Research/Papers/社会智能/Social_Code/Social_Code|Social Code]]" in agent
    assert (papers / "LLM智能体/Debate/Debate.md").read_bytes() == debate_before

    assert tags_of(papers / "长视频理解/Video_Agent/Video_Agent.md") == [
        "papers/长视频理解", "大模型", "多模态", "video",
    ]
    assert tags_of(papers / "长视频理解/TimeSpot/TimeSpot.md") == ["papers/长视频理解", "大模型"]
    assert (papers / "长视频理解/LVBench/LVBench.zh-CN.md").read_bytes() == lvbench_before

    assert (papers / "Benchmark/SWE_bench/SWE-bench.md").is_file()
    assert not (papers / "Benchmark/SWE_bench/SWE-bench inner").exists()
    assert (papers / "Benchmark/Face_Human_Bench/Face_Human_Bench.pdf").read_bytes() == b"%PDF loose"
    assert tags_of(papers / "Benchmark/RootPaper/RootPaper.md") == ["papers/Benchmark", "Root"]
    assert (library / "Daily/today.md").read_text(encoding="utf-8") == (
        "![[Research/Papers/长视频理解/TimeSpot/images/fig.png]]\n"
    )

    convention = (library / "DeepPaperNote/domains.md").read_text(encoding="utf-8")
    assert convention.startswith("---\naliases: [领域分类]\ntags: [paper-domains]\nupdated: ")
    assert "## 长视频理解\n\n- 定义：理解长视频的模型与基准。\n" in convention
    assert "- 代表论文：[[LVBench.zh-CN|LVBench: Long Video]]\n" in convention
    assert "- 代表论文：[[AgentRL|AgentRL]]、[[Debate|Debate]]\n" in convention
    assert [line[3:] for line in convention.splitlines() if line.startswith("## ")] == [
        "长视频理解", "LLM智能体", "社会智能", "Benchmark",
    ]

    log = json.loads(Path(payload["log"]).read_text(encoding="utf-8"))
    assert log["undone"] is False and log["papers_dir"] == PAPERS
    assert {step["kind"] for step in log["steps"]} >= {"mkdir", "move", "edit", "rmdir"}


def test_undo_restores_the_library_byte_for_byte(run, library, tmp_path):
    before = snapshot(library)
    code, payload = apply(run, library, tmp_path)
    assert code == 0, payload
    code, undone = run("organize.py", "undo", "--latest", vault=library)
    assert code == 0, undone
    assert without_logs(snapshot(library)) == before
    assert not (library / PAPERS / "社会智能").exists()
    assert json.loads(Path(payload["log"]).read_text(encoding="utf-8"))["undone"] is True
    code, again = run("organize.py", "undo", "--latest", vault=library)
    assert code == 1 and again["status"] == "refused"


def test_undo_refuses_when_a_touched_file_changed(run, library, tmp_path):
    code, payload = apply(run, library, tmp_path)
    assert code == 0, payload
    agent = library / PAPERS / "LLM智能体/AgentRL/AgentRL.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\nMy edit.\n", encoding="utf-8")
    after = snapshot(library)
    code, undone = run("organize.py", "undo", "--latest", vault=library)
    assert code == 1
    assert any("AgentRL.md" in error for error in undone["errors"])
    assert snapshot(library) == after


def test_apply_refuses_a_stale_preview(run, library, tmp_path):
    code, payload = preview(run, library, tmp_path)
    social = library / PAPERS / "大模型/Social_Code/Social_Code.md"
    social.write_text(social.read_text(encoding="utf-8") + "\nNew line.\n", encoding="utf-8")
    before = snapshot(library)
    code, result = apply(run, library, tmp_path, digest=payload["plan_digest"])
    assert code == 1 and result["status"] == "refused"
    assert snapshot(library) == before


def edited(change) -> dict:
    plan = copy.deepcopy(PLAN)
    change(plan)
    return plan


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        (lambda p: p["moves"].append({"paper": "长视频理解/Missing", "to": "Benchmark"}), "长视频理解/Missing"),
        (lambda p: p["moves"].append({"paper": "长视频理解/TimeSpot", "to": "计算机视觉"}), "计算机视觉"),
        (lambda p: p["domains"].pop(), "Benchmark"),
        (lambda p: p["domains"].append({"name": "a b", "definition": "x", "includes": "x", "excludes": "x",
                                         "representative_papers": []}), "a b"),
        (lambda p: p["domains"][3]["representative_papers"].append("Benchmark/PDFOnly"), "Benchmark/PDFOnly"),
        (lambda p: p["moves"].append({"paper": "长视频理解/LVBench", "to": "LLM智能体"}), None),
    ],
)
def test_preview_refuses_an_invalid_plan(run, library, tmp_path, change, needle):
    if needle is None:
        (library / PAPERS / "LLM智能体/LVBench").mkdir()
        needle = "LLM智能体/LVBench"
    before = snapshot(library)
    code, payload = preview(run, library, tmp_path, edited(change))
    assert code == 1 and payload["status"] == "refused"
    assert any(needle in error for error in payload["errors"]), payload["errors"]
    assert snapshot(library) == before


def test_notes_without_frontmatter_are_never_edited(run, library, tmp_path):
    plan = edited(lambda p: p["retag"].append({"paper": "多智能体/Debate"}))
    code, payload = preview(run, library, tmp_path, plan)
    assert code == 0, payload
    assert not any(item["path"].endswith("Debate.md") for item in payload["edits"])


@pytest.mark.skipif(os.name == "nt", reason="the test holds the lock with fcntl")
def test_apply_waits_for_the_deeppapernote_lock(run, library, tmp_path):
    import fcntl

    code, payload = preview(run, library, tmp_path)
    before = snapshot(library)
    with (library / ".deeppapernote.lock").open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        code, result = run(
            "organize.py", "apply", "--plan", plan_file(tmp_path, PLAN),
            "--expected-digest", payload["plan_digest"], "--lock-timeout", "0.3", vault=library,
        )
    assert code == 1 and any("lock" in error for error in result["errors"])
    assert snapshot(library) == before


def test_verify_finds_a_link_left_on_an_old_path(run, library, tmp_path):
    code, payload = apply(run, library, tmp_path)
    assert code == 0, payload
    (library / "Daily/new.md").write_text("[[Research/Papers/大模型/Social_Code/Social_Code]]\n", encoding="utf-8")
    code, result = run("organize.py", "verify", vault=library)
    assert result["status"] == "issues"
    assert any("Daily/new.md" in issue for issue in result["issues"])


def test_flatten_with_retag_fixes_the_nested_note(run, library, tmp_path):
    inner = library / PAPERS / "Benchmark/SWE_bench/SWE-bench inner/SWE-bench.md"
    inner.write_text(inner.read_text(encoding="utf-8").replace("papers/Benchmark", "papers/benchmark"), encoding="utf-8")
    plan = edited(lambda p: p["retag"].append({"paper": "Benchmark/SWE_bench"}))
    code, payload = apply(run, library, tmp_path, plan)
    assert code == 0, payload
    assert tags_of(library / PAPERS / "Benchmark/SWE_bench/SWE-bench.md") == ["papers/Benchmark", "benchmark"]
