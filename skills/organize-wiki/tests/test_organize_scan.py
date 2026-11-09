from __future__ import annotations

from pathlib import Path

from organize_helpers import PAPERS, snapshot, write


def scan(run, library: Path) -> dict:
    code, payload = run("scan_library.py", vault=library)
    assert code == 0, payload
    return payload


def by_id(payload: dict) -> dict:
    return {paper["id"]: paper for paper in payload["papers"]}


def test_scan_lists_domains_and_papers(run, library):
    payload = scan(run, library)
    assert payload["status"] == "ok"
    assert payload["language"] == "zh-CN"
    domains = {item["name"]: item for item in payload["domains"]}
    assert set(domains) == {"长视频理解", "大模型", "多智能体", "LLM智能体", "Benchmark"}
    assert domains["长视频理解"]["paper_count"] == 3
    assert domains["长视频理解"]["in_convention"] is False
    papers = by_id(payload)
    assert papers["长视频理解/LVBench"]["title"] == "LVBench: Long Video"
    assert papers["长视频理解/LVBench"]["has_sidecar"] is True
    assert papers["长视频理解/LVBench"]["notes"] == ["LVBench.zh-CN.md"]
    assert papers["长视频理解/LVBench"]["excerpt"] == "LVBench abstract."
    assert papers["Benchmark/PDFOnly"]["pdf_only"] is True
    assert papers["Benchmark/PDFOnly"]["title"] == "PDF Only Paper"


def test_scan_reports_tag_status(run, library):
    papers = by_id(scan(run, library))
    assert papers["长视频理解/LVBench"]["tag_status"] == "ok"
    assert papers["长视频理解/Video_Agent"]["tag_status"] == "multiple"
    assert papers["长视频理解/Video_Agent"]["papers_tags"] == ["papers/大模型", "papers/多模态"]
    assert papers["长视频理解/TimeSpot"]["tag_status"] == "mismatch"
    assert papers["多智能体/Debate"]["tag_status"] == "no_frontmatter"
    assert papers["Benchmark/PDFOnly"]["tag_status"] == "no_note"


def test_scan_reports_anomalies(run, library):
    anomalies = {(item["kind"], item["path"]) for item in scan(run, library)["anomalies"]}
    assert anomalies == {
        ("paper_at_root", "RootPaper"),
        ("loose_file", "长视频理解/Face_Human_Bench.pdf"),
        ("nested_folder", "Benchmark/SWE_bench/SWE-bench inner"),
        ("images_index", "长视频理解/TimeSpot/images/index.md"),
    }


def test_scan_reads_the_domains_file_and_research_memory(run, library):
    write(
        library / "DeepPaperNote/domains.md",
        "﻿---\naliases: [领域分类]\n---\n# 领域分类\n\n## 长视频理解\n\n- 定义：长视频。\n- 收录：长视频问答。\n\n"
        "## Agents\n\n- Definition: LLM agents.\n- Excludes: robotics.\n",
    )
    payload = scan(run, library)
    convention = payload["domains_file"]
    assert convention["exists"] is True and len(convention["sha256"]) == 64
    assert list(convention["domains"]) == ["长视频理解", "Agents"]
    assert convention["domains"]["长视频理解"] == {"definition": "长视频。", "includes": "长视频问答。"}
    assert convention["domains"]["Agents"]["excludes"] == "robotics."
    domains = {item["name"]: item for item in payload["domains"]}
    assert domains["长视频理解"]["in_convention"] is True
    assert payload["research_memory"] == {
        "exists": True, "directions": ["长视频理解的记忆机制"], "not_focus": ["目标检测"],
    }


def test_scan_is_read_only(run, library):
    before = snapshot(library)
    scan(run, library)
    assert snapshot(library) == before


def test_scan_needs_a_vault(run, tmp_path):
    code, payload = run("scan_library.py")
    assert payload["status"] == "needs_vault"
    plain = tmp_path / "plain"
    plain.mkdir()
    code, payload = run("scan_library.py", vault=plain)
    assert payload["status"] == "not_a_vault"


def test_scan_reads_the_configured_papers_dir(run, library):
    payload = scan(run, library)
    assert payload["papers_dir"] == PAPERS


def test_notes_in_a_nested_folder_count_for_the_paper(run, library):
    inner = library / PAPERS / "Benchmark/SWE_bench/SWE-bench inner/SWE-bench.md"
    inner.write_text(inner.read_text(encoding="utf-8").replace("papers/Benchmark", "papers/benchmark"), encoding="utf-8")
    paper = by_id(scan(run, library))["Benchmark/SWE_bench"]
    assert paper["tag_status"] == "mismatch"
    assert paper["papers_tags"] == ["papers/benchmark"]
    assert paper["title"] == "SWE-bench"
    assert paper["pdf_only"] is False
