"""Domain routing: the overview the model reads and the checks on the domain it chooses.

The model picks the domain folder for a new paper directory. This module only
describes the existing domains and validates the choice; it never picks one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from _frontmatter import FrontmatterError, frontmatter_block, parse_frontmatter
from _note_paths import existing_domain_dirs, resolve_note_output_mode, safe_relative_path_parts

DOMAINS_FILE = Path("DeepPaperNote") / "domains.md"
SAMPLE_TITLES = 8
TAG_PREFIX = "papers/"
FIELD_KEYS = {
    "定义": "definition",
    "definition": "definition",
    "收录": "includes",
    "includes": "includes",
    "不收录": "excludes",
    "excludes": "excludes",
    "代表论文": "representative_papers",
    "representative papers": "representative_papers",
}
DOMAIN_HEADING_RE = re.compile(r"^##[ \t]+(?!#)(.+?)[ \t]*#*[ \t]*$")
FIELD_RE = re.compile(r"^[ \t]*[-*][ \t]+([^:：]+?)[ \t]*[:：][ \t]*(.*?)[ \t]*$")
NEW_DOMAIN_NAME_RE = re.compile(r"[\w-]+")
DOMAIN_CHOICE_CODES = frozenset(
    {"domain_required", "domain_name_invalid", "new_domain_reason_required"}
)


class DomainChoiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def domain_locations(config: dict[str, Any]) -> tuple[Path, Path | None]:
    """The folder that holds the domains, and the domains file (Obsidian mode only)."""
    output_mode, root = resolve_note_output_mode(config)
    if output_mode != "obsidian":
        return root, None
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    return root / Path(*safe_relative_path_parts(papers_dir, "papers_dir")), root / DOMAINS_FILE


def parse_domains_file(text: str) -> dict[str, dict[str, str]]:
    """Each `##` heading names a domain; `- Label: text` lines under it fill its fields."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    try:
        block = frontmatter_block(text)
    except FrontmatterError:
        block = None
    if block is not None:
        text = text[4 + len(block):].partition("\n")[2]
    domains: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.split("\n"):
        heading = DOMAIN_HEADING_RE.match(line)
        if heading:
            current = domains.setdefault(heading.group(1).strip(), {})
            continue
        if line.startswith("#"):
            current = None
            continue
        field = FIELD_RE.match(line) if current is not None else None
        if field:
            key = FIELD_KEYS.get(field.group(1).strip().lower())
            if key and field.group(2) and key not in current:
                current[key] = field.group(2)
    return domains


def read_domains_file(path: Path | None) -> dict[str, dict[str, str]] | None:
    if path is None or not path.is_file():
        return None
    try:
        return parse_domains_file(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def paper_folders(domain_dir: Path) -> list[Path]:
    if not domain_dir.is_dir():
        return []
    return [
        child for child in sorted(domain_dir.iterdir())
        if child.is_dir() and not child.name.startswith(".")
    ]


def paper_title(folder: Path) -> str:
    """The sidecar title, else a note's `title` property or H1, else the folder name."""
    try:
        title = json.loads((folder / ".deeppapernote.json").read_text(encoding="utf-8"))["title"]
        if isinstance(title, str) and title.strip():
            return title.strip()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    for note in sorted(folder.glob("*.md")):
        try:
            text = note.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            continue
        try:
            fields = parse_frontmatter(text) or {}
        except FrontmatterError:
            fields = {}
        title = fields.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        heading = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
        if heading:
            return heading.group(1).strip()
    return folder.name.replace("_", " ")


def domain_overview(config: dict[str, Any]) -> dict[str, Any]:
    """What the model reads before choosing: every domain with its definition or sample titles."""
    base, domains_file = domain_locations(config)
    convention = read_domains_file(domains_file)
    on_disk = existing_domain_dirs(config)
    domains = []
    for name in sorted(set(on_disk) | set(convention or {})):
        folders = paper_folders(base / name) if name in on_disk else []
        entry: dict[str, Any] = {
            "name": name,
            "paper_count": len(folders),
            "on_disk": name in on_disk,
            "in_convention": name in (convention or {}),
        }
        if convention and name in convention:
            entry.update(convention[name])
        else:
            entry["sample_titles"] = [paper_title(folder) for folder in folders[:SAMPLE_TITLES]]
        domains.append(entry)
    return {
        "source": "folders" if convention is None else "domains_file",
        "domains_file": None if convention is None else str(domains_file),
        "domains": domains,
        "guide": "references/domain-routing.md",
    }


def resolve_domain_choice(
    config: dict[str, Any], domain: str, new_domain_reason: str = ""
) -> tuple[str, bool]:
    """Return (domain, is_new) for the model's choice, or raise DomainChoiceError."""
    name = (domain or "").strip()
    if not name:
        raise DomainChoiceError(
            "domain_required",
            "Choose a domain from domain_overview and rerun with --domain.",
        )
    if (
        "/" in name or "\\" in name or name.startswith(".")
        or any(ord(char) < 32 for char in name)
    ):
        raise DomainChoiceError(
            "domain_name_invalid", f"A domain is one folder name inside the papers root: {name}"
        )
    base, domains_file = domain_locations(config)
    known = set(existing_domain_dirs(config)) | set(read_domains_file(domains_file) or {})
    for existing in sorted(known):
        if existing.casefold() == name.casefold():
            return existing, False
    if (base / name).exists():
        raise DomainChoiceError(
            "domain_name_invalid", f"{name} already exists and is not a domain folder."
        )
    if not NEW_DOMAIN_NAME_RE.fullmatch(name) or name.isdigit():
        raise DomainChoiceError(
            "domain_name_invalid",
            f"A new domain name must work as a tag: letters, digits, _ and - only: {name}",
        )
    if not (new_domain_reason or "").strip():
        raise DomainChoiceError(
            "new_domain_reason_required",
            f"{name} is a new domain; pass --new-domain-reason saying why no existing domain fits.",
        )
    return name, True


def saved_domain(config: dict[str, Any], note_path: Path) -> str:
    """The domain a note is saved under: its paper folder's parent below the papers root."""
    base, _ = domain_locations(config)
    parent = Path(note_path).parent.parent
    try:
        parts = parent.resolve().relative_to(base.resolve()).parts
    except ValueError:
        parts = ()
    return "/".join(parts) or parent.name


def domain_tag(domain: str) -> str:
    return TAG_PREFIX + re.sub(r"\s+", "_", domain.strip())


def domain_tag_issue(text: str, domain: str) -> str:
    """Empty when the note carries exactly one papers/ tag and it names the saved domain."""
    try:
        fields = parse_frontmatter(text) or {}
    except FrontmatterError:
        fields = {}
    tags = fields.get("tags")
    values = tags if isinstance(tags, list) else [tags] if isinstance(tags, str) else []
    found = [tag.strip() for tag in values if tag.strip().startswith(TAG_PREFIX)]
    expected = domain_tag(domain)
    if found == [expected]:
        return ""
    return (
        f"The note must carry exactly one {TAG_PREFIX} tag, {expected}, matching the saved "
        f"domain {domain}; found {', '.join(found) or 'none'}."
    )
