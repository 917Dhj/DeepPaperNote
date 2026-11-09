from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import aggregate_reading
import memory_vault

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aggregate_reading.py"
ZH_GUIDANCE = "> [!note] 这一节留给你自己：写下你的判断、它和你研究的联系、想验证的点。重新生成这篇笔记时，这一节会原样保留。"


def structured(paper_type: str, methods: str, datasets: str, tasks: str, read_date: str, domain: str = "AI") -> str:
    return (
        f"tags: [papers/{domain}]\npaper_type: {paper_type}\nmethods: {methods}\n"
        f"datasets: {datasets}\ntasks: {tasks}\nread_date: {read_date}\n"
    )


@pytest.fixture
def library(vault: Path, note) -> Path:
    note("AI/Self_Instruct", "Self_Instruct.zh-CN", title="Self-Instruct",
         frontmatter=structured("AI_method", '["[[instruction tuning]]", data synthesis]', "[SuperNI]",
                                "[instruction following]", "2026-10-20"),
         body=("## 阅读收获\n\n### 可迁移\n\n- 判断：自举生成的思路可以迁移到咨询对话合成，前提是有种子对话。\n"
               "- 通用条目。\n\n## 关联\n\n## 我的笔记\n\n" + ZH_GUIDANCE + "\n\n我想把它用在心理咨询数据上。\n"))
    note("AI/Self_Instruct", "Self_Instruct.en", title="Self-Instruct",
         frontmatter=structured("AI_method", "[data synthesis]", "[SuperNI]", "[instruction following]", "2026-10-20"))
    note("AI/Alpaca", "Alpaca.zh-CN", title="Stanford Alpaca",
         frontmatter=structured("AI_method", "[data synthesis, distillation]", "[]", "[instruction following]", "2026-09-02"),
         body="## 我的笔记\n\n" + ZH_GUIDANCE + "\n")
    note("Psych/Counsel", "Counsel.zh-CN", title="Counseling Dialogues",
         frontmatter=structured("benchmark_or_dataset", "[]", "[CounselChat]", "[empathy evaluation]", "2025-12-01", "Psych"))
    note("Old/Legacy", "Legacy.zh-CN", title="An Old Note",
         frontmatter="tags: [papers/Old]\ndate: 2020\n",
         body="## 我的笔记\n\n旧笔记里我写过的想法。\n")
    (vault / "Papers" / "AI" / "README.md").write_text("no frontmatter here\n", encoding="utf-8")
    return vault


def run(vault: Path, **kwargs) -> dict:
    return aggregate_reading.aggregate(vault, "Papers", language=kwargs.pop("language", "zh-CN"), today="2026-11-06")


def test_papers_are_counted_once_per_directory_and_language_picks_the_target(library: Path) -> None:
    result = run(library)
    targets = {paper["target"] for paper in result["papers"]}
    assert targets == {"Self_Instruct.zh-CN", "Alpaca.zh-CN", "Counsel.zh-CN", "Legacy.zh-CN"}
    english = aggregate_reading.aggregate(library, "Papers", language="en", today="2026-11-06")
    assert "Self_Instruct.en" in {paper["target"] for paper in english["papers"]}
    assert (result["paper_count"], result["structured_count"], result["legacy_count"]) == (4, 3, 1)
    assert result["legacy_targets"] == ["Legacy.zh-CN"]


def test_counts_name_the_notes_behind_each_value(library: Path) -> None:
    aggregates = run(library)["aggregates"]
    methods = {item["value"]: item for item in aggregates["methods"]}
    assert methods["data synthesis"]["count"] == 2
    assert methods["data synthesis"]["targets"] == ["Alpaca.zh-CN", "Self_Instruct.zh-CN"]
    assert "instruction tuning" in methods  # a wikilink value counts by its text
    assert aggregates["methods"][0]["value"] == "data synthesis"  # most frequent first
    assert {item["value"]: item["count"] for item in aggregates["domains"]} == {"AI": 2, "Psych": 1, "Old": 1}
    assert {item["value"]: item["count"] for item in aggregates["paper_types"]} == {"AI_method": 2, "benchmark_or_dataset": 1}


def test_reading_by_month_and_recent_window(library: Path) -> None:
    result = run(library)
    assert result["aggregates"]["by_month"] == {"2025-12": 1, "2026-09": 1, "2026-10": 1}
    assert result["aggregates"]["recent_90_days"] == {"count": 2, "targets": ["Alpaca.zh-CN", "Self_Instruct.zh-CN"]}


def test_user_notes_and_judgments_are_collected(library: Path) -> None:
    papers = {paper["target"]: paper for paper in run(library)["papers"]}
    assert papers["Self_Instruct.zh-CN"]["my_notes"] == "我想把它用在心理咨询数据上。"
    assert papers["Self_Instruct.zh-CN"]["judgments"] == ["判断：自举生成的思路可以迁移到咨询对话合成，前提是有种子对话。"]
    assert papers["Alpaca.zh-CN"]["my_notes"] == ""  # only the default guidance
    assert papers["Legacy.zh-CN"]["my_notes"] == "旧笔记里我写过的想法。"
    assert run(library)["aggregates"]["with_my_notes"] == ["Legacy.zh-CN", "Self_Instruct.zh-CN"]


def test_enough_reading_needs_five_papers(library: Path, note) -> None:
    assert run(library)["enough_reading"] is False
    note("AI/Fifth", "Fifth.zh-CN", title="Fifth", frontmatter="tags: [papers/AI]\n")
    assert run(library)["enough_reading"] is True


def test_existing_memory_is_reported_with_its_hash(library: Path) -> None:
    assert run(library)["memory"] == {
        "path": str(library / "DeepPaperNote" / "research-memory.md"), "exists": False, "sha256": "",
        "language": None, "directions": [], "not_focus": [], "observations": [],
    }
    memory = library / "DeepPaperNote" / "research-memory.md"
    memory.parent.mkdir()
    memory.write_text("# 研究记忆\n\n## 我的研究方向\n\n- 方向一\n", encoding="utf-8")
    reported = run(library)["memory"]
    assert reported["exists"] is True and len(reported["sha256"]) == 64
    assert reported["directions"] == [{"text": "方向一", "details": []}]


def test_the_memory_folder_is_never_read_as_papers(library: Path) -> None:
    memory = library / "Papers" / "DeepPaperNote"
    memory.mkdir()
    (memory / "research-memory.md").write_text("---\ntags: [research-memory]\n---\n# 研究记忆\n", encoding="utf-8")
    assert "research-memory" not in {paper["target"] for paper in run(library)["papers"]}


# --- configuration --------------------------------------------------------------


def write_config(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "dpn-config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_vault_comes_from_the_deeppapernote_configuration(tmp_path: Path, library: Path) -> None:
    config = write_config(tmp_path, {"obsidian_vault": str(library), "papers_dir": "Papers", "output_language": "en"})
    assert memory_vault.locate(config_path=config) == {
        "status": "ok", "vault": str(library.resolve()), "papers_dir": "Papers", "language": "en",
    }


def test_missing_configuration_asks_for_the_vault(tmp_path: Path) -> None:
    assert memory_vault.locate(config_path=tmp_path / "missing.json")["status"] == "needs_vault"


def test_explicit_vault_overrides_the_configuration(tmp_path: Path, library: Path) -> None:
    located = memory_vault.locate(vault=str(library), papers_dir="Papers", config_path=tmp_path / "missing.json")
    assert (located["status"], located["language"]) == ("ok", "zh-CN")


def test_a_folder_without_obsidian_is_not_a_vault(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert memory_vault.locate(vault=str(plain), config_path=tmp_path / "missing.json")["status"] == "not_a_vault"


def test_cli_writes_the_aggregate(tmp_path: Path, library: Path) -> None:
    env = {**os.environ, "DEEPPAPERNOTE_CONFIG_PATH": str(write_config(tmp_path, {"obsidian_vault": str(library), "papers_dir": "Papers"}))}
    output = tmp_path / "aggregate.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "--today", "2026-11-06", "--output", str(output)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ok" and payload["paper_count"] == 4


def test_cli_without_a_vault_reports_needs_vault(tmp_path: Path) -> None:
    env = {**os.environ, "DEEPPAPERNOTE_CONFIG_PATH": str(tmp_path / "missing.json")}
    result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "needs_vault"


def test_cli_prints_json_a_windows_console_can_read(tmp_path: Path, library: Path) -> None:
    env = {
        **os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0",
        "DEEPPAPERNOTE_CONFIG_PATH": str(write_config(tmp_path, {"obsidian_vault": str(library), "papers_dir": "Papers"})),
    }
    result = subprocess.run([sys.executable, str(SCRIPT), "--today", "2026-11-06"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["paper_count"] == 4
