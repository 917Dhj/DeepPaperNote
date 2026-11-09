from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import _final_quality
import build_synthesis_bundle
import lint_grounding
import lint_note
import pytest
import vault_connections
from formal_save_helpers import formal_save_args
from localization import note_schema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"


def write_note(vault: Path, rel_dir: str, stem: str, frontmatter: str, title: str) -> Path:
    path = vault / "Papers" / rel_dir / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n\n# {title}\n", encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / ".obsidian").mkdir(parents=True)
    write_note(
        root,
        "AI/Super_NaturalInstructions",
        "Super_NaturalInstructions.zh-CN",
        "doi: 10.18653/v1/2022.emnlp-main.340\naliases: [Super-NaturalInstructions]\n"
        "methods: [instruction tuning]\ndatasets: [SuperNI]\ntasks: []\n",
        "Super-NaturalInstructions: Generalization via Declarative Instructions",
    )
    write_note(
        root,
        "AI/Super_NaturalInstructions",
        "Super_NaturalInstructions.en",
        "doi: 10.18653/v1/2022.emnlp-main.340\naliases: [Super-NaturalInstructions]\n",
        "Super-NaturalInstructions: Generalization via Declarative Instructions",
    )
    write_note(
        root,
        "AI/InstructGPT",
        "InstructGPT.en",
        "arxiv_id: 2203.02155\naliases: [InstructGPT]\nmethods: [RLHF, instruction tuning]\n"
        "datasets: []\ntasks: [instruction following]\n",
        "Training Language Models to Follow Instructions with Human Feedback",
    )
    write_note(
        root,
        "AI/Alpaca",
        "Alpaca.zh-CN",
        'aliases: [Alpaca]\nmethods: ["[[self-instruct data]]", knowledge distillation]\n'
        "datasets: []\ntasks: []\n",
        "Stanford Alpaca",
    )
    write_note(
        root,
        "AI/Unrelated",
        "Unrelated.zh-CN",
        "methods: [transformer]\ndatasets: []\ntasks: []\n",
        "An Unrelated Vision Paper",
    )
    write_note(
        root,
        "AI/Self_Instruct",
        "Self_Instruct.zh-CN",
        "doi: 10.18653/v1/2023.acl-long.754\nmethods: [instruction tuning]\ndatasets: [SuperNI]\n",
        "Self-Instruct",
    )
    return root


def config(vault: Path, mode: str = "obsidian") -> dict:
    return {
        "save_mode": mode,
        "obsidian_vault": str(vault),
        "papers_dir": "Papers",
        "output_language": "zh-CN",
    }


REFERENCES = [
    {
        "raw_text": "Wang et al. 2022. Super-NaturalInstructions: Generalization via Declarative Instructions on 1600+ NLP Tasks. EMNLP. doi:10.18653/v1/2022.emnlp-main.340",
        "display_text": "Wang et al. 2022. Super-NaturalInstructions",
    },
    {
        "raw_text": "Ouyang et al. 2022. Training language models to follow instructions with human feedback. arXiv:2203.02155",
        "display_text": "Ouyang et al. 2022",
    },
    {"raw_text": "Smith 2020. Something not in the vault.", "display_text": "Smith 2020"},
]

FULL_TEXT = (
    "We use instruction tuning and compare against RLHF trained models on instruction following. "
    "We evaluate on SuperNI. Knowledge distillation is not used."
)


def candidates(vault: Path, language: str = "zh-CN", **kwargs) -> dict:
    own = vault / "Papers" / "AI" / "Self_Instruct"
    return vault_connections.connection_candidates(
        config(vault, kwargs.pop("mode", "obsidian")),
        REFERENCES if "references" not in kwargs else kwargs.pop("references"),
        FULL_TEXT if "full_text" not in kwargs else kwargs.pop("full_text"),
        language,
        own_directory=own,
    )


# --- recall ------------------------------------------------------------------


def test_cited_candidates_match_by_doi_and_arxiv_and_merge_languages(vault: Path) -> None:
    result = candidates(vault)
    assert result["status"] == "ok"
    cited = {item["target"]: item for item in result["cited"]}
    assert set(cited) == {"Super_NaturalInstructions.zh-CN", "InstructGPT.en"}
    assert cited["Super_NaturalInstructions.zh-CN"]["match_reason"] == "doi"
    assert cited["InstructGPT.en"]["match_reason"] == "arxiv_id"
    assert (
        cited["InstructGPT.en"]["title"]
        == "Training Language Models to Follow Instructions with Human Feedback"
    )


def test_english_run_prefers_the_english_note(vault: Path) -> None:
    targets = {item["target"] for item in candidates(vault, language="en")["cited"]}
    assert "Super_NaturalInstructions.en" in targets


def test_own_paper_directory_is_never_a_candidate(vault: Path) -> None:
    refs = REFERENCES + [
        {
            "raw_text": "Wang et al. 2023. Self-Instruct. doi:10.18653/v1/2023.acl-long.754",
            "display_text": "Self-Instruct",
        }
    ]
    result = candidates(vault, references=refs)
    all_targets = {item["target"] for item in result["cited"] + result["related"]}
    assert "Self_Instruct.zh-CN" not in all_targets


def test_reference_matching_two_different_papers_is_dropped(vault: Path) -> None:
    write_note(
        vault,
        "AI/Other_Copy",
        "Other_Copy.zh-CN",
        "doi: 10.18653/v1/2022.emnlp-main.340\n",
        "A second paper claiming the same DOI",
    )
    targets = {item["target"] for item in candidates(vault)["cited"]}
    assert "Super_NaturalInstructions.zh-CN" not in targets


def test_cited_candidates_are_capped_at_thirty(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    refs = []
    for i in range(35):
        write_note(root, f"AI/P{i}", f"P{i}.zh-CN", f"doi: 10.1000/paper{i}\n", f"Paper {i}")
        refs.append({"raw_text": f"Ref {i}. doi:10.1000/paper{i}", "display_text": f"Ref {i}"})
    result = vault_connections.connection_candidates(
        config(root), refs, "", "zh-CN", own_directory=None
    )
    assert len(result["cited"]) == 30


def test_related_needs_two_values_or_one_dataset_or_task(vault: Path) -> None:
    related = {item["target"]: item for item in candidates(vault, references=[])["related"]}
    # SuperNI is a dataset hit: one is enough.
    assert "Super_NaturalInstructions.zh-CN" in related
    # RLHF + instruction tuning (+ a task): qualifies.
    assert "InstructGPT.en" in related
    # Alpaca: only "knowledge distillation" matches -> one method value is not enough.
    assert "Alpaca.zh-CN" not in related
    assert "Unrelated.zh-CN" not in related
    assert related["Super_NaturalInstructions.zh-CN"]["matched_values"]["datasets"] == ["SuperNI"]


def test_wikilink_valued_properties_match_by_their_text(vault: Path) -> None:
    text = FULL_TEXT + " We reuse self-instruct data with knowledge distillation."
    related = {
        item["target"] for item in candidates(vault, references=[], full_text=text)["related"]
    }
    assert "Alpaca.zh-CN" in related


def test_title_match_survives_pdf_line_break_hyphenation(vault: Path) -> None:
    refs = [
        {
            "raw_text": "Long Ouyang, Jeff Wu, et al. 2022. Training Language Models to Follow Instruc- tions "
            "with Human Feedback. In NeurIPS.",
            "display_text": "Ouyang et al. 2022",
        }
    ]
    cited = {
        item["target"]: item["match_reason"] for item in candidates(vault, references=refs)["cited"]
    }
    assert cited == {"InstructGPT.en": "title_or_alias"}


def test_short_alias_still_needs_word_boundaries(vault: Path) -> None:
    refs = [
        {
            "raw_text": "Someone 2021. Alpacas and llamas in the wild.",
            "display_text": "Someone 2021",
        }
    ]
    assert candidates(vault, references=refs)["cited"] == []


def test_cited_papers_are_not_repeated_as_related(vault: Path) -> None:
    result = candidates(vault)
    cited = {item["target"] for item in result["cited"]}
    related = {item["target"] for item in result["related"]}
    assert not cited & related


def test_related_candidates_are_capped_at_fifteen(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    for i in range(20):
        write_note(root, f"AI/R{i}", f"R{i}.zh-CN", "datasets: [SuperNI]\n", f"Related {i}")
    result = vault_connections.connection_candidates(
        config(root), [], "We use SuperNI.", "zh-CN", own_directory=None
    )
    assert len(result["related"]) == 15


def test_workspace_mode_recalls_nothing(vault: Path) -> None:
    result = candidates(vault, mode="workspace")
    assert result == {"status": "workspace", "cited": [], "related": []}


def test_missing_vault_is_reported(tmp_path: Path) -> None:
    result = vault_connections.connection_candidates(
        config(tmp_path / "missing"), REFERENCES, FULL_TEXT, "zh-CN", own_directory=None
    )
    assert result == {"status": "vault_unavailable", "cited": [], "related": []}


def test_bundle_carries_connection_candidates_instead_of_references() -> None:
    contract = build_synthesis_bundle.compact_writing_contract("zh-CN")
    assert "connections_contract" in contract
    connections = contract["connections_contract"]
    assert connections["section"] == "关联"
    assert connections["subsections"] == ["库内笔记", "关键前置文献"]
    assert connections["max_in_vault"] == 8
    assert connections["key_prior_work_items"] == {"min": 3, "max": 5}
    assert set(connections["relation_labels"]) == {
        "baseline",
        "extends",
        "extended_by",
        "same_task",
        "same_benchmark",
        "shared_method",
        "conflicting_findings",
    }


# --- note plan and grounding --------------------------------------------------

KEY_PRIOR = [
    {"work": "Wang et al. 2022. Super-NaturalInstructions", "role": "数据来源"},
    {"work": "Ouyang et al. 2022. InstructGPT", "role": "基线"},
    {"work": "Brown et al. 2020. GPT-3", "role": "骨干模型"},
]
CONNECTION = {
    "target": "InstructGPT.en",
    "relation": "baseline",
    "reason": "本文直接拿它作为主要对照模型。",
}


def bundle_with(targets: list[str], status: str = "ok") -> dict:
    return {
        "connection_candidates": {
            "status": status,
            "cited": [{"target": t} for t in targets],
            "related": [],
        }
    }


def plan_with(**overrides) -> dict:
    from test_lint_grounding import grounded_note_plan

    plan = grounded_note_plan()
    plan["key_prior_work"] = KEY_PRIOR
    plan["connections"] = [CONNECTION]
    plan.update(overrides)
    return plan


def plan_codes(plan: dict, bundle: dict | None = None) -> set[str]:
    from test_lint_grounding import source_manifest

    issues = lint_grounding.validate_note_plan(plan, source_manifest(), "zh-CN")
    issues += lint_grounding.validate_bundle_contract(
        plan, bundle if bundle is not None else bundle_with(["InstructGPT.en"])
    )
    return {item["code"] for item in issues}


def test_valid_connection_plan_has_no_connection_issues() -> None:
    codes = plan_codes(plan_with())
    assert not {code for code in codes if "connection" in code or "key_prior_work" in code}


@pytest.mark.parametrize("count", [2, 6])
def test_key_prior_work_holds_three_to_five(count: int) -> None:
    assert "note_plan_key_prior_work_count_invalid" in plan_codes(
        plan_with(key_prior_work=(KEY_PRIOR * 2)[:count])
    )


def test_key_prior_work_items_need_work_and_role() -> None:
    bad = KEY_PRIOR[:2] + [{"work": "Brown et al. 2020", "role": ""}]
    assert "note_plan_key_prior_work_item_invalid" in plan_codes(plan_with(key_prior_work=bad))


def test_connections_may_be_empty() -> None:
    codes = plan_codes(plan_with(connections=[]), bundle_with([], status="workspace"))
    assert not {code for code in codes if "connection" in code}


def test_connections_are_capped_at_eight() -> None:
    many = [dict(CONNECTION, target=f"P{i}") for i in range(9)]
    assert "note_plan_connections_count_invalid" in plan_codes(
        plan_with(connections=many), bundle_with([f"P{i}" for i in range(9)])
    )


def test_connection_relation_must_be_a_known_key() -> None:
    assert "note_plan_connection_relation_invalid" in plan_codes(
        plan_with(connections=[dict(CONNECTION, relation="inspired_by")])
    )


def test_connection_needs_a_reason() -> None:
    assert "note_plan_connection_item_invalid" in plan_codes(
        plan_with(connections=[dict(CONNECTION, reason=" ")])
    )


def test_connection_target_must_be_a_bundle_candidate() -> None:
    assert "note_plan_connection_target_unknown" in plan_codes(
        plan_with(), bundle_with(["Someone_Else.zh-CN"])
    )


def test_duplicate_connection_targets_are_rejected() -> None:
    assert "note_plan_connection_duplicate" in plan_codes(
        plan_with(connections=[CONNECTION, CONNECTION])
    )


# --- Final Note Lint ----------------------------------------------------------

ZH_GUIDANCE = note_schema("zh-CN")["my_notes_guidance"]


def connections_section(entries: list[str] | None = None, prior: int = 3, empty: str = "") -> str:
    entries = (
        entries
        if entries is not None
        else ["- [[InstructGPT.en|InstructGPT]]（基线/对比）：本文直接拿它作为主要对照模型。"]
    )
    lines = ["## 关联", "", "### 库内笔记", ""]
    lines += entries if entries else [empty or "库里暂无相关笔记"]
    lines += ["", "### 关键前置文献", ""]
    lines += [f"- Author{i} et al. 202{i}. Some prior work {i}（基线）" for i in range(prior)]
    lines += ["", "## 我的笔记", "", ZH_GUIDANCE, ""]
    return "\n".join(lines)


def note_with(section_text: str) -> str:
    from test_lint_note import _valid_note_text

    head = (
        _valid_note_text().split("## 引用", 1)[0]
        if "## 引用" in _valid_note_text()
        else _valid_note_text().split("## 关联", 1)[0]
    )
    return head + section_text


def connection_reasons(text: str, connections: list[dict] | None = None) -> set[str]:
    plan = {"connections": [CONNECTION] if connections is None else connections}
    return {str(item["reason"]) for item in lint_note.inspect_connections(text, plan)}


@pytest.fixture(autouse=True)
def zh_profile():
    lint_note.configure_output_language("zh-CN")
    yield
    lint_note.configure_output_language("zh-CN")


def test_valid_connections_section_passes() -> None:
    assert connection_reasons(note_with(connections_section())) == set()


def test_connections_need_both_subsections() -> None:
    text = note_with(connections_section()).replace("### 关键前置文献", "### 其他")
    assert "connections_subsection_missing" in connection_reasons(text)


def test_entry_must_follow_the_fixed_format() -> None:
    text = note_with(connections_section(["- [[InstructGPT.en|InstructGPT]] 是本文的基线。"]))
    assert "connections_entry_invalid" in connection_reasons(text)


def test_entry_label_must_match_the_planned_relation() -> None:
    text = note_with(
        connections_section(["- [[InstructGPT.en|InstructGPT]]（同一任务）：都做指令跟随。"])
    )
    assert "connections_relation_mismatch" in connection_reasons(text)


def test_entry_targets_must_equal_planned_connections() -> None:
    text = note_with(
        connections_section(
            [
                "- [[InstructGPT.en|InstructGPT]]（基线/对比）：主要对照。",
                "- [[Alpaca.zh-CN|Alpaca]]（同一任务）：也做指令跟随。",
            ]
        )
    )
    assert "connections_targets_mismatch_plan" in connection_reasons(text)


def test_empty_vault_section_uses_a_fixed_sentence() -> None:
    assert connection_reasons(note_with(connections_section([])), connections=[]) == set()
    assert (
        connection_reasons(
            note_with(connections_section([], empty="当前为 workspace 模式，未连接知识库")),
            connections=[],
        )
        == set()
    )
    bad = note_with(connections_section([], empty="暂时没有找到"))
    assert "connections_empty_statement_invalid" in connection_reasons(bad, connections=[])


@pytest.mark.parametrize("count", [2, 6])
def test_key_prior_work_section_holds_three_to_five(count: int) -> None:
    assert "key_prior_work_count_invalid" in connection_reasons(
        note_with(connections_section(prior=count))
    )


def test_english_entry_format() -> None:
    lint_note.configure_output_language("en")
    text = (
        "## Connections\n\n### In Your Vault\n\n"
        "- [[InstructGPT.en|InstructGPT]] (baseline): The paper compares against it directly.\n\n"
        "### Key Prior Work\n\n- A 2020. One (backbone)\n- B 2021. Two (baseline)\n- C 2022. Three (data source)\n\n"
        "## My Notes\n\n" + note_schema("en")["my_notes_guidance"] + "\n"
    )
    assert {
        str(i["reason"]) for i in lint_note.inspect_connections(text, {"connections": [CONNECTION]})
    } == set()


def test_connections_section_is_exempt_from_mixed_language_checks() -> None:
    assert lint_note.mixed_language_issues(note_with(connections_section())) == []


# --- Final Quality Review v3 --------------------------------------------------


def quality_plan(connections: list | None = None) -> dict:
    return {
        "output_language": "en",
        "central_claims": [{"claim": "c", "what_it_does_not_prove": "d"}],
        "storyline": "The paper takes on one problem. It answers with one mechanism. The evidence supports that mechanism in the reported setting.", "core_answers": {"method.problem": {"answer": "The reported problem.", "evidence_refs": [{"pages": [1]}]}},
        "mechanism_result_map": ["m"],
        "claim_boundaries": ["b"],
        "reuse_takeaways": ["t" * 30],
        "followup_questions": ["q" * 30],
        "connections": [CONNECTION] if connections is None else connections,
        "key_prior_work": KEY_PRIOR,
    }


def quality_review(ref: str = "") -> dict:
    checks = dict.fromkeys(_final_quality.QUALITY_CHECKS, True)
    findings = []
    if ref:
        checks["connections"] = False
        findings = [
            {"check": "connections", "plan_ref": ref, "reason": "r", "required_revision": "v"}
        ]
    return {
        "schema_version": _final_quality.QUALITY_REVIEW_SCHEMA_VERSION,
        "output_language": "en",
        "verdict": "fail" if ref else "pass",
        "reviewed_note_sha256": "a" * 64,
        "reviewed_plan_sha256": "b" * 64,
        "checks": checks,
        "blocking_findings": findings,
    }


def validate(review: dict, plan: dict | None = None) -> str:
    return _final_quality.validate_quality(
        review,
        note_sha256="a" * 64,
        plan_sha256="b" * 64,
        plan=plan or quality_plan(),
        language="en",
    )


def test_quality_review_keeps_the_connections_check() -> None:
    assert "connections" in _final_quality.QUALITY_CHECKS
    validate(quality_review())


@pytest.mark.parametrize("ref", ["/connections/0", "/key_prior_work/2"])
def test_connections_finding_refs(ref: str) -> None:
    validate(quality_review(ref))


def test_connections_finding_rejects_missing_items() -> None:
    with pytest.raises(ValueError):
        validate(quality_review("/connections/3"))


def test_empty_connections_still_review_key_prior_work() -> None:
    validate(quality_review(), quality_plan(connections=[]))


# --- Formal Save link check ---------------------------------------------------


def run_writer(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    return subprocess.run(
        [sys.executable, str(WRITE_SCRIPT), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def source_manifest_args(tmp_path: Path) -> list[str]:
    path = tmp_path / "source-manifest.json"
    path.write_text(
        json.dumps({"status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64}),
        encoding="utf-8",
    )
    return ["--source-manifest", str(path)]


def linked_note(
    body_link: str = "[[InstructGPT.en|InstructGPT]]",
    frontmatter_link: str = "",
    my_notes: str = "",
) -> str:
    fm = f'methods: ["{frontmatter_link}"]\n' if frontmatter_link else "methods: []\n"
    return (
        f"---\ntags: [papers/AI]\n{fm}---\n\n# My Test Paper\n\n## 关联\n\n### 库内笔记\n\n"
        f"- {body_link}（基线/对比）：主要对照。\n\n## 我的笔记\n\n{my_notes or ZH_GUIDANCE}\n"
    )


def save(tmp_path: Path, vault: Path, text: str) -> subprocess.CompletedProcess:
    return run_writer(
        tmp_path,
        "--vault",
        str(vault),
        "--papers-dir",
        "Papers",
        "--title",
        "My Test Paper",
        *source_manifest_args(tmp_path),
        *formal_save_args(tmp_path, text, domain="AI"),
    )


def test_save_accepts_connection_links_to_existing_notes(tmp_path: Path, vault: Path) -> None:
    result = save(tmp_path, vault, linked_note())
    assert result.returncode == 0, result.stderr


def test_save_refuses_a_link_to_a_missing_note(tmp_path: Path, vault: Path) -> None:
    result = save(tmp_path, vault, linked_note(body_link="[[Missing_Paper.zh-CN|Missing]]"))
    assert result.returncode != 0
    assert "Missing_Paper.zh-CN" in result.stderr + result.stdout
    assert not list((vault / "Papers").glob("**/My_Test_Paper*.md"))


def test_save_refuses_a_missing_frontmatter_link(tmp_path: Path, vault: Path) -> None:
    result = save(tmp_path, vault, linked_note(frontmatter_link="[[NoSuchTerm]]"))
    assert result.returncode != 0
    assert "NoSuchTerm" in result.stderr + result.stdout


def test_links_in_my_notes_are_not_checked(tmp_path: Path, vault: Path) -> None:
    result = save(tmp_path, vault, linked_note(my_notes="想以后写一篇 [[还不存在的笔记]]。"))
    assert result.returncode == 0, result.stderr


def test_workspace_save_refuses_any_generated_link(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DEEPPAPERNOTE_OBSIDIAN_VAULT", raising=False)
    result = run_writer(
        tmp_path, "--title", "Workspace Paper", *formal_save_args(tmp_path, linked_note(), domain="AI")
    )
    assert result.returncode != 0
    assert "workspace" in (result.stderr + result.stdout).lower()
