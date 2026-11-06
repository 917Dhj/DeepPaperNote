"""Read a paper-glossary term library that shares this run's vault, read-only.

DeepPaperNote never imports paper-glossary code: the glossary fails hard on a
malformed note, while a paper note must never fail because of one. This reader
skips what it cannot read and reports it as a warning.

The glossary is read only when its device-local configuration
(`~/.paper-glossary/config.json`: `vault_root`, `terms_subdir`) points at the
vault this run saves to, and its terms directory exists.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from _frontmatter import FrontmatterError, frontmatter_block, parse_frontmatter
from _note_paths import configured_obsidian_vault
from common import normalize_whitespace

MAX_TERMS = 40
H1_RE = re.compile(r"(?m)^#[ \t]+(.+?)[ \t]*$")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")


def default_config_path() -> Path:
    return Path.home() / ".paper-glossary" / "config.json"


def _key(value: str) -> str:
    return unicodedata.normalize("NFKC", normalize_whitespace(value)).casefold()


def glossary_location(config: dict[str, Any], *, config_path: Path | None = None) -> dict[str, Any]:
    """`{status, terms_dir, vault}`; status is ok, workspace, not_configured, other_vault, or unavailable."""
    try:
        vault = configured_obsidian_vault(config)
    except Exception:
        return {"status": "unavailable", "terms_dir": "", "vault": None}
    if vault is None:
        return {"status": "workspace", "terms_dir": "", "vault": None}
    path = config_path if config_path is not None else default_config_path()
    try:
        glossary = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        vault_root = Path(str(glossary["vault_root"])).expanduser()
        subdir = str(glossary["terms_subdir"]).strip()
        if not vault_root.is_absolute() or not subdir:
            raise ValueError("relative vault_root or empty terms_subdir")
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "not_configured", "terms_dir": "", "vault": vault}
    if vault_root.resolve() != vault.resolve():
        return {"status": "other_vault", "terms_dir": "", "vault": vault}
    terms_dir = (vault / subdir).resolve()
    if not terms_dir.is_relative_to(vault.resolve()) or not terms_dir.is_dir():
        return {"status": "unavailable", "terms_dir": "", "vault": vault}
    return {"status": "ok", "terms_dir": str(terms_dir), "vault": vault}


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [value] if isinstance(value, str) and value.strip() else []


def read_term_notes(terms_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Term notes with their names (file name, aliases, H1); ambiguous names are dropped."""
    notes: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in sorted(terms_dir.glob("*.md"), key=lambda item: item.name.casefold()):
        try:
            text = path.read_bytes().decode("utf-8-sig")
            fields = parse_frontmatter(text) or {}
        except (OSError, UnicodeDecodeError, FrontmatterError) as exc:
            warnings.append(f"Skipped unreadable glossary note {path.name}: {exc}")
            continue
        block = frontmatter_block(text) or ""
        body = text.split(block, 1)[-1] if block else text
        heading = H1_RE.search(body)
        display = normalize_whitespace(heading.group(1)) if heading else path.stem
        names: list[str] = []
        for name in [path.stem, *_as_list(fields.get("aliases")), display]:
            name = normalize_whitespace(name)
            # Exact de-duplication: "C＃" and "C#" are both kept as match forms.
            if name and name.casefold() not in {existing.casefold() for existing in names}:
                names.append(name)
        notes.append({"term": display, "path": path, "names": names})

    owners: dict[str, set[Path]] = {}
    for note in notes:
        for name in note["names"]:
            owners.setdefault(_key(name), set()).add(note["path"])
    shared = {key for key, paths in owners.items() if len(paths) > 1}
    for key in sorted(shared):
        files = ", ".join(sorted(path.name for path in owners[key]))
        warnings.append(f"Glossary name '{key}' belongs to several notes ({files}); not used.")
    for note in notes:
        note["names"] = [name for name in note["names"] if _key(name) not in shared]
    return [note for note in notes if note["names"]], warnings


def _is_acronym(form: str) -> bool:
    letters = [ch for ch in form if ch.isalpha()]
    return form.isascii() and bool(letters) and all(ch.isupper() for ch in letters) and " " not in form


def _form_pattern(form: str) -> re.Pattern[str]:
    escaped = re.escape(form)
    if not form.isascii():
        return re.compile(escaped, re.IGNORECASE)
    flags = 0 if _is_acronym(form) else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", flags)


def _vault_stem_counts(vault: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in vault.rglob("*.md"):
        relative = path.relative_to(vault)
        if any(part.startswith(".") for part in relative.parts):
            continue
        counts[path.stem.casefold()] = counts.get(path.stem.casefold(), 0) + 1
    return counts


def _link(note: dict[str, Any], vault: Path, stem_counts: dict[str, int]) -> str:
    path: Path = note["path"]
    target = path.stem
    if stem_counts.get(target.casefold(), 0) > 1:
        target = path.relative_to(vault.resolve()).with_suffix("").as_posix()
    return f"[[{target}]]" if target == note["term"] else f"[[{target}|{note['term']}]]"


def body_text_from_raw_sections(path: str | Path | None) -> str:
    """Paper body text: section records except the bibliography."""
    if not path:
        return ""
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    texts = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(record, dict)
            and record.get("record_type", "section") == "section"
            and record.get("kind") != "references"
            and isinstance(record.get("text"), str)
        ):
            texts.append(record["text"])
    return "\n\n".join(texts)


def glossary_terms(
    config: dict[str, Any], body_text: str, *, config_path: Path | None = None
) -> dict[str, Any]:
    """Glossary terms that appear in this paper's body, with links to copy verbatim."""
    location = glossary_location(config, config_path=config_path)
    result: dict[str, Any] = {
        "status": location["status"],
        "terms_dir": location["terms_dir"],
        "terms": [],
        "warnings": [],
    }
    if location["status"] != "ok":
        return result
    notes, warnings = read_term_notes(Path(location["terms_dir"]))
    result["warnings"] = warnings
    found = []
    for note in notes:
        counts = [(name, len(_form_pattern(name).findall(body_text))) for name in note["names"]]
        matched = [(name, count) for name, count in counts if count]
        if matched:
            found.append((note, [name for name, _ in matched], sum(count for _, count in matched)))
    if not found:
        return result
    vault: Path = location["vault"]
    stem_counts = _vault_stem_counts(vault.resolve())
    found.sort(key=lambda item: (-item[2], item[0]["term"].casefold()))
    result["terms"] = [
        {
            "term": note["term"],
            "link": _link(note, vault, stem_counts),
            "matched_forms": forms,
            "occurrences": occurrences,
        }
        for note, forms, occurrences in found[:MAX_TERMS]
    ]
    return result


# --- Formal Save -------------------------------------------------------------


def frontmatter_links(text: str) -> list[str]:
    """Targets of the `[[links]]` inside the YAML properties block."""
    try:
        block = frontmatter_block(text)
    except FrontmatterError:
        return []
    if not block:
        return []
    return [
        inner.split("|", 1)[0].split("#", 1)[0].strip()
        for bang, inner in WIKILINK_RE.findall(block)
        if not bang
    ]


def frontmatter_links_outside_glossary(
    text: str, config: dict[str, Any], *, config_path: Path | None = None
) -> tuple[list[str], str]:
    """Frontmatter link targets that are not glossary term notes, and the glossary status."""
    targets = frontmatter_links(text)
    location = glossary_location(config, config_path=config_path)
    if not targets:
        return [], location["status"]
    if location["status"] != "ok":
        return targets, location["status"]
    terms_dir = Path(location["terms_dir"])
    vault = location["vault"].resolve()
    allowed: set[str] = set()
    for path in terms_dir.glob("*.md"):
        allowed.add(path.stem.casefold())
        allowed.add(path.relative_to(vault).with_suffix("").as_posix().casefold())
    return [target for target in targets if target.casefold().lstrip("/") not in allowed], "ok"


def glossary_followup(
    config: dict[str, Any],
    *,
    source_manifest: str,
    note_path: str,
    regenerated: bool,
    config_path: Path | None = None,
) -> dict[str, Any]:
    location = glossary_location(config, config_path=config_path)
    return {
        "status": "suggested" if location["status"] == "ok" else location["status"],
        "terms_dir": location["terms_dir"],
        "source_manifest": source_manifest,
        "note_path": note_path,
        "regenerated": regenerated,
    }
