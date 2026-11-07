"""Preview, apply, undo, and verify a library reorganization plan.

`references/file-contract.md` defines the plan, the outputs, and the log.
"""

from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, unquote

import domains_file
import scan_library
from wiki_vault import (
    DOMAINS_RELATIVE_PATH,
    ITEM_RE,
    KEY_RE,
    LOG_RELATIVE_DIR,
    TAG_PREFIX,
    domain_tag,
    is_paper_folder,
    locate,
    markdown_files,
    note_tags,
    read_text,
    sha256_bytes,
    sha256_file,
    valid_new_domain_name,
    vault_lock,
    visible,
)

LIST_KEYS = ("renames", "moves", "flatten", "wrap", "retag")
WIKI_TARGET_RE = re.compile(r"(?<=\[\[)([^\]|#\n]+)")
MARKDOWN_TARGET_RE = re.compile(r"(?<=\]\()(<?)([^)\s>]+)")
YAML_SPECIAL_RE = re.compile(r"""[:#\[\]{},&*!|>'"%@`]""")


class Refused(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class Program:
    """Everything apply will do, computed without touching the vault."""

    vault: Path
    papers_dir: str
    language: str
    mkdirs: list[str] = field(default_factory=list)
    wraps: list[tuple[str, str]] = field(default_factory=list)
    flattens: list[tuple[str, list[str], str]] = field(default_factory=list)
    moves: list[dict] = field(default_factory=list)
    edits: dict[str, dict] = field(default_factory=dict)
    rmdirs: list[str] = field(default_factory=list)
    domains_created: list[str] = field(default_factory=list)
    domains_removed: list[str] = field(default_factory=list)
    domains_text: str = ""
    domains_before: str | None = None
    warnings: list[str] = field(default_factory=list)
    digest: str = ""


# --- text rewriting ------------------------------------------------------------


def _rewrite_target(target: str, mapping: list[tuple[str, str]]) -> str | None:
    forms = (
        (lambda s: s),
        (lambda s: s.replace(" ", "%20")),
        (lambda s: quote(s, safe="/")),
    )
    for old, new in mapping:
        for form in forms:
            prefix = form(old)
            if target == prefix or target.startswith(prefix + "/"):
                return form(new) + target[len(prefix):]
    return None


def rewrite_links(text: str, mapping: list[tuple[str, str]]) -> str:
    """Rewrite `[[…]]` and `](…)` targets that start with an old vault-relative path."""
    if not mapping:
        return text

    def wiki(match: re.Match) -> str:
        new = _rewrite_target(match.group(1), mapping)
        return match.group(1) if new is None else new

    def markdown(match: re.Match) -> str:
        new = _rewrite_target(match.group(2), mapping)
        return match.group(0) if new is None else match.group(1) + new

    return MARKDOWN_TARGET_RE.sub(markdown, WIKI_TARGET_RE.sub(wiki, text))


def _yaml_item(tag: str) -> str:
    return json.dumps(tag, ensure_ascii=False) if YAML_SPECIAL_RE.search(tag) else tag


def normalize_tags(text: str, domain: str, old_domain: str = "") -> str:
    """Make `tags` hold the domain tag first; the old folder's tag goes, other papers/ tags become topics."""
    bom = "﻿" if text.startswith("﻿") else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    body = text.removeprefix("﻿").replace("\r\n", "\n")
    tags = note_tags(body)
    if tags is None:
        return text
    wanted = domain_tag(domain)
    replaced = domain_tag(old_domain) if old_domain else ""
    normalized = [wanted]
    for tag in tags:
        if tag == replaced:
            continue
        topic = tag[len(TAG_PREFIX):] if tag.startswith(TAG_PREFIX) and tag != wanted else tag
        if topic and topic not in normalized:
            normalized.append(topic)
    if normalized == tags:
        return text
    end = re.search(r"^---[ \t]*$", body[4:], flags=re.MULTILINE)
    lines = body[4 : 4 + end.start()].split("\n")
    rest = body[4 + end.start():]
    rendered = ["tags:"] + [f"  - {_yaml_item(tag)}" for tag in normalized]
    start = next((i for i, line in enumerate(lines) if (m := KEY_RE.match(line)) and m.group(1) == "tags"), None)
    if start is None:
        lines = rendered + lines
    else:
        stop = start + 1
        while stop < len(lines) and ITEM_RE.match(lines[stop]):
            stop += 1
        lines[start:stop] = rendered
    result = "---\n" + "\n".join(lines) + rest
    return bom + result.replace("\n", newline)


# --- planning -------------------------------------------------------------------


def _component(value: object) -> str:
    name = str(value or "").strip()
    if not name or "/" in name or "\\" in name or name.startswith(".") or name in {".", ".."}:
        return ""
    return name


def _note_link(folder: Path, paper: dict, language: str) -> str:
    note = scan_library.preferred_note([folder / name for name in paper["notes"]], language)
    title = paper["title"].replace("|", "-").replace("]", ")")
    return f"[[{note.stem}|{title}]]"


def build(vault: Path, papers_dir: str, plan: dict, today: str) -> Program:
    language = plan.get("language") if plan.get("language") in domains_file.TITLE else None
    located_language = locate(vault=str(vault))["language"]
    program = Program(vault=vault, papers_dir=papers_dir, language=language or located_language)
    root = vault / papers_dir
    scan = scan_library.scan(vault, papers_dir, program.language)
    papers = {paper["id"]: paper for paper in scan["papers"]}
    on_disk = [domain["name"] for domain in scan["domains"]]
    convention = scan["domains_file"]["domains"]
    loose = {item["path"] for item in scan["anomalies"] if item["kind"] == "loose_file"}
    nested: dict[str, list[str]] = {}
    for item in scan["anomalies"]:
        if item["kind"] == "nested_folder":
            nested.setdefault(item["path"].rsplit("/", 1)[0], []).append(item["path"])
    errors: list[str] = []

    if not isinstance(plan.get("domains"), list) or not plan["domains"]:
        raise Refused(["the plan has no domains list"])
    for key in LIST_KEYS:
        if not isinstance(plan.get(key, []), list):
            errors.append(f"{key} must be a list")
    if errors:
        raise Refused(errors)
    plan_domains: list[str] = []
    for entry in plan["domains"]:
        name = _component(entry.get("name") if isinstance(entry, dict) else "")
        if not name:
            errors.append(f"invalid domain name: {entry!r}")
            continue
        if name in plan_domains:
            errors.append(f"domain listed twice: {name}")
        if name not in on_disk and name not in convention and not valid_new_domain_name(name):
            errors.append(f"invalid new domain name: {name}")
        plan_domains.append(name)

    final = {paper_id: paper["domain"] for paper_id, paper in papers.items()}
    wrapped: dict[str, tuple[str, str]] = {}
    for entry in plan.get("wrap", []):
        file, folder = str(entry.get("file", "")), _component(entry.get("folder"))
        if file not in loose or "/" not in file:
            errors.append(f"unknown loose file in a domain: {file}")
            continue
        if not folder:
            errors.append(f"invalid folder for {file}: {entry.get('folder')!r}")
            continue
        domain = file.split("/", 1)[0]
        paper_id = f"{domain}/{folder}"
        if paper_id in final:
            errors.append(f"destination exists: {paper_id}")
            continue
        final[paper_id] = domain
        wrapped[paper_id] = (file, folder)
    for entry in plan.get("renames", []):
        source, target = str(entry.get("from", "")), str(entry.get("to", ""))
        if source not in on_disk:
            errors.append(f"unknown domain: {source}")
            continue
        if target not in plan_domains:
            errors.append(f"target domain is not in domains: {target}")
            continue
        for paper_id, domain in final.items():
            if domain == source:
                final[paper_id] = target
    for entry in plan.get("moves", []):
        paper_id, target = str(entry.get("paper", "")), str(entry.get("to", ""))
        if paper_id not in final:
            errors.append(f"unknown paper: {paper_id}")
        elif target not in plan_domains:
            errors.append(f"target domain is not in domains: {target}")
        else:
            final[paper_id] = target
    flatten_ids = []
    for entry in plan.get("flatten", []):
        paper_id = str(entry.get("paper", ""))
        if paper_id not in nested:
            errors.append(f"no nested folder to flatten: {paper_id}")
        else:
            flatten_ids.append(paper_id)
    retag_ids = []
    for entry in plan.get("retag", []):
        paper_id = str(entry.get("paper", ""))
        if paper_id not in papers:
            errors.append(f"unknown paper: {paper_id}")
        else:
            retag_ids.append(paper_id)

    wrapped_files = {file for file, _ in wrapped.values()}
    unwrapped_loose = {path.split("/", 1)[0] for path in loose - wrapped_files if "/" in path}
    remaining = {domain for domain in final.values() if domain} | unwrapped_loose
    for domain in sorted(remaining):
        if domain not in plan_domains:
            errors.append(f"domain folder missing from domains: {domain}")
    destinations: dict[str, str] = {}
    for paper_id, domain in final.items():
        folder = paper_id.rsplit("/", 1)[-1]
        current = papers[paper_id]["domain"] if paper_id in papers else None
        destination = f"{domain}/{folder}"
        if destination in destinations:
            errors.append(f"destination exists: {destination}")
        destinations[destination] = paper_id
        if (current is None or domain != current) and (root / destination).exists():
            errors.append(f"destination exists: {destination}")
    for paper_id in flatten_ids:
        folder = root / paper_id
        for sub in nested[paper_id]:
            for child in (root / sub).iterdir():
                if (folder / child.name).exists():
                    errors.append(f"flatten would overwrite: {paper_id}/{child.name}")
    rendered_domains = []
    for entry in plan["domains"]:
        name = _component(entry.get("name"))
        links = []
        for paper_id in entry.get("representative_papers") or []:
            paper = papers.get(paper_id)
            if paper is None:
                errors.append(f"unknown representative paper: {paper_id}")
            elif paper["pdf_only"]:
                errors.append(f"representative paper has no note: {paper_id}")
            else:
                links.append(_note_link(root / paper_id, paper, program.language))
        rendered_domains.append({
            "name": name,
            **{key: entry.get(key, "") for key in ("definition", "includes", "excludes")},
            "representative_papers": domains_file.link_list(links, program.language),
        })
    if errors:
        raise Refused(errors)

    # Folder operations, in execution order.
    prefix = papers_dir.strip("/")
    program.domains_created = [name for name in plan_domains if name not in on_disk and name in remaining]
    program.mkdirs = [f"{prefix}/{name}" for name in program.domains_created]
    mapping: list[tuple[str, str]] = []
    for paper_id, (file, folder) in wrapped.items():
        destination = f"{final[paper_id]}/{folder}"
        program.wraps.append((f"{prefix}/{file}", f"{prefix}/{destination}"))
        mapping.append((f"{prefix}/{file}", f"{prefix}/{destination}/{file.rsplit('/', 1)[1]}"))
        if final[paper_id] != file.split("/", 1)[0]:
            program.moves.append({"paper": paper_id, "from": paper_id, "to": destination})
    for paper_id in flatten_ids:
        children = [f"{prefix}/{sub}" for sub in nested[paper_id]]
        program.flattens.append((f"{prefix}/{paper_id}", children, paper_id))
        target = f"{prefix}/{final[paper_id]}/{paper_id.rsplit('/', 1)[-1]}"
        mapping.extend((child, target) for child in children)
    for paper_id, paper in papers.items():
        if final[paper_id] != paper["domain"]:
            destination = f"{final[paper_id]}/{paper['folder']}"
            program.moves.append({"paper": paper_id, "from": paper_id, "to": destination})
            mapping.append((f"{prefix}/{paper_id}", f"{prefix}/{destination}"))
    mapping.sort(key=lambda pair: len(pair[0]), reverse=True)

    def final_path(relative: str) -> str:
        for old, new in mapping:
            if relative == old or relative.startswith(old + "/"):
                return new + relative[len(old):]
        return relative

    # Text edits.
    retag_folders = {
        f"{prefix}/{paper_id}": (final[paper_id], papers[paper_id]["domain"])
        for paper_id in papers
        if final[paper_id] != papers[paper_id]["domain"] or paper_id in retag_ids
    }
    for path in markdown_files(vault):
        relative = path.relative_to(vault).as_posix()
        original = read_text(path)
        text = rewrite_links(original, mapping)
        kinds = ["links"] if text != original else []
        parent = relative.rsplit("/", 1)[0]
        flattened_parent = next((outer for outer, children, _ in program.flattens if parent in children), None)
        retag = retag_folders.get(flattened_parent or parent)
        if retag is not None:
            tagged = normalize_tags(text, *retag)
            if tagged != text:
                kinds.append("tags")
                text = tagged
        if kinds:
            program.edits[relative] = {
                "final": final_path(relative), "text": text, "kinds": sorted(kinds),
                "before_sha256": sha256_bytes(path.read_bytes()),
            }

    domains_path = vault / DOMAINS_RELATIVE_PATH
    program.domains_before = read_text(domains_path) if domains_path.is_file() else None
    program.domains_text = domains_file.render(rendered_domains, program.language, today)

    for domain in on_disk:
        if domain not in remaining:
            program.domains_removed.append(domain)
            program.rmdirs.append(f"{prefix}/{domain}")
    for name in plan_domains:
        if name not in remaining:
            program.warnings.append(f"domain has no papers yet: {name}")

    program.digest = sha256_bytes(json.dumps({
        "plan": plan, "today": today,
        "edits": {path: [edit["before_sha256"], edit["final"]] for path, edit in sorted(program.edits.items())},
        "moves": program.moves, "wraps": program.wraps,
        "flattens": [[outer, children] for outer, children, _ in program.flattens],
        "mkdirs": program.mkdirs, "rmdirs": program.rmdirs,
        "domains_before": sha256_file(domains_path),
    }, ensure_ascii=False, sort_keys=True).encode())
    return program


def preview_payload(program: Program) -> dict:
    domains_relative = DOMAINS_RELATIVE_PATH.as_posix()
    before = program.domains_before or ""
    return {
        "status": "ok",
        "plan_digest": program.digest,
        "summary": {
            "domains_created": program.domains_created,
            "domains_removed": program.domains_removed,
            "moves": len(program.moves),
            "flattens": len(program.flattens),
            "wraps": len(program.wraps),
            "tag_edits": sum("tags" in edit["kinds"] for edit in program.edits.values()),
            "link_edits": sum("links" in edit["kinds"] for edit in program.edits.values()),
        },
        "moves": program.moves,
        "edits": [{"path": edit["final"], "kinds": edit["kinds"]} for edit in program.edits.values()],
        "domains_file": {
            "path": str(program.vault / DOMAINS_RELATIVE_PATH),
            "exists": program.domains_before is not None,
            "text": program.domains_text,
            "diff": "".join(difflib.unified_diff(
                before.splitlines(keepends=True), program.domains_text.splitlines(keepends=True),
                fromfile=f"a/{domains_relative}", tofile=f"b/{domains_relative}",
            )),
        },
        "warnings": program.warnings,
        "errors": [],
    }


# --- applying -------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.organize-tmp")
    temporary.write_bytes(text.encode("utf-8"))
    os.replace(temporary, path)


def _remove_dir(path: Path) -> dict:
    hidden = {}
    for child in path.iterdir():
        hidden[child.name] = base64.b64encode(child.read_bytes()).decode("ascii")
        child.unlink()
    path.rmdir()
    return hidden


def _undo_step(vault: Path, step: dict) -> None:
    kind = step["kind"]
    if kind == "edit":
        target = vault / step["path"]
        if step["before_text"] is None:
            target.unlink(missing_ok=True)
        else:
            _write(target, step["before_text"])
    elif kind == "move":
        (vault / step["from"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(vault / step["to"]), str(vault / step["from"]))
    elif kind == "mkdir":
        target = vault / step["path"]
        if target.is_dir() and not any(target.iterdir()):
            target.rmdir()
    elif kind == "rmdir":
        target = vault / step["path"]
        target.mkdir(parents=True, exist_ok=True)
        for name, data in step.get("hidden_files", {}).items():
            (target / name).write_bytes(base64.b64decode(data))


def execute(program: Program) -> list[dict]:
    vault, steps = program.vault, []
    try:
        for relative in program.mkdirs:
            (vault / relative).mkdir(parents=True)
            steps.append({"kind": "mkdir", "path": relative})
        for source, folder in program.wraps:
            if not (vault / folder).exists():
                (vault / folder).mkdir(parents=True)
                steps.append({"kind": "mkdir", "path": folder})
            destination = f"{folder}/{source.rsplit('/', 1)[1]}"
            shutil.move(str(vault / source), str(vault / destination))
            steps.append({"kind": "move", "from": source, "to": destination})
        for outer, children, _ in program.flattens:
            for child in children:
                for entry in sorted((vault / child).iterdir()):
                    destination = f"{outer}/{entry.name}"
                    shutil.move(str(entry), str(vault / destination))
                    steps.append({"kind": "move", "from": f"{child}/{entry.name}", "to": destination})
                steps.append({"kind": "rmdir", "path": child, "hidden_files": _remove_dir(vault / child)})
        prefix = program.papers_dir.strip("/")
        wrapped_folders = {folder for _, folder in program.wraps}
        for move in program.moves:
            source, destination = f"{prefix}/{move['from']}", f"{prefix}/{move['to']}"
            if destination in wrapped_folders:
                continue
            shutil.move(str(vault / source), str(vault / destination))
            steps.append({"kind": "move", "from": source, "to": destination})
        for edit in program.edits.values():
            target = vault / edit["final"]
            before = read_text(target)
            _write(target, edit["text"])
            steps.append({"kind": "edit", "path": edit["final"], "kinds": edit["kinds"],
                          "before_text": before, "after_sha256": sha256_file(target)})
        domains_path = vault / DOMAINS_RELATIVE_PATH
        if not domains_path.parent.exists():
            domains_path.parent.mkdir(parents=True)
            steps.append({"kind": "mkdir", "path": DOMAINS_RELATIVE_PATH.parent.as_posix()})
        if program.domains_text != program.domains_before:
            _write(domains_path, program.domains_text)
            steps.append({"kind": "edit", "path": DOMAINS_RELATIVE_PATH.as_posix(), "kinds": ["domains"],
                          "before_text": program.domains_before, "after_sha256": sha256_file(domains_path)})
        for relative in program.rmdirs:
            target = vault / relative
            if any(visible(child) for child in target.iterdir()):
                raise OSError(f"domain folder is not empty: {relative}")
            steps.append({"kind": "rmdir", "path": relative, "hidden_files": _remove_dir(target)})
    except Exception:
        for step in reversed(steps):
            _undo_step(vault, step)
        raise
    return steps


def write_log(vault: Path, papers_dir: str, digest: str, steps: list[dict]) -> Path:
    directory = vault / LOG_RELATIVE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}.json"
    counter = 2
    while path.exists():
        path = directory / f"{stamp}-{counter}.json"
        counter += 1
    log = {"schema_version": 1, "created": datetime.now().isoformat(timespec="seconds"),
           "papers_dir": papers_dir, "plan_digest": digest, "undone": False, "steps": steps}
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def logs(vault: Path) -> list[Path]:
    directory = vault / LOG_RELATIVE_DIR
    return sorted(directory.glob("*.json"), reverse=True) if directory.is_dir() else []


# --- undo and verify ------------------------------------------------------------


def undo_conflicts(vault: Path, steps: list[dict]) -> list[str]:
    conflicts = []
    for step in steps:
        if step["kind"] == "edit" and sha256_file(vault / step["path"]) != step["after_sha256"]:
            conflicts.append(f"changed since the reorganization: {step['path']}")
        elif step["kind"] == "move":
            if not (vault / step["to"]).exists():
                conflicts.append(f"moved item is gone: {step['to']}")
            elif (vault / step["from"]).exists():
                conflicts.append(f"original location is occupied: {step['from']}")
        elif step["kind"] == "rmdir" and (vault / step["path"]).exists():
            conflicts.append(f"removed folder exists again: {step['path']}")
    return conflicts


def verify(vault: Path, papers_dir: str) -> dict:
    found = logs(vault)
    if not found:
        return {"status": "ok", "issues": [], "log": None}
    log = json.loads(found[0].read_text(encoding="utf-8"))
    issues = []
    old_paths = []
    for step in log["steps"]:
        if step["kind"] == "move":
            if not (vault / step["to"]).exists():
                issues.append(f"moved item is missing: {step['to']}")
            old_paths.append(step["from"])
    prefix = papers_dir.strip("/")
    for path in markdown_files(vault):
        text = read_text(path)
        targets = [m.group(1) for m in WIKI_TARGET_RE.finditer(text)]
        targets += [unquote(m.group(2)) for m in MARKDOWN_TARGET_RE.finditer(text)]
        for target in targets:
            if any(target == old or target.startswith(old + "/") for old in old_paths):
                issues.append(f"link to an old path in {path.relative_to(vault).as_posix()}: {target}")
    for step in log["steps"]:
        if step["kind"] == "edit" and "tags" in step.get("kinds", []):
            note = vault / step["path"]
            parts = Path(step["path"]).relative_to(prefix).parts if note.is_file() else ()
            if len(parts) >= 3:
                tags = note_tags(read_text(note)) or []
                papers_tags = [tag for tag in tags if tag.startswith(TAG_PREFIX)]
                if papers_tags != [domain_tag(parts[0])]:
                    issues.append(f"tags do not name the domain in {step['path']}: {papers_tags}")
    domains_path = vault / DOMAINS_RELATIVE_PATH
    listed = domains_file.parse(read_text(domains_path))["domains"] if domains_path.is_file() else {}
    root = vault / papers_dir
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if child.is_dir() and visible(child) and not is_paper_folder(child) and child.name not in listed:
            issues.append(f"domain folder missing from the domains file: {child.name}")
    return {"status": "issues" if issues else "ok", "issues": issues, "log": str(found[0])}


# --- command line ----------------------------------------------------------------


def emit(payload: dict, code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return code


def refused(errors: list[str]) -> int:
    return emit({"status": "refused", "errors": errors}, 1)


def load_plan(path: str) -> dict:
    plan = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(plan, dict):
        raise Refused(["the plan must be a JSON object"])
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "apply", "undo", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--vault", default="")
        command.add_argument("--papers-dir", default="")
        if name in ("preview", "apply"):
            command.add_argument("--plan", required=True)
        if name == "apply":
            command.add_argument("--expected-digest", required=True)
        if name in ("apply", "undo"):
            command.add_argument("--lock-timeout", type=float, default=15.0)
        if name == "undo":
            command.add_argument("--latest", action="store_true", required=True)
    args = parser.parse_args()
    located = locate(vault=args.vault, papers_dir=args.papers_dir)
    if located["status"] != "ok":
        return emit(located, 1)
    vault, papers_dir = Path(located["vault"]), located["papers_dir"]
    today = date.today().isoformat()
    try:
        if args.command == "preview":
            return emit(preview_payload(build(vault, papers_dir, load_plan(args.plan), today)))
        if args.command == "verify":
            return emit(verify(vault, papers_dir))
        with vault_lock(vault, args.lock_timeout):
            if args.command == "apply":
                program = build(vault, papers_dir, load_plan(args.plan), today)
                if program.digest != args.expected_digest:
                    return refused(["the library or the plan changed after preview; run preview again"])
                steps = execute(program)
                log = write_log(vault, papers_dir, program.digest, steps)
                return emit({"status": "ok", "log": str(log), "verify": verify(vault, papers_dir)})
            pending = [path for path in logs(vault)
                       if not json.loads(path.read_text(encoding="utf-8")).get("undone")]
            if not pending:
                return refused(["no reorganization left to undo"])
            log = json.loads(pending[0].read_text(encoding="utf-8"))
            conflicts = undo_conflicts(vault, log["steps"])
            if conflicts:
                return refused(conflicts)
            for step in reversed(log["steps"]):
                _undo_step(vault, step)
            log.update(undone=True, undone_at=datetime.now().isoformat(timespec="seconds"))
            pending[0].write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return emit({"status": "ok", "log": str(pending[0]), "undone_steps": len(log["steps"])})
    except Refused as exc:
        return refused(exc.errors)
    except TimeoutError as exc:
        return refused([f"could not take the vault lock: {exc}"])
    except (OSError, ValueError) as exc:
        return refused([f"{type(exc).__name__}: {exc}"])


if __name__ == "__main__":
    raise SystemExit(main())
