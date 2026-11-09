from __future__ import annotations

import pytest

import memory_format

CONTENT = {
    "directions": [
        {"text": "用大模型合成心理咨询对话数据，关注数据质量评估", "details": ["正在关心的问题：如何自动评估共情程度"]},
        {"text": "指令微调数据的自动构造"},
    ],
    "not_focus": [{"text": "计算机视觉的检测任务"}],
    "observations": [
        {"text": "2026-09 以来读的 8 篇里有 5 篇关于指令数据合成", "evidence": [["Self_Instruct.zh-CN", "Self-Instruct"]]},
    ],
}


def created(language: str = "zh-CN") -> str:
    return memory_format.render_new(CONTENT, language, today="2026-11-06")


def test_new_file_has_frontmatter_title_and_three_sections() -> None:
    text = created()
    assert text.startswith("---\naliases: [研究记忆]\ntags: [research-memory]\nupdated: 2026-11-06\n---\n\n# 研究记忆\n")
    assert text.index("## 我的研究方向") < text.index("## 不太关心的") < text.index("## 阅读观察")
    assert "- 用大模型合成心理咨询对话数据，关注数据质量评估\n  - 正在关心的问题：如何自动评估共情程度\n" in text
    assert "- 2026-09 以来读的 8 篇里有 5 篇关于指令数据合成\n  - 依据：[[Self_Instruct.zh-CN|Self-Instruct]]\n" in text
    assert memory_format.OBSERVATIONS_NOTE["zh-CN"] in text


def test_english_file_uses_english_headings() -> None:
    text = created("en")
    assert "# Research Memory" in text
    assert "## My Research Directions" in text and "## Not My Focus" in text and "## Reading Observations" in text
    assert "  - Evidence: [[Self_Instruct.zh-CN|Self-Instruct]]" in text


def test_no_observations_writes_the_fixed_sentence() -> None:
    text = memory_format.render_new({**CONTENT, "observations": []}, "zh-CN", today="2026-11-06")
    assert memory_format.NO_OBSERVATIONS["zh-CN"] in text


def test_parse_round_trips_items_in_either_language() -> None:
    for language in ("zh-CN", "en"):
        parsed = memory_format.parse(created(language))
        assert parsed["language"] == language
        assert [item["text"] for item in parsed["directions"]] == [
            "用大模型合成心理咨询对话数据，关注数据质量评估", "指令微调数据的自动构造",
        ]
        assert parsed["directions"][0]["details"] == ["正在关心的问题：如何自动评估共情程度"]
        assert [item["text"] for item in parsed["not_focus"]] == ["计算机视觉的检测任务"]
        assert len(parsed["observations"]) == 1


def test_parse_tolerates_a_hand_edited_file() -> None:
    text = "# 研究记忆\n\n## 我的研究方向\n\n随手写的一段话。\n\n- 方向一\n* 方向二\n\n## 我自己的小节\n\n- 不算方向\n"
    parsed = memory_format.parse(text)
    assert [item["text"] for item in parsed["directions"]] == ["方向一", "方向二"]
    assert parsed["not_focus"] == [] and parsed["observations"] == []


def test_too_many_directions_are_refused() -> None:
    content = {**CONTENT, "directions": [{"text": f"方向 {i}"} for i in range(6)]}
    with pytest.raises(ValueError, match="at most 5"):
        memory_format.render_new(content, "zh-CN", today="2026-11-06")


# --- updates: only the listed items change ----------------------------------

HAND_EDITED = (
    "---\naliases: [研究记忆]\ntags: [research-memory]\nupdated: 2026-10-01\nmy_own_key: keep\n---\n\n"
    "# 研究记忆\n\n## 我的研究方向\n\n我用自己的话补充一句。\n\n"
    "- 用大模型合成心理咨询对话数据，**尤其是**质量评估\n  - 正在关心的问题：共情\n  - 我自己加的子项\n"
    "- 指令微调数据的自动构造\n\n"
    "## 不太关心的\n\n- 计算机视觉的检测任务\n\n"
    "## 我自己的小节\n\n- 保留我\n\n"
    "## 阅读观察\n\n> 旧说明\n\n- 旧观察\n  - 依据：[[Old]]\n"
)


def apply(operations: list[dict], observations: list | None = None) -> str:
    return memory_format.apply_changes(
        HAND_EDITED, {"operations": operations, "observations": observations}, today="2026-11-06"
    )


def test_untouched_content_is_kept_byte_for_byte() -> None:
    result = apply([{"op": "add", "section": "not_focus", "text": "强化学习理论"}])
    expected = HAND_EDITED.replace("updated: 2026-10-01", "updated: 2026-11-06").replace(
        "- 计算机视觉的检测任务\n", "- 计算机视觉的检测任务\n- 强化学习理论\n"
    )
    assert result == expected


def test_remove_and_replace_match_the_item_text_exactly() -> None:
    result = apply([
        {"op": "remove", "section": "directions", "match": "指令微调数据的自动构造"},
        {"op": "replace", "section": "directions", "match": "用大模型合成心理咨询对话数据，**尤其是**质量评估",
         "text": "用大模型合成心理咨询对话数据", "details": ["正在关心的问题：共情评估"]},
    ])
    assert "指令微调数据的自动构造" not in result
    assert "- 用大模型合成心理咨询对话数据\n  - 正在关心的问题：共情评估\n" in result
    assert "我自己加的子项" not in result  # replace swaps the whole item, sub-items included
    assert "我用自己的话补充一句。" in result and "## 我自己的小节\n\n- 保留我\n" in result


def test_unknown_match_fails_the_whole_change() -> None:
    with pytest.raises(ValueError, match="not found"):
        apply([{"op": "remove", "section": "directions", "match": "不存在的方向"}])


def test_observations_are_replaced_as_a_whole_section() -> None:
    result = apply([], observations=[{"text": "新观察", "evidence": [["New.zh-CN", "New Paper"]]}])
    tail = result.split("## 阅读观察", 1)[1]
    assert "旧观察" not in tail and "旧说明" not in tail
    assert memory_format.OBSERVATIONS_NOTE["zh-CN"] in tail
    assert "- 新观察\n  - 依据：[[New.zh-CN|New Paper]]\n" in tail


def test_missing_observations_leave_the_section_alone() -> None:
    assert "- 旧观察" in apply([])


def test_adding_beyond_five_directions_is_refused() -> None:
    operations = [{"op": "add", "section": "directions", "text": f"新方向 {i}"} for i in range(4)]
    with pytest.raises(ValueError, match="at most 5"):
        apply(operations)


def test_add_to_a_section_the_user_deleted_recreates_it() -> None:
    text = HAND_EDITED.replace("## 不太关心的\n\n- 计算机视觉的检测任务\n\n", "")
    result = memory_format.apply_changes(
        text, {"operations": [{"op": "add", "section": "not_focus", "text": "强化学习理论"}]}, today="2026-11-06"
    )
    parsed = memory_format.parse(result)
    assert [item["text"] for item in parsed["not_focus"]] == ["强化学习理论"]
    assert result.index("## 不太关心的") < result.index("## 阅读观察")
