"""The model chooses the domain folder; the save script validates the choice."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from formal_save_helpers import formal_save_args

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / "skills" / "deeppapernote"
WRITE_SCRIPT = SKILL_ROOT / "scripts" / "write_obsidian_note.py"
PAPERS = Path("Research/Papers")


def make_paper(domain_dir: Path, folder: str, title: str) -> None:
    paper = domain_dir / folder
    paper.mkdir(parents=True)
    (paper / f"{folder}.md").write_text(f"# {title}\n\nBody.\n", encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    papers = root / PAPERS
    make_paper(papers / "长视频理解", "LVBench", "LVBench: An Extreme Long Video Benchmark")
    make_paper(papers / "长视频理解", "Video_Agent", "VideoAgent: Long-form Video Understanding")
    make_paper(papers / "心理健康", "ChatMind", "A Chatbot for Depression")
    return root


def run_writer(tmp_path: Path, vault: Path, *extra: str, preflight: bool = True,
               note_text: str = "", title: str = "Streaming Video Memory") -> tuple:
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(json.dumps({
        "status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64,
    }), encoding="utf-8")
    command = [
        sys.executable, str(WRITE_SCRIPT),
        "--save-mode", "obsidian", "--vault", str(vault), "--papers-dir", str(PAPERS),
        "--title", title, "--language", "zh-CN", "--source-manifest", str(manifest),
        *extra,
    ]
    if preflight:
        command.append("--preflight")
    else:
        command += formal_save_args(tmp_path, note_text, source_manifest_path=manifest, domain=None)
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    result = subprocess.run(command, capture_output=True, text=True, env=env, cwd=tmp_path)
    payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
    return result, payload


def note(tag_lines: str) -> str:
    return f"---\ntags:\n{tag_lines}aliases:\n  - SVM\n---\n# Streaming Video Memory\n\nBody.\n"


def overview_by_name(payload: dict) -> dict:
    return {item["name"]: item for item in payload["domain_overview"]["domains"]}


def test_new_paper_without_a_domain_is_blocked_with_the_domain_overview(tmp_path, vault):
    before = sorted(p.relative_to(vault) for p in vault.rglob("*"))
    result, payload = run_writer(tmp_path, vault)
    assert result.returncode == 2, result.stdout + result.stderr
    assert payload["status"] == "blocked"
    assert payload["phase"] == "save_target_admission"
    assert payload["conflict_code"] == "domain_required"
    overview = payload["domain_overview"]
    assert overview["source"] == "folders"
    domains = overview_by_name(payload)
    assert set(domains) == {"长视频理解", "心理健康"}
    assert domains["长视频理解"]["paper_count"] == 2
    assert domains["长视频理解"]["sample_titles"] == [
        "LVBench: An Extreme Long Video Benchmark",
        "VideoAgent: Long-form Video Understanding",
    ]
    assert sorted(p.relative_to(vault) for p in vault.rglob("*")) == before


def test_choosing_an_existing_domain_admits_a_new_directory_there(tmp_path, vault):
    result, payload = run_writer(tmp_path, vault, "--domain", "长视频理解")
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["admission"] == "new_directory"
    assert payload["domain"] == "长视频理解"
    assert payload["new_domain"] is False
    assert Path(payload["target_directory"]) == (
        vault / PAPERS / "长视频理解" / "Streaming_Video_Memory"
    )


def test_a_new_domain_needs_a_reason(tmp_path, vault):
    result, payload = run_writer(tmp_path, vault, "--domain", "视频记忆")
    assert result.returncode == 2
    assert payload["conflict_code"] == "new_domain_reason_required"
    assert "domain_overview" in payload
    result, payload = run_writer(
        tmp_path, vault, "--domain", "视频记忆",
        "--new-domain-reason", "现有领域都不收录流式视频的记忆机制。",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["new_domain"] is True
    assert payload["new_domain_reason"] == "现有领域都不收录流式视频的记忆机制。"
    assert not (vault / PAPERS / "视频记忆").exists()


@pytest.mark.parametrize("name", ["a/b", "..", ".hidden", "视频 记忆", "#标签", "2024", "LVBench"])
def test_invalid_new_domain_names_are_refused(tmp_path, vault, name):
    (vault / PAPERS / "LVBench").mkdir()
    (vault / PAPERS / "LVBench" / ".deeppapernote.json").write_text("{}", encoding="utf-8")
    result, payload = run_writer(
        tmp_path, vault, "--domain", name, "--new-domain-reason", "No domain fits.",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert payload["conflict_code"] == "domain_name_invalid"


def test_a_domain_named_like_the_paper_still_gets_a_paper_folder(tmp_path, vault):
    result, payload = run_writer(
        tmp_path, vault, "--domain", "Streaming_Video_Memory",
        "--new-domain-reason", "No domain fits.",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(payload["target_directory"]) == (
        vault / PAPERS / "Streaming_Video_Memory" / "Streaming_Video_Memory"
    )


def test_an_existing_paper_directory_wins_and_needs_no_domain(tmp_path, vault):
    folder = vault / "Elsewhere" / "Streaming_Video_Memory"
    folder.mkdir(parents=True)
    result, payload = run_writer(tmp_path, vault)
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["admission"] == "reuse_empty_same_name_directory"
    assert payload["domain_routing_skipped"] is True
    assert Path(payload["target_directory"]) == folder


def test_the_domains_file_defines_the_overview(tmp_path, vault):
    convention = vault / "DeepPaperNote" / "domains.md"
    convention.parent.mkdir()
    convention.write_text(
        "﻿---\naliases: [领域分类]\n---\n# 领域分类\n\n"
        "## 长视频理解\n\n- 定义：理解长视频的模型与基准。\n- 收录：长视频问答、长视频基准。\n"
        "- 不收录：短视频动作识别（去计算机视觉）。\n- 代表论文：[[LVBench]]\n\n"
        "## Video Memory\n\n- Definition: Memory for streaming video.\n"
        "- Includes: memory banks for video agents.\n- Excludes: text-only memory.\n",
        encoding="utf-8",
    )
    result, payload = run_writer(tmp_path, vault)
    assert result.returncode == 2
    overview = payload["domain_overview"]
    assert overview["source"] == "domains_file"
    assert Path(overview["domains_file"]) == convention
    domains = overview_by_name(payload)
    assert domains["长视频理解"]["definition"] == "理解长视频的模型与基准。"
    assert domains["长视频理解"]["excludes"] == "短视频动作识别（去计算机视觉）。"
    assert domains["长视频理解"]["paper_count"] == 2
    assert domains["长视频理解"]["on_disk"] and domains["长视频理解"]["in_convention"]
    assert domains["Video Memory"]["includes"] == "memory banks for video agents."
    assert domains["Video Memory"]["on_disk"] is False
    assert domains["心理健康"]["in_convention"] is False
    assert domains["心理健康"]["sample_titles"] == ["A Chatbot for Depression"]
    result, payload = run_writer(tmp_path, vault, "--domain", "Video Memory")
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["new_domain"] is False


def test_formal_save_requires_one_papers_tag_matching_the_domain(tmp_path, vault):
    choice = ("--domain", "长视频理解")
    for tags in ("  - papers/心理健康\n", "  - papers/长视频理解\n  - papers/多模态\n", ""):
        result, _ = run_writer(tmp_path, vault, *choice, preflight=False, note_text=note(tags))
        assert result.returncode != 0
        assert "papers/长视频理解" in result.stdout + result.stderr
    result, payload = run_writer(
        tmp_path, vault, *choice, preflight=False,
        note_text=note("  - papers/长视频理解\n  - video-memory\n"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["domain"] == "长视频理解"
    assert Path(payload["note_path"]).parent.parent == vault / PAPERS / "长视频理解"


def test_a_reused_directory_tags_its_own_domain(tmp_path, vault):
    folder = vault / PAPERS / "心理健康" / "Streaming_Video_Memory"
    folder.mkdir()
    result, _ = run_writer(
        tmp_path, vault, preflight=False, note_text=note("  - papers/长视频理解\n"),
    )
    assert result.returncode != 0
    result, payload = run_writer(
        tmp_path, vault, preflight=False, note_text=note("  - papers/心理健康\n"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(payload["note_path"]).parent == folder


def test_workspace_save_also_requires_a_domain(tmp_path):
    workspace = tmp_path / "workspace"
    make_paper(workspace / "DeepPaperNote_output" / "长视频理解", "LVBench", "LVBench")
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(json.dumps({
        "status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64,
    }), encoding="utf-8")
    base = [
        sys.executable, str(WRITE_SCRIPT), "--save-mode", "workspace",
        "--title", "Streaming Video Memory", "--language", "zh-CN",
        "--source-manifest", str(manifest),
    ]
    text = note("  - papers/长视频理解\n")
    result = subprocess.run(
        base + formal_save_args(tmp_path, text, source_manifest_path=manifest, domain=None),
        capture_output=True, text=True, cwd=workspace,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["conflict_code"] == "domain_required"
    assert [d["name"] for d in payload["domain_overview"]["domains"]] == ["长视频理解"]
    result = subprocess.run(
        base + ["--domain", "长视频理解"]
        + formal_save_args(tmp_path, text, source_manifest_path=manifest, domain=None),
        capture_output=True, text=True, cwd=workspace,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    saved = Path(json.loads(result.stdout)["note_path"])
    assert saved.parent.parent == (workspace / "DeepPaperNote_output" / "长视频理解").resolve()


def test_workspace_preflight_chooses_the_domain(tmp_path):
    workspace = tmp_path / "workspace"
    make_paper(workspace / "DeepPaperNote_output" / "长视频理解", "LVBench", "LVBench")
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(json.dumps({
        "status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64,
    }), encoding="utf-8")
    command = [
        sys.executable, str(WRITE_SCRIPT), "--save-mode", "workspace", "--preflight",
        "--title", "Streaming Video Memory", "--language", "zh-CN",
        "--source-manifest", str(manifest),
    ]
    result = subprocess.run(command, capture_output=True, text=True, cwd=workspace)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["conflict_code"] == "domain_required"
    result = subprocess.run(
        command + ["--domain", "长视频理解"], capture_output=True, text=True, cwd=workspace,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["domain"] == "长视频理解"
    assert payload["admission"] == "workspace"
    assert not (workspace / "DeepPaperNote_output" / "长视频理解" / "Streaming_Video_Memory").exists()


def test_keyword_domain_rules_are_gone():
    assert not (SKILL_ROOT / "references" / "domain_rules.yaml").exists()
    import _note_paths

    for name in ("infer_domain_label", "domain_name_score", "load_domain_rules"):
        assert not hasattr(_note_paths, name)
