"""Read and write `<vault>/DeepPaperNote/domains.md`, the user's domain convention."""

from __future__ import annotations

import re

from wiki_vault import split_frontmatter

FIELDS = ("definition", "includes", "excludes", "representative_papers")
LABELS = {
    "zh-CN": {"definition": "定义", "includes": "收录", "excludes": "不收录", "representative_papers": "代表论文"},
    "en": {
        "definition": "Definition", "includes": "Includes", "excludes": "Excludes",
        "representative_papers": "Representative papers",
    },
}
TITLE = {"zh-CN": "领域分类", "en": "Paper Domains"}
NOTE_LINE = {
    "zh-CN": "这份约定由整理知识库 skill 与你一起维护。DeepPaperNote 保存新论文时按它选择领域文件夹。",
    "en": (
        "This convention is kept with you by the organize-wiki skill. "
        "DeepPaperNote follows it to choose the domain folder for a new paper."
    ),
}
SEPARATOR = {"zh-CN": "：", "en": ": "}
JOINER = {"zh-CN": "、", "en": ", "}
LABEL_KEYS = {label.lower(): key for labels in LABELS.values() for key, label in labels.items()}
DOMAIN_HEADING_RE = re.compile(r"^##[ \t]+(?!#)(.+?)[ \t]*#*[ \t]*$")
FIELD_RE = re.compile(r"^[ \t]*[-*][ \t]+([^:：]+?)[ \t]*[:：][ \t]*(.*?)[ \t]*$")


def parse(text: str) -> dict:
    """`{language, domains}`: each `##` heading is a domain, `- Label: text` lines its fields."""
    _, body = split_frontmatter(text)
    language = "en" if re.search(r"(?m)^#[ \t]+Paper Domains[ \t]*$", body) else "zh-CN"
    domains: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in body.split("\n"):
        heading = DOMAIN_HEADING_RE.match(line)
        if heading:
            current = domains.setdefault(heading.group(1).strip(), {})
            continue
        if line.startswith("#"):
            current = None
            continue
        field = FIELD_RE.match(line) if current is not None else None
        if field:
            key = LABEL_KEYS.get(field.group(1).strip().lower())
            if key and field.group(2) and key not in current:
                current[key] = field.group(2)
    return {"language": language, "domains": domains}


def render(domains: list[dict], language: str, today: str) -> str:
    """The whole file. Each domain's `representative_papers` is its rendered link text."""
    alias = TITLE[language]
    lines = [
        "---", f"aliases: [{alias}]", "tags: [paper-domains]", f"updated: {today}", "---", "",
        f"# {TITLE[language]}", "", f"> {NOTE_LINE[language]}",
    ]
    for domain in domains:
        lines += ["", f"## {domain['name']}", ""]
        for key in FIELDS:
            value = " ".join(str(domain.get(key) or "").split())
            if value:
                lines.append(f"- {LABELS[language][key]}{SEPARATOR[language]}{value}")
    return "\n".join(lines) + "\n"


def link_list(links: list[str], language: str) -> str:
    return JOINER[language].join(links)
