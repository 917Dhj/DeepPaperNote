from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from formal_save_helpers import formal_save_args

import _final_quality
import _user_notes
import build_synthesis_bundle
import lint_grounding
import lint_note
from contracts import takeaway_plan_issues
from localization import note_schema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRITE_SCRIPT = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "write_obsidian_note.py"

ZH_GUIDANCE = note_schema("zh-CN")["my_notes_guidance"]
EN_GUIDANCE = note_schema("en")["my_notes_guidance"]


def zh_tail(transferable: list[str] | None = None, next_steps: list[str] | None = None) -> str:
    transferable = transferable if transferable is not None else [
        "把失败调用记录成显式状态的做法，可以迁移到任何多步工具链路，前提是每一步都能拿到可判定的返回码。"
    ]
    next_steps = next_steps if next_steps is not None else [
        "怀疑状态机在高延迟外部服务下会失效，可以在注入超时的环境里复跑主实验来检验。"
    ]
    lines = ["## 阅读收获", "", "### 可迁移", ""]
    lines += [f"- {item}" for item in transferable]
    lines += ["", "### 下一步", ""]
    lines += [f"- {item}" for item in next_steps]
    lines += [
        "",
        "## 关联",
        "",
        "### 库内笔记",
        "",
        "库里暂无相关笔记",
        "",
        "### 关键前置文献",
        "",
        "- Smith et al. 2024. Auditable Tool Use for Multi-hop Question Answering（基线）",
        "- Yao et al. 2023. ReAct: Synergizing Reasoning and Acting in Language Models（方法来源）",
        "- Schick et al. 2023. Toolformer: Language Models Can Teach Themselves to Use Tools（方法来源）",
        "",
        "## 我的笔记",
        "",
        ZH_GUIDANCE,
        "",
    ]
    return "\n".join(lines)


def zh_note(tail: str | None = None) -> str:
    return """# Paper

## 核心信息

- 标题: Paper
- 发表时间: 2024

## 原文摘要翻译

论文围绕长链路推理中的错误传播问题，提出一种把检索证据、工具调用状态和最终答案联合建模的框架。

## 创新点

- 论文把检索证据选择和工具调用规划放在同一个状态转移过程里建模，使错误证据不会被默认当成可靠输入。
- 论文设计了失败调用回溯机制，显式记录每一步工具返回的置信度和异常类型。

## 一句话总结

这篇论文用可审计的工具调用状态机降低长链路问答中的错误累积。

## 背景与问题

论文关注多步问答系统在检索证据不完整、工具调用失败时，如何保持最终答案的可追溯性与可靠性。

## 现有方法的局限

只看答案的方法无法区分证据不足和推理错误，失败的工具调用也不会留下可检查的记录。

## 核心思路与挑战

核心思路是把每一步工具调用写进可审计的状态机，难点是失败状态要被后续步骤显式读取。

## 方法

输入问题先进入证据筛选模块，随后工具规划器选择下一步调用，最后由答案生成器结合状态日志输出结论。

## 实验证据

在三个多步问答数据集上，方法把答案准确率从 71.2% 提升到 78.5%，并将不可追溯错误比例从 18% 降到 9%。

## 深度分析

这项工作的关键价值是把失败工具调用从隐藏中间状态变成可检查证据，因此适合需要审计链路的知识密集型问答。

## 局限

论文主要在英文问答数据上验证，工具集合也集中在检索和计算两类，尚未证明该状态机能覆盖高延迟外部服务。

""" + (tail if tail is not None else zh_tail())


def reasons(text: str) -> set[str]:
    return {str(item["reason"]) for item in lint_note.inspect_substantive_content(text)}


@pytest.fixture(autouse=True)
def zh_lint_profile():
    lint_note.configure_output_language("zh-CN")
    lint_note.configure_paper_type("method")
    yield
    lint_note.configure_output_language("zh-CN")


# --- section schema -------------------------------------------------------


def test_section_order_puts_takeaways_before_references_and_my_notes_last() -> None:
    zh = list(note_schema("zh-CN")["sections"].values())
    en = list(note_schema("en")["sections"].values())
    assert zh[-4:] == ["局限", "阅读收获", "关联", "我的笔记"]
    assert en[-4:] == ["Limitations", "Takeaways", "Connections", "My Notes"]


def test_writing_contract_carries_takeaways_and_my_notes_contracts() -> None:
    for language, guidance in (("zh-CN", ZH_GUIDANCE), ("en", EN_GUIDANCE)):
        contract = build_synthesis_bundle.compact_writing_contract(language)
        takeaways = contract["takeaways_contract"]
        assert takeaways["min_items"] == 1 and takeaways["max_items"] == 2
        assert takeaways["plan_fields"] == ["reuse_takeaways", "followup_questions"]
        assert len(takeaways["subsections"]) == 2
        my_notes = contract["my_notes_contract"]
        assert my_notes["guidance"] == guidance
        assert my_notes["position"] == "last"
        assert my_notes["section"] == contract["section_order"]["tail"][-1]
        assert "reader_research_direction" in contract["note_plan_contract"]["template"]
        assert "reader_research_direction" not in contract["note_plan_contract"]["required_fields"]


# --- Final Note Lint --------------------------------------------------------


def test_note_with_takeaways_and_exact_guidance_passes_substantive_gate() -> None:
    assert lint_note.inspect_substantive_content(zh_note()) == []
    assert lint_note.find_missing_sections(zh_note()) == []


def test_guidance_callout_is_not_mixed_language() -> None:
    assert lint_note.mixed_language_issues(zh_note()) == []


def test_takeaways_requires_both_subsections() -> None:
    note = zh_note().replace("### 下一步", "### 其他")
    assert "takeaways_subsection_missing" in reasons(note)


@pytest.mark.parametrize("count", [0, 3])
def test_takeaways_slot_holds_one_or_two_items(count: int) -> None:
    items = [f"第 {i} 条可迁移的做法写得足够具体，说明了场景和前提条件，而不是一句通用的套话。" for i in range(count)]
    note = zh_note(zh_tail(transferable=items))
    assert "takeaways_item_count_invalid" in reasons(note)


def test_two_items_per_slot_are_allowed() -> None:
    items = [f"第 {i} 条可迁移的做法写得足够具体，说明了场景和前提条件，而不是一句通用的套话。" for i in range(2)]
    assert lint_note.inspect_substantive_content(zh_note(zh_tail(transferable=items))) == []


def test_my_notes_must_hold_exactly_the_standard_guidance() -> None:
    note = zh_note().replace(ZH_GUIDANCE, "我觉得这篇论文的失败回溯机制很值得借鉴，可以用到自己的项目里。")
    assert "my_notes_guidance_mismatch" in reasons(note)


def test_my_notes_must_be_the_last_section() -> None:
    note = zh_note().rstrip("\n") + "\n\n## 附录\n\n额外内容写在用户区之后会让边界失效，需要拒绝。\n"
    assert "my_notes_not_last" in reasons(note)


def test_english_note_requires_new_top_level_profile() -> None:
    lint_note.configure_output_language("en")
    lint_note.configure_paper_type("")  # fixed sections only
    headings = "\n\n".join(f"## {name}\n\nBody." for name in note_schema("en")["sections"].values())
    assert lint_note.english_top_level_section_warnings(f"# T\n\n{headings}\n") == []
    old = headings.replace("## My Notes", "## Research Notes")
    assert lint_note.english_top_level_section_warnings(f"# T\n\n{old}\n") == [
        "top_level_section_profile_invalid"
    ]


# --- note plan --------------------------------------------------------------

GOOD_TAKEAWAY = "Record each tool failure as explicit state so later steps can tell missing evidence from bad reasoning."
GOOD_QUESTION = "Does the state machine still help when external tools time out, tested by injecting latency into the main benchmark?"


def plan(**overrides) -> dict:
    payload = {
        "reuse_takeaways": [GOOD_TAKEAWAY],
        "followup_questions": [GOOD_QUESTION],
        "key_prior_work": [{"work": "Smith et al. 2024. Auditable Tool Use", "role": "baseline"}, {"work": "Yao et al. 2023. ReAct", "role": "method source"}, {"work": "Schick et al. 2023. Toolformer", "role": "method source"}],
        "connections": [],
        "reader_research_direction": "",
    }
    payload.update(overrides)
    return payload


def codes(payload: dict) -> set[tuple[str, str]]:
    return {(item["code"], item.get("field", "")) for item in takeaway_plan_issues(payload)}


def test_valid_takeaway_plan_has_no_issues() -> None:
    assert takeaway_plan_issues(plan()) == []
    assert takeaway_plan_issues(plan(reader_research_direction="LLM data synthesis for counseling")) == []
    payload = plan()
    del payload["reader_research_direction"]
    assert takeaway_plan_issues(payload) == []


def test_takeaway_plan_limits_items_to_two() -> None:
    assert ("note_plan_takeaway_item_count_invalid", "reuse_takeaways") in codes(
        plan(reuse_takeaways=[GOOD_TAKEAWAY] * 3)
    )


def test_takeaway_plan_rejects_thin_generic_and_non_string_items() -> None:
    assert ("note_plan_takeaway_item_too_thin", "followup_questions") in codes(
        plan(followup_questions=["More data."])
    )
    assert ("note_plan_takeaway_item_too_thin", "reuse_takeaways") in codes(
        plan(reuse_takeaways=["Use the raw source to explain why this method matters for practice."])
    )
    assert ("note_plan_takeaway_item_invalid", "reuse_takeaways") in codes(
        plan(reuse_takeaways=[{"text": GOOD_TAKEAWAY}])
    )


def test_reader_research_direction_must_be_a_string() -> None:
    assert ("note_plan_reader_research_direction_invalid", "reader_research_direction") in codes(
        plan(reader_research_direction=["data synthesis"])
    )


def test_grounding_and_note_lint_both_enforce_takeaway_plan_rules(tmp_path: Path) -> None:
    from test_lint_grounding import grounded_note_plan, source_manifest

    bad = grounded_note_plan()
    bad["reuse_takeaways"] = [GOOD_TAKEAWAY] * 3
    grounding_codes = {item["code"] for item in lint_grounding.validate_note_plan(bad, source_manifest(), "zh-CN")}
    assert "note_plan_takeaway_item_count_invalid" in grounding_codes

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(bad), encoding="utf-8")
    _, issues = lint_note.inspect_note_plan(plan_path, "zh-CN")
    assert "planning_reuse_takeaways_count_invalid" in issues


# --- Final Quality Review ---------------------------------------------------


def quality_plan() -> dict:
    return {
        "output_language": "en",
        "central_claims": [{"claim": "c", "what_it_does_not_prove": "d"}],
        "storyline": "The paper takes on one problem. It answers with one mechanism. The evidence supports that mechanism in the reported setting.", "core_answers": {"method.problem": {"answer": "The reported problem.", "evidence_refs": [{"pages": [1]}]}},
        "mechanism_result_map": ["m"],
        "claim_boundaries": ["b"],
        "reuse_takeaways": [GOOD_TAKEAWAY],
        "followup_questions": [GOOD_QUESTION],
        "key_prior_work": [{"work": "Smith et al. 2024. Auditable Tool Use", "role": "baseline"}, {"work": "Yao et al. 2023. ReAct", "role": "method source"}, {"work": "Schick et al. 2023. Toolformer", "role": "method source"}],
        "connections": [],
    }


def quality_review(*, finding_ref: str = "") -> dict:
    checks = dict.fromkeys(_final_quality.QUALITY_CHECKS, True)
    findings = []
    if finding_ref:
        checks["takeaways"] = False
        findings = [{
            "check": "takeaways",
            "plan_ref": finding_ref,
            "reason": "The takeaway is generic.",
            "required_revision": "Name the paper mechanism and the target problem.",
        }]
    return {
        "schema_version": _final_quality.QUALITY_REVIEW_SCHEMA_VERSION,
        "output_language": "en",
        "verdict": "fail" if finding_ref else "pass",
        "reviewed_note_sha256": "a" * 64,
        "reviewed_plan_sha256": "b" * 64,
        "checks": checks,
        "blocking_findings": findings,
    }


def validate_review(review: dict, plan_payload: dict | None = None) -> str:
    return _final_quality.validate_quality(
        review, note_sha256="a" * 64, plan_sha256="b" * 64,
        plan=plan_payload or quality_plan(), language="en",
    )


def test_quality_review_has_takeaways_check() -> None:
    assert "takeaways" in _final_quality.QUALITY_CHECKS
    validate_review(quality_review())


@pytest.mark.parametrize("ref", ["/reuse_takeaways/0", "/followup_questions/0"])
def test_takeaways_finding_may_reference_either_plan_field(ref: str) -> None:
    validate_review(quality_review(finding_ref=ref))


@pytest.mark.parametrize("ref", ["/followup_questions/3", "/claim_boundaries/0"])
def test_takeaways_finding_rejects_other_or_missing_refs(ref: str) -> None:
    with pytest.raises(ValueError):
        validate_review(quality_review(finding_ref=ref))


def test_bundle_routes_the_current_quality_review_schema() -> None:
    contract = build_synthesis_bundle.compact_writing_contract("en")
    assert contract["final_quality_gate"]["schema_version"] == _final_quality.QUALITY_REVIEW_SCHEMA_VERSION


def test_version_one_review_is_rejected_with_a_rerun_hint() -> None:
    review = quality_review()
    review["schema_version"] = 1
    with pytest.raises(ValueError, match="schema_version 4.*rerun"):
        validate_review(review)


def test_readability_receipt_and_state_stay_version_one() -> None:
    receipt = {"schema_version": 1, "output_language": "en", "verdict": "pass", "reviewed_note_sha256": "a" * 64}
    _final_quality.validate_readability(receipt, note_sha256="a" * 64, language="en")
    review = quality_review()
    state = _final_quality.advance_state(None, review, validate_review(review), language="en")
    assert state["schema_version"] == 1


def test_quality_review_requires_nonempty_takeaway_plan_fields() -> None:
    payload = quality_plan()
    payload["followup_questions"] = []
    with pytest.raises(ValueError):
        validate_review(quality_review(), payload)


# --- user notes merge -------------------------------------------------------

USER_BLOCK = "## 我的笔记\n\n我准备把失败状态记录用到自己的对话数据合成里。\n\n## 我自己的小标题\n\n- 待验证：超时场景。\n"


def draft() -> str:
    return zh_note()


def old_note_with(block: str) -> str:
    generated, _ = _user_notes.split_user_notes(draft(), "zh-CN")
    return generated.replace("71.2%", "70.0%") + block


def test_split_returns_generated_prefix_and_block_to_end_of_file() -> None:
    generated, block = _user_notes.split_user_notes(old_note_with(USER_BLOCK), "zh-CN")
    assert block == USER_BLOCK
    assert generated.endswith("\n") and "## 我的笔记" not in generated


def test_split_reports_missing_heading() -> None:
    assert _user_notes.split_user_notes("# T\n\n## 局限\n\n正文。\n", "zh-CN") is None


def test_merge_preserves_user_block_verbatim() -> None:
    merged, info = _user_notes.merge_user_notes(draft(), old_note_with(USER_BLOCK), "zh-CN")
    assert info["status"] == "preserved"
    assert merged.endswith(USER_BLOCK)
    assert merged.startswith(_user_notes.split_user_notes(draft(), "zh-CN")[0])
    assert info["user_notes_sha256"] == hashlib.sha256(USER_BLOCK.encode()).hexdigest()
    assert info["chars"] > 0


def test_merge_treats_guidance_only_block_as_untouched() -> None:
    block = f"## 我的笔记\n\n{ZH_GUIDANCE}\n"
    merged, info = _user_notes.merge_user_notes(draft(), old_note_with(block), "zh-CN")
    assert info["status"] == "untouched"
    assert merged == draft()


def test_merge_treats_byte_identical_saved_note_as_untouched() -> None:
    legacy = old_note_with("## 我的笔记\n\n模型当年写的旧式笔记内容。\n")
    recorded = hashlib.sha256(legacy.encode()).hexdigest()
    merged, info = _user_notes.merge_user_notes(draft(), legacy, "zh-CN", recorded_saved_sha256=recorded)
    assert info["status"] == "untouched"
    assert merged == draft()


def test_merge_keeps_legacy_model_text_when_note_was_edited() -> None:
    legacy = old_note_with("## 我的笔记\n\n模型当年写的旧式笔记内容。\n")
    merged, info = _user_notes.merge_user_notes(draft(), legacy, "zh-CN", recorded_saved_sha256="c" * 64)
    assert info["status"] == "preserved"
    assert merged.endswith("模型当年写的旧式笔记内容。\n")


def test_merge_without_heading_in_old_note_reports_it() -> None:
    merged, info = _user_notes.merge_user_notes(draft(), "# Paper\n\n旧笔记没有这一节。\n", "zh-CN")
    assert info["status"] == "heading_missing"
    assert merged == draft()


def test_merge_without_existing_note() -> None:
    merged, info = _user_notes.merge_user_notes(draft(), None, "zh-CN")
    assert info["status"] == "no_existing_note"
    assert merged == draft()


def test_merge_normalizes_crlf_in_preserved_block() -> None:
    old = old_note_with(USER_BLOCK).replace("\n", "\r\n")
    merged, info = _user_notes.merge_user_notes(draft(), old, "zh-CN")
    assert "\r" not in merged and merged.endswith(USER_BLOCK)


def test_merge_refuses_to_drop_user_notes_when_draft_lacks_heading() -> None:
    with pytest.raises(ValueError):
        _user_notes.merge_user_notes("# Paper\n\n草稿没有这一节。\n", old_note_with(USER_BLOCK), "zh-CN")


def test_restore_generated_text_recovers_the_reviewed_draft() -> None:
    merged, _ = _user_notes.merge_user_notes(draft(), old_note_with(USER_BLOCK), "zh-CN")
    assert _user_notes.restore_generated_text(merged, draft(), "zh-CN") == draft()
    edited_later = merged + "\n用户后来又补了一句。\n"
    assert _user_notes.restore_generated_text(edited_later, draft(), "zh-CN") == draft()


def test_inspect_existing_user_notes_for_preflight() -> None:
    assert _user_notes.inspect_existing_user_notes(old_note_with(USER_BLOCK), "zh-CN")["status"] == "present"
    assert _user_notes.inspect_existing_user_notes(
        old_note_with(f"## 我的笔记\n\n{ZH_GUIDANCE}\n"), "zh-CN"
    ) == {"status": "none", "chars": 0, "legacy_format": False}
    assert _user_notes.inspect_existing_user_notes("# T\n", "zh-CN") == {
        "status": "heading_missing", "chars": 0, "legacy_format": False,
    }


# --- Formal Save integration -----------------------------------------------


def source_manifest_args(tmp_path: Path) -> list[str]:
    path = tmp_path / "source-manifest.json"
    path.write_text(json.dumps({"status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64}), encoding="utf-8")
    return ["--source-manifest", str(path)]


def run_writer(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DEEPPAPERNOTE_DISABLE_SHELL_CONFIG"] = "1"
    return subprocess.run(
        [sys.executable, str(WRITE_SCRIPT), *args], cwd=tmp_path, env=env, capture_output=True, text=True
    )


def save_to_vault(tmp_path: Path, vault: Path, note_text: str, *extra: str) -> subprocess.CompletedProcess:
    return run_writer(
        tmp_path, "--vault", str(vault), "--title", "My Test Paper",
        *extra, *source_manifest_args(tmp_path), *formal_save_args(tmp_path, note_text),
    )


def test_obsidian_overwrite_preserves_user_notes_and_records_hashes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    first = save_to_vault(tmp_path, vault, draft())
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    generated, _ = _user_notes.split_user_notes(note_path.read_text(encoding="utf-8"), "zh-CN")
    note_path.write_text(generated + USER_BLOCK, encoding="utf-8")
    edited_sha = hashlib.sha256(note_path.read_bytes()).hexdigest()

    conflict = save_to_vault(tmp_path, vault, draft().replace("78.5%", "79.0%"))
    assert conflict.returncode == 2
    blocked = json.loads(conflict.stdout)
    assert blocked["conflict_code"] == "same_language_note_exists"
    assert blocked["user_notes"]["status"] == "present"
    assert blocked["user_notes"]["chars"] > 0

    replacement = draft().replace("78.5%", "79.0%")
    second = save_to_vault(
        tmp_path, vault, replacement,
        "--overwrite-existing-note", "--expected-existing-note-sha256", edited_sha,
    )
    assert second.returncode == 0, second.stderr
    payload = json.loads(second.stdout)
    saved = note_path.read_text(encoding="utf-8")
    assert "79.0%" in saved and saved.endswith(USER_BLOCK)
    assert payload["user_notes"]["status"] == "preserved"
    assert payload["reviewed_note_sha256"] == hashlib.sha256(replacement.encode()).hexdigest()
    assert payload["saved_note_sha256"] == hashlib.sha256(saved.encode()).hexdigest()
    assert payload["user_notes"]["sha256"] == hashlib.sha256(USER_BLOCK.encode()).hexdigest()
    sidecar = json.loads((note_path.parent / ".deeppapernote.json").read_text(encoding="utf-8"))
    entry = sidecar["sources"]["a" * 64]["notes"]["zh-CN"]
    assert entry["note_sha256"] == payload["saved_note_sha256"]
    assert entry["generated_note_sha256"] == payload["reviewed_note_sha256"]


def test_obsidian_overwrite_of_untouched_note_uses_fresh_guidance(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    first = save_to_vault(tmp_path, vault, draft())
    assert first.returncode == 0, first.stderr
    original_sha = hashlib.sha256(draft().encode()).hexdigest()
    replacement = draft().replace("78.5%", "79.0%")
    second = save_to_vault(
        tmp_path, vault, replacement,
        "--overwrite-existing-note", "--expected-existing-note-sha256", original_sha,
    )
    assert second.returncode == 0, second.stderr
    payload = json.loads(second.stdout)
    assert payload["user_notes"]["status"] == "untouched"
    assert Path(payload["note_path"]).read_text(encoding="utf-8") == replacement


def test_workspace_save_preserves_user_notes(tmp_path: Path) -> None:
    env_args = ("--title", "Workspace Paper")
    os.environ.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    first = run_writer(tmp_path, *env_args, *formal_save_args(tmp_path, draft()))
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    generated, _ = _user_notes.split_user_notes(note_path.read_text(encoding="utf-8"), "zh-CN")
    note_path.write_text(generated + USER_BLOCK, encoding="utf-8")

    replacement = draft().replace("78.5%", "79.0%")
    second = run_writer(tmp_path, *env_args, *formal_save_args(tmp_path, replacement))
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["user_notes"]["status"] == "preserved"
    assert note_path.read_text(encoding="utf-8").endswith(USER_BLOCK)


# --- follow-up: legacy detection and tighter takeaway rules ------------------

LEGACY_NOTE = """# Paper

## 局限

论文只在英文数据上验证。

## 我的笔记

模型在改版前写的旧式笔记内容，用户后来又补了一句。

## 引用

- Smith et al. 2024.
"""


def test_preserved_block_from_a_pre_takeaways_note_is_flagged_legacy() -> None:
    _, info = _user_notes.merge_user_notes(draft(), LEGACY_NOTE, "zh-CN")
    assert info["status"] == "preserved"
    assert info["legacy_format"] is True
    assert _user_notes.inspect_existing_user_notes(LEGACY_NOTE, "zh-CN")["legacy_format"] is True


def test_preserved_block_from_a_current_note_is_not_legacy() -> None:
    _, info = _user_notes.merge_user_notes(draft(), old_note_with(USER_BLOCK), "zh-CN")
    assert info["legacy_format"] is False
    assert _user_notes.inspect_existing_user_notes(old_note_with(USER_BLOCK), "zh-CN")["legacy_format"] is False


def test_workspace_save_reports_legacy_format_in_receipt(tmp_path: Path) -> None:
    os.environ.pop("DEEPPAPERNOTE_OBSIDIAN_VAULT", None)
    first = run_writer(tmp_path, "--title", "Legacy Paper", *formal_save_args(tmp_path, draft()))
    assert first.returncode == 0, first.stderr
    note_path = Path(json.loads(first.stdout)["note_path"])
    note_path.write_text(LEGACY_NOTE, encoding="utf-8")
    second = run_writer(tmp_path, "--title", "Legacy Paper", *formal_save_args(tmp_path, draft()))
    assert second.returncode == 0, second.stderr
    user_notes = json.loads(second.stdout)["user_notes"]
    assert user_notes["status"] == "preserved" and user_notes["legacy_format"] is True


JUDGED = "判断：把标签先行生成迁移到咨询风险分级数据上，前提是由专业人员先定义风险等级并复核标签。"
UNJUDGED = "把标签先行生成迁移到咨询风险分级数据上，前提是由专业人员先定义风险等级并复核标签。"


def marker_reasons(transferable: list[str], direction: str) -> set[str]:
    note = zh_note(zh_tail(transferable=transferable))
    return {str(item["reason"]) for item in lint_note.inspect_takeaway_judgment(note, direction)}


def test_stated_direction_requires_a_judgment_marked_transferable_item() -> None:
    assert "takeaways_judgment_marker_missing" in marker_reasons([UNJUDGED], "心理咨询数据合成")
    assert marker_reasons([JUDGED], "心理咨询数据合成") == set()
    assert marker_reasons([f"**{JUDGED[:3]}**{JUDGED[3:]}", UNJUDGED], "心理咨询数据合成") == set()


def test_no_stated_direction_needs_no_judgment_marker() -> None:
    assert marker_reasons([UNJUDGED], "") == set()


def test_overlong_takeaway_item_is_a_warning() -> None:
    long_item = "判断：" + "把标签先行生成迁移到咨询风险分级数据上，前提是由专业人员先定义风险等级并复核标签，" * 4
    issues = lint_note.inspect_substantive_content(zh_note(zh_tail(transferable=[long_item])))
    found = [item for item in issues if item["reason"] == "takeaways_item_too_long"]
    assert found and found[0]["severity"] == "warning"
    assert not any(item["severity"] == "error" for item in issues)


def test_takeaways_contract_exposes_marker_and_length_limit() -> None:
    for language, marker in (("zh-CN", "判断："), ("en", "Judgment:")):
        contract = build_synthesis_bundle.compact_writing_contract(language)["takeaways_contract"]
        assert contract["judgment_marker"] == marker
        assert contract["max_item_chars"] > 0


def test_note_lint_cli_checks_judgment_marker_against_plan(tmp_path: Path) -> None:
    from test_lint_note import _valid_plan_payload

    note_path = tmp_path / "note.md"
    note_path.write_text(zh_note(zh_tail(transferable=[UNJUDGED])), encoding="utf-8")
    plan = _valid_plan_payload()
    plan["reader_research_direction"] = "心理咨询数据合成"
    plan_path = tmp_path / "note.plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    script = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts" / "lint_note.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(note_path), "--plan-file", str(plan_path), "--language", "zh-CN"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert "takeaways_judgment_marker_missing" in payload["warnings"]
    assert payload["passes_substantive_content"] is False
