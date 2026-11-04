"""Every script, option, file, and bundle field the agent-facing docs name must exist.

These checks test what the docs point at, not how they are worded.
"""

from __future__ import annotations

import functools
import re
import subprocess
import sys
from pathlib import Path

import pytest
from build_synthesis_bundle import bundle as build_synthesis_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / "skills" / "deeppapernote"
SCRIPTS_DIR = SKILL_ROOT / "scripts"
REFERENCES_DIR = SKILL_ROOT / "references"
DOCS = {
    path.relative_to(PROJECT_ROOT).as_posix(): path
    for path in (SKILL_ROOT / "SKILL.md", *sorted(REFERENCES_DIR.glob("*.md")))
}

SCRIPT_RE = re.compile(r"scripts/([A-Za-z0-9_]+\.py)")
REFERENCE_RE = re.compile(r"references/([A-Za-z0-9_.-]+\.(?:md|yaml))")
OPTION_RE = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
SUBCOMMAND_RE = re.compile(r"scripts/[A-Za-z0-9_]+\.py\s+([a-z][a-z_-]*)\b")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
FENCE_RE = re.compile(r"```[a-z]*\n(.*?)```", re.DOTALL)
BUNDLE_PATH_RE = re.compile(r"^(?:writing_contract|figure_table_manifest)(?:\.[a-z_]+)+$")

STALE_DOC = """
Run `scripts/plan_figure_table_decisions.py review --decisions X --review-decisions Y`.
```bash
python3 scripts/run_pipeline.py prepare \\
  --workdir run --bogus-flag 1
```
Use `--zotero-mode auto` and `--not-a-flag`.
See `scripts/materialize_figure_asset.py` and `references/workflow.md`.
Read `writing_contract.note_plan_contract.template` and `figure_table_manifest.decisions`.
"""


def code_snippets(text: str) -> list[str]:
    """Return each fenced command, with continuation lines joined, and each inline code span."""
    snippets = []
    for block in FENCE_RE.findall(text):
        snippets.extend(block.replace("\\\n", " ").splitlines())
    snippets.extend(INLINE_CODE_RE.findall(FENCE_RE.sub("", text)))
    return [snippet for snippet in snippets if snippet.strip()]


@functools.cache
def help_text(script: str, subcommand: str = "") -> str:
    command = [sys.executable, str(SCRIPTS_DIR / script)]
    if subcommand:
        result = subprocess.run([*command, subcommand, "--help"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
    return subprocess.run([*command, "--help"], capture_output=True, text=True).stdout


@functools.cache
def all_options() -> frozenset[str]:
    options: set[str] = set()
    for path in SCRIPTS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        options.update(re.findall(r"[\"'](--[a-z][a-z0-9-]*)[\"']", source))
    return frozenset(options)


@functools.cache
def generated_bundle() -> dict:
    identity = {
        "artifact_type": "canonical_identity",
        "schema_version": 2,
        "paper_id": "paper:doc-references",
        "identity_verdict": "accepted",
        "work_level_identity": {"paper_id": "paper:doc-references"},
        "accepted_metadata": {"paper_id": "paper:doc-references"},
    }
    return build_synthesis_bundle(
        metadata={},
        evidence_wrapper={},
        figures_wrapper={"output_language": "zh-CN", "figure_plan": {}},
        assets_wrapper={},
        source_manifest={"identity_contract": identity},
        figure_decisions_wrapper={"output_language": "zh-CN", "decisions": []},
        output_language="zh-CN",
    )


def missing_scripts(text: str) -> list[str]:
    return sorted({name for name in SCRIPT_RE.findall(text) if not (SCRIPTS_DIR / name).is_file()})


def missing_references(text: str) -> list[str]:
    return sorted(
        {name for name in REFERENCE_RE.findall(text) if not (REFERENCES_DIR / name).is_file()}
    )


def missing_options(text: str) -> list[str]:
    missing = set()
    for snippet in code_snippets(text):
        options = OPTION_RE.findall(snippet)
        scripts = SCRIPT_RE.findall(snippet)
        if len(scripts) == 1 and (SCRIPTS_DIR / scripts[0]).is_file():
            subcommand = SUBCOMMAND_RE.search(snippet)
            accepted = help_text(scripts[0], subcommand.group(1) if subcommand else "")
            missing.update(f"{scripts[0]} {opt}" for opt in options if opt not in accepted)
        else:
            missing.update(opt for opt in options if opt not in all_options())
    return sorted(missing)


def missing_bundle_fields(text: str) -> list[str]:
    def resolves(dotted: str) -> bool:
        data: object = generated_bundle()
        for part in dotted.split("."):
            if not isinstance(data, dict) or part not in data:
                return False
            data = data[part]
        return True

    named = {span for span in INLINE_CODE_RE.findall(text) if BUNDLE_PATH_RE.match(span)}
    return sorted(path for path in named if not resolves(path))


def test_checks_catch_stale_pointers() -> None:
    assert missing_scripts(STALE_DOC) == ["materialize_figure_asset.py"]
    assert missing_references(STALE_DOC) == ["workflow.md"]
    assert missing_options(STALE_DOC) == [
        "--not-a-flag",
        "plan_figure_table_decisions.py --review-decisions",
        "run_pipeline.py --bogus-flag",
    ]
    assert missing_bundle_fields(STALE_DOC) == ["figure_table_manifest.decisions"]


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_doc_points_only_at_things_that_exist(doc: str) -> None:
    text = DOCS[doc].read_text(encoding="utf-8")

    assert missing_scripts(text) == []
    assert missing_references(text) == []
    assert missing_options(text) == []
    assert missing_bundle_fields(text) == []


def test_every_reference_file_has_a_pointer() -> None:
    pointed = set()
    for path in DOCS.values():
        pointed.update(REFERENCE_RE.findall(path.read_text(encoding="utf-8")))

    orphans = [path.name for path in REFERENCES_DIR.glob("*.md") if path.name not in pointed]
    assert sorted(orphans) == []
