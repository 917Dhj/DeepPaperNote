"""Parse, create, and update `research-memory.md` (see references/file-contract.md).

Creation renders the whole file. An update edits only the items a change list
names, plus the whole Reading Observations section when new observations are
given; every other byte of the user's file is kept.
"""

from __future__ import annotations

import re

LANGUAGES = ("zh-CN", "en")
SECTION_KEYS = ("directions", "not_focus", "observations")
HEADINGS = {
    "zh-CN": {"directions": "我的研究方向", "not_focus": "不太关心的", "observations": "阅读观察"},
    "en": {
        "directions": "My Research Directions",
        "not_focus": "Not My Focus",
        "observations": "Reading Observations",
    },
}
TITLES = {"zh-CN": "研究记忆", "en": "Research Memory"}
EVIDENCE_LABEL = {"zh-CN": "依据：", "en": "Evidence: "}
EVIDENCE_JOINER = {"zh-CN": "、", "en": ", "}
OBSERVATIONS_NOTE = {
    "zh-CN": "> 这一节由研究记忆 skill 生成，每次更新整节替换；你自己的看法请写在上面两节。",
    "en": "> The research-memory skill writes this section and replaces it on every update; "
    "put your own views in the two sections above.",
}
NO_OBSERVATIONS = {
    "zh-CN": "阅读还不够多，暂时没有观察。",
    "en": "Not enough reading yet for observations.",
}
MAX_DIRECTIONS = 5

HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
ITEM_RE = re.compile(r"^[-*+][ \t]+(.*\S)[ \t]*$")
DETAIL_RE = re.compile(r"^[ \t]+[-*+][ \t]+(.*\S)[ \t]*$")
SECTION_BY_HEADING = {
    heading.casefold(): (key, language)
    for language, headings in HEADINGS.items()
    for key, heading in headings.items()
}


# --- reading -----------------------------------------------------------------


def _section_spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Line ranges (heading line, end) of the three known sections."""
    headings = [(i, HEADING_RE.match(line)) for i, line in enumerate(lines)]
    starts = [(i, match.group(1)) for i, match in headings if match]
    spans: dict[str, tuple[int, int]] = {}
    for position, (start, title) in enumerate(starts):
        known = SECTION_BY_HEADING.get(title.casefold())
        if known is None or known[0] in spans:
            continue
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        spans[known[0]] = (start, end)
    return spans


def _items(lines: list[str], start: int, end: int) -> list[dict]:
    """Top-level list items in lines[start:end], each with its indented sub-items."""
    items: list[dict] = []
    for index in range(start, end):
        line = lines[index]
        top = ITEM_RE.match(line)
        if top:
            items.append({"text": top.group(1), "details": [], "first": index, "last": index})
            continue
        detail = DETAIL_RE.match(line)
        if detail and items and items[-1]["last"] == index - 1:
            items[-1]["details"].append(detail.group(1))
            items[-1]["last"] = index
    return items


def detect_language(text: str) -> str | None:
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match and match.group(1).casefold() in SECTION_BY_HEADING:
            return SECTION_BY_HEADING[match.group(1).casefold()][1]
    return None


def parse(text: str) -> dict:
    """The items of each known section; unknown sections and prose are ignored."""
    lines = text.splitlines()
    spans = _section_spans(lines)
    parsed: dict = {"language": detect_language(text)}
    for key in SECTION_KEYS:
        if key in spans:
            start, end = spans[key]
            items = _items(lines, start + 1, end)
            parsed[key] = [{"text": item["text"], "details": item["details"]} for item in items]
        else:
            parsed[key] = []
    return parsed


# --- rendering ---------------------------------------------------------------


def _item_lines(item: dict) -> list[str]:
    text = " ".join(str(item.get("text", "")).split())
    if not text:
        raise ValueError("Every item needs non-empty text.")
    details = [" ".join(str(detail).split()) for detail in item.get("details") or []]
    return [f"- {text}", *(f"  - {detail}" for detail in details if detail)]


def _observation_lines(observations: list[dict], language: str) -> list[str]:
    lines = [OBSERVATIONS_NOTE[language], ""]
    if not observations:
        return lines + [NO_OBSERVATIONS[language]]
    for observation in observations:
        evidence = [
            f"[[{target}|{title}]]" if title and title != target else f"[[{target}]]"
            for target, title in observation.get("evidence") or []
        ]
        details = [EVIDENCE_LABEL[language] + EVIDENCE_JOINER[language].join(evidence)] if evidence else []
        lines += _item_lines({"text": observation.get("text", ""), "details": details})
    return lines


def _check_directions(count: int) -> None:
    if count > MAX_DIRECTIONS:
        raise ValueError(f"Research directions hold at most {MAX_DIRECTIONS} items; merge some first.")


def render_new(content: dict, language: str, *, today: str) -> str:
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    directions = content.get("directions") or []
    _check_directions(len(directions))
    headings = HEADINGS[language]
    lines = [
        "---",
        f"aliases: [{TITLES['zh-CN']}]",
        "tags: [research-memory]",
        f"updated: {today}",
        "---",
        "",
        f"# {TITLES[language]}",
        "",
        f"## {headings['directions']}",
        "",
    ]
    for item in directions:
        lines += _item_lines(item)
    lines += ["", f"## {headings['not_focus']}", ""]
    for item in content.get("not_focus") or []:
        lines += _item_lines(item)
    lines += ["", f"## {headings['observations']}", ""]
    lines += _observation_lines(content.get("observations") or [], language)
    return "\n".join(lines) + "\n"


# --- updating ----------------------------------------------------------------


def _touch_updated(lines: list[str], today: str) -> None:
    if not lines or lines[0].strip() != "---":
        return
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            lines.insert(index, f"updated: {today}")
            return
        if re.match(r"^updated[ \t]*:", lines[index]):
            lines[index] = f"updated: {today}"
            return


def _ensure_section(lines: list[str], key: str, language: str) -> tuple[int, int]:
    spans = _section_spans(lines)
    if key in spans:
        return spans[key]
    order = SECTION_KEYS.index(key)
    later = [spans[k][0] for k in SECTION_KEYS[order + 1 :] if k in spans]
    at = min(later) if later else len(lines)
    block = [f"## {HEADINGS[language][key]}", ""]
    if at == len(lines):
        block = ([""] if lines and lines[-1].strip() else []) + block
    else:
        block = block + [""]
    lines[at:at] = block
    return _section_spans(lines)[key]


def _find(lines: list[str], key: str, match: str) -> dict:
    start, end = _section_spans(lines).get(key, (0, 0))
    found = [item for item in _items(lines, start + 1, end) if item["text"] == match]
    if not found:
        raise ValueError(f"Item not found in {key}: {match}")
    return found[0]


def apply_changes(text: str, changes: dict, *, today: str) -> str:
    language = detect_language(text) or "zh-CN"
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")
    for operation in changes.get("operations") or []:
        op, key = operation.get("op"), operation.get("section")
        if key not in ("directions", "not_focus") or op not in ("add", "remove", "replace"):
            raise ValueError(f"Unsupported change: {operation}")
        if op == "add":
            start, end = _ensure_section(lines, key, language)
            items = _items(lines, start + 1, end)
            if key == "directions":
                _check_directions(len(items) + 1)
            at = items[-1]["last"] + 1 if items else start + 2
            if not items and (start + 1 >= len(lines) or lines[start + 1].strip()):
                lines.insert(start + 1, "")
            lines[at:at] = _item_lines(operation)
            continue
        item = _find(lines, key, str(operation.get("match", "")))
        replacement = _item_lines(operation) if op == "replace" else []
        lines[item["first"] : item["last"] + 1] = replacement
    observations = changes.get("observations")
    if observations is not None:
        start, end = _ensure_section(lines, "observations", language)
        body = ["", *_observation_lines(observations, language)]
        if end < len(lines):
            body.append("")
        lines[start + 1 : end] = body
    _touch_updated(lines, today)
    return "\n".join(lines) + ("\n" if trailing_newline or not lines else "")
