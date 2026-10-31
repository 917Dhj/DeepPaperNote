from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from common import normalize_whitespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"
EXPECTATIONS_DIR = PROJECT_ROOT / "evals" / "expectations"
PAPERS_DIR = PROJECT_ROOT / "evals" / "papers"
EXPECTATION_FIELDS = {
    "schema_version",
    "pdf",
    "sha256",
    "split",
    "source",
    "traits",
    "labels",
    "captions",
    "review",
    "same_visual",
    "known_gaps",
}
LANGUAGE = "zh-CN"


def load_expectations() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(EXPECTATIONS_DIR.glob("*.json"))
    }


EXPECTATIONS = load_expectations()


def check_ids(expectation: dict) -> list[str]:
    return [
        "sha256",
        "labels:missing",
        "labels:extra",
        *(f"caption:{label}" for label in expectation["captions"]),
        *(f"review:{label}" for label in expectation["review"]),
        *(f"same_visual:{'|'.join(pair)}" for pair in expectation["same_visual"]),
    ]


def gap_reason(expectation: dict, check: str) -> str | None:
    for pattern, reason in expectation["known_gaps"].items():
        if fnmatch.fnmatchcase(check, pattern):
            return reason
    return None


def corpus_params() -> list:
    params = []
    for paper, expectation in EXPECTATIONS.items():
        split_mark = pytest.mark.corpus
        if expectation["split"] == "holdout":
            split_mark = pytest.mark.corpus_holdout
        marks = [split_mark]
        for check in check_ids(expectation):
            reason = gap_reason(expectation, check)
            if reason:
                marks_for_check = [*marks, pytest.mark.xfail(strict=True, reason=reason)]
            else:
                marks_for_check = marks
            params.append(pytest.param(paper, check, marks=marks_for_check, id=f"{paper}:{check}"))
    return params


def run_step(script: str, env: dict[str, str], *arguments: object) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *map(str, arguments)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )


def run_preparation(pdf_path: Path, workdir: Path, env: dict[str, str]) -> dict:
    """Run the offline stages after acquisition, so results depend only on the PDF."""
    workdir.mkdir()
    fetch = workdir / "fetch.json"
    fetch.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "fetch_pdf.py",
                "paper_id": f"corpus:{pdf_path.stem}",
                "title": pdf_path.stem,
                "pdf_path": str(pdf_path),
                "identity_contract": {
                    "artifact_type": "canonical_identity",
                    "schema_version": 2,
                    "paper_id": f"corpus:{pdf_path.stem}",
                    "identity_verdict": "accepted",
                    "work_level_identity": {"title": pdf_path.stem},
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = workdir / "run_source_manifest.json"
    evidence = workdir / "evidence.json"
    assets = workdir / "assets.json"
    figures = workdir / "figures.json"
    decisions = workdir / "decisions.json"
    run_step("extract_source_text.py", env, "--input", fetch, "--output", manifest)
    run_step(
        "extract_evidence.py",
        env,
        "--input",
        fetch,
        "--source-manifest",
        manifest,
        "--output",
        evidence,
    )
    run_step(
        "extract_pdf_assets.py",
        env,
        "--input",
        fetch,
        "--assets-dir",
        workdir / "assets",
        "--output",
        assets,
    )
    run_step(
        "plan_figures.py",
        env,
        "--evidence",
        evidence,
        "--assets",
        assets,
        "--language",
        LANGUAGE,
        "--output",
        figures,
    )
    run_step(
        "plan_figure_table_decisions.py",
        env,
        "--source-manifest",
        manifest,
        "--figures",
        figures,
        "--assets",
        assets,
        "--language",
        LANGUAGE,
        "--output",
        decisions,
    )
    captions: dict[str, list[str]] = {}
    source_captions = json.loads(manifest.read_text(encoding="utf-8"))["captions"]
    for item in source_captions["figures"] + source_captions["tables"]:
        captions.setdefault(item["id"], []).append(normalize_whitespace(item["caption"]))
    return {
        "captions": captions,
        "decisions": {
            item["source_id"]: item["decision"]
            for item in json.loads(decisions.read_text(encoding="utf-8"))["decisions"]
        },
    }


@pytest.fixture(scope="session")
def corpus_runs(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("paper-corpus")
    config = root / "config.json"
    config.write_text(
        json.dumps({"output_language": LANGUAGE, "save_mode": "workspace"}), encoding="utf-8"
    )
    env = {
        **os.environ,
        "DEEPPAPERNOTE_CONFIG_PATH": str(config),
        "DEEPPAPERNOTE_DISABLE_SHELL_CONFIG": "1",
    }
    runs: dict[str, dict] = {}

    def run(paper: str) -> dict:
        if paper not in runs:
            pdf_path = PAPERS_DIR / EXPECTATIONS[paper]["pdf"]
            runs[paper] = run_preparation(pdf_path, root / paper, env)
        return runs[paper]

    return run


@pytest.mark.parametrize(("paper", "check"), corpus_params())
def test_paper_corpus(paper: str, check: str, corpus_runs) -> None:
    expectation = EXPECTATIONS[paper]
    pdf_path = PAPERS_DIR / expectation["pdf"]
    if not pdf_path.is_file():
        pytest.skip(f"{pdf_path} is not available locally.")
    kind, _, target = check.partition(":")
    if kind == "sha256":
        digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        assert digest == expectation["sha256"], "The local PDF differs from the expected file."
        return
    run = corpus_runs(paper)
    if check == "labels:missing":
        assert sorted(set(expectation["labels"]) - set(run["captions"])) == []
    elif check == "labels:extra":
        assert sorted(set(run["captions"]) - set(expectation["labels"])) == []
    elif kind == "caption":
        expected = expectation["captions"][target]
        assert any(
            caption.startswith(expected["starts"]) and caption.endswith(expected["ends"])
            for caption in run["captions"].get(target, [])
        ), run["captions"].get(target, [])
    elif kind == "review":
        assert run["decisions"].get(target) == "review_pending"
    else:
        assert len(set(target.split("|")) & set(run["decisions"])) == 1


def test_expectations_are_well_formed() -> None:
    assert EXPECTATIONS
    for paper, expectation in EXPECTATIONS.items():
        assert set(expectation) == EXPECTATION_FIELDS, paper
        assert expectation["schema_version"] == 1, paper
        assert Path(expectation["pdf"]).name == expectation["pdf"], paper
        assert re.fullmatch(r"[0-9a-f]{64}", expectation["sha256"]), paper
        assert expectation["split"] in {"dev", "holdout"}, paper
        assert set(expectation["captions"]) <= set(expectation["labels"]), paper
        assert all(
            set(item) == {"starts", "ends"} and all(item.values())
            for item in expectation["captions"].values()
        ), paper
        assert all(len(pair) == 2 for pair in expectation["same_visual"]), paper
        checks = check_ids(expectation)
        for pattern, reason in expectation["known_gaps"].items():
            assert reason.strip(), (paper, pattern)
            assert any(fnmatch.fnmatchcase(check, pattern) for check in checks), (paper, pattern)
