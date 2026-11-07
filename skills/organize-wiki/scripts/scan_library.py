"""Read the paper library: domains, papers with their tag status, anomalies, and the convention.

Read-only. `references/file-contract.md` describes the output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import domains_file
from wiki_vault import (
    DOMAINS_RELATIVE_PATH,
    MEMORY_RELATIVE_PATH,
    TAG_PREFIX,
    domain_tag,
    h1_title,
    is_paper_folder,
    locate,
    note_tags,
    parse_frontmatter,
    read_text,
    sha256_file,
    split_frontmatter,
    visible,
)

EXCERPT_CHARS = 400
TAG_SEVERITY = ("ok", "mismatch", "multiple", "missing", "no_frontmatter")
ABSTRACT_HEADINGS = {"摘要", "abstract"}
MEMORY_SECTIONS = {
    "我的研究方向": "directions", "my research directions": "directions",
    "不太关心的": "not_focus", "not my focus": "not_focus",
}


def preferred_note(notes: list[Path], language: str) -> Path | None:
    suffix = f".{language}.md"
    return next((note for note in notes if note.name.endswith(suffix)), notes[0] if notes else None)


def excerpt(body: str) -> str:
    """The Abstract section when the note has one, else the body after the H1."""
    sections = re.split(r"(?m)^(#{1,6}[ \t]+.*)$", body)
    chosen = ""
    for index in range(1, len(sections) - 1, 2):
        title = sections[index].lstrip("#").strip().lower()
        if title in ABSTRACT_HEADINGS:
            chosen = sections[index + 1]
            break
    if not chosen:
        chosen = "".join(part for part in sections[2:] if not part.startswith("#")) or sections[0]
    chosen = re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", " ", chosen)
    return " ".join(chosen.split())[:EXCERPT_CHARS]


def tag_status(tags: list[str] | None, domain: str) -> str:
    if tags is None:
        return "no_frontmatter"
    papers = [tag for tag in tags if tag.startswith(TAG_PREFIX)]
    if not papers:
        return "missing"
    if len(papers) > 1:
        return "multiple"
    return "ok" if papers[0] == domain_tag(domain) else "mismatch"


def read_paper(folder: Path, domain: str, language: str, anomalies: list[dict], root: Path) -> dict:
    notes = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix == ".md" and visible(path))
    for child in sorted(folder.iterdir()):
        if child.is_dir() and visible(child) and child.name != "images":
            notes += sorted(path for path in child.iterdir() if path.is_file() and path.suffix == ".md" and visible(path))
    sidecar_title = ""
    try:
        sidecar_title = str(json.loads((folder / ".deeppapernote.json").read_text(encoding="utf-8"))["title"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    statuses, papers_tags, title, text_excerpt = [], [], "", ""
    main = preferred_note(notes, language)
    for note in notes:
        text = read_text(note)
        tags = note_tags(text)
        statuses.append(tag_status(tags, domain))
        for tag in tags or []:
            if tag.startswith(TAG_PREFIX) and tag not in papers_tags:
                papers_tags.append(tag)
        if note == main:
            block, body = split_frontmatter(text)
            fields = parse_frontmatter(block) if block is not None else {}
            title = str(fields.get("title") or "").strip() or h1_title(body)
            text_excerpt = excerpt(body)
    for child in sorted(folder.iterdir()):
        if not child.is_dir() or not visible(child):
            continue
        relative = child.relative_to(root).as_posix()
        if child.name == "images":
            for index in sorted(child.rglob("*.md")):
                anomalies.append({"kind": "images_index", "path": index.relative_to(root).as_posix(),
                                  "detail": "a note inside the paper's images folder"})
        elif any(child.rglob("*.md")):
            anomalies.append({"kind": "nested_folder", "path": relative,
                              "detail": "a subfolder holding notes; flatten moves its files up"})
    return {
        "id": folder.relative_to(root).as_posix(),
        "domain": domain,
        "folder": folder.name,
        "title": sidecar_title.strip() or title or folder.name.replace("_", " "),
        "notes": [note.relative_to(folder).as_posix() for note in notes],
        "has_sidecar": (folder / ".deeppapernote.json").is_file(),
        "pdf_only": not notes,
        "tag_status": max(statuses, key=TAG_SEVERITY.index) if statuses else "no_note",
        "papers_tags": papers_tags,
        "excerpt": text_excerpt,
    }


def read_memory(path: Path) -> dict:
    result = {"exists": path.is_file(), "directions": [], "not_focus": []}
    if not result["exists"]:
        return result
    section = None
    for line in split_frontmatter(read_text(path))[1].split("\n"):
        if line.startswith("## "):
            section = MEMORY_SECTIONS.get(line[3:].strip().lower())
        elif line.startswith("#"):
            section = None
        elif section and re.match(r"^[-*+][ \t]+\S", line):
            result[section].append(line[1:].strip())
    return result


def scan(vault: Path, papers_dir: str, language: str) -> dict:
    root = vault / papers_dir
    convention_path = vault / DOMAINS_RELATIVE_PATH
    convention = (
        domains_file.parse(read_text(convention_path))["domains"] if convention_path.is_file() else {}
    )
    domains, papers, anomalies = [], [], []
    children = sorted(root.iterdir()) if root.is_dir() else []
    for child in children:
        if not visible(child):
            continue
        relative = child.relative_to(root).as_posix()
        if child.is_file():
            anomalies.append({"kind": "loose_file", "path": relative, "detail": "a file directly in the papers root"})
        elif is_paper_folder(child):
            anomalies.append({"kind": "paper_at_root", "path": relative,
                              "detail": "a paper folder outside any domain"})
            papers.append(read_paper(child, "", language, anomalies, root))
        else:
            count = 0
            for entry in sorted(child.iterdir()):
                if not visible(entry):
                    continue
                if entry.is_file():
                    anomalies.append({"kind": "loose_file", "path": entry.relative_to(root).as_posix(),
                                      "detail": "a file directly in a domain folder"})
                else:
                    count += 1
                    papers.append(read_paper(entry, child.name, language, anomalies, root))
            domains.append({"name": child.name, "paper_count": count, "in_convention": child.name in convention})
    return {
        "domains_file": {
            "path": str(convention_path),
            "exists": convention_path.is_file(),
            "sha256": sha256_file(convention_path),
            "domains": convention,
        },
        "research_memory": read_memory(vault / MEMORY_RELATIVE_PATH),
        "domains": domains,
        "papers": papers,
        "anomalies": anomalies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="")
    parser.add_argument("--papers-dir", default="")
    parser.add_argument("--output", default="", help="Write the JSON here instead of stdout.")
    args = parser.parse_args()
    located = locate(vault=args.vault, papers_dir=args.papers_dir)
    payload = {**located, "today": date.today().isoformat()}
    if located["status"] == "ok":
        payload.update(scan(Path(located["vault"]), located["papers_dir"], located["language"]))
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": payload["status"], "output": args.output}))
    else:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
