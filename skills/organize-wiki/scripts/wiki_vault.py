"""Find the vault and read its paper library, tolerantly, for the organize-wiki skill.

The vault and paper folder come from DeepPaperNote's user configuration
(`~/.deeppapernote/config.json`, or `DEEPPAPERNOTE_CONFIG_PATH`), read as plain
JSON. Explicit arguments win. Reading never fails on one malformed note.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
from pathlib import Path

DEFAULT_PAPERS_DIR = "Research/Papers"
DOMAINS_RELATIVE_PATH = Path("DeepPaperNote") / "domains.md"
MEMORY_RELATIVE_PATH = Path("DeepPaperNote") / "research-memory.md"
LOG_RELATIVE_DIR = Path("DeepPaperNote") / "organize-log"
LOCK_NAME = ".deeppapernote.lock"
TAG_PREFIX = "papers/"
LANGUAGE_ALIASES = {"zh": "zh-CN", "zh-cn": "zh-CN", "zh_cn": "zh-CN", "en": "en", "en-us": "en"}
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(.*?))?[ \t]*$")
ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.*?)[ \t]*$")
H1_RE = re.compile(r"(?m)^#[ \t]+(.+?)[ \t]*$")
NEW_DOMAIN_NAME_RE = re.compile(r"[\w-]+")


def default_config_path() -> Path:
    override = os.environ.get("DEEPPAPERNOTE_CONFIG_PATH", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".deeppapernote" / "config.json"


def normalize_language(value: object) -> str:
    return LANGUAGE_ALIASES.get(str(value or "").strip().lower(), "zh-CN")


def locate(*, vault: str | None = None, papers_dir: str | None = None) -> dict:
    """`{status, vault, papers_dir, language}`; status is ok, needs_vault, or not_a_vault."""
    try:
        config = json.loads(default_config_path().read_text(encoding="utf-8-sig"))
        config = config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        config = {}
    chosen = (vault or str(config.get("obsidian_vault") or "")).strip()
    folder = (papers_dir or str(config.get("papers_dir") or "")).strip().strip("/") or DEFAULT_PAPERS_DIR
    language = normalize_language(config.get("output_language"))
    if not chosen:
        return {"status": "needs_vault", "vault": "", "papers_dir": folder, "language": language}
    root = Path(chosen).expanduser().resolve()
    if not (root / ".obsidian").is_dir():
        return {"status": "not_a_vault", "vault": str(root), "papers_dir": folder, "language": language}
    return {"status": "ok", "vault": str(root), "papers_dir": folder, "language": language}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes()) if path.is_file() else ""


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")


def visible(path: Path) -> bool:
    return not path.name.startswith(".")


def domain_tag(domain: str) -> str:
    return TAG_PREFIX + re.sub(r"\s+", "_", domain.strip())


def valid_new_domain_name(name: str) -> bool:
    return bool(NEW_DOMAIN_NAME_RE.fullmatch(name)) and not name.isdigit()


def is_paper_folder(path: Path) -> bool:
    """DeepPaperNote's marker for a paper folder sitting where a domain is expected."""
    return path.is_dir() and any(
        (path / marker).exists()
        for marker in (f"{path.name}.md", f"{path.name}.zh-CN.md", f"{path.name}.en.md", ".deeppapernote.json")
    )


def markdown_files(vault: Path) -> list[Path]:
    """Every note in the vault outside hidden folders such as `.obsidian` and `.trash`."""
    files = []
    for root, dirs, names in os.walk(vault):
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        files.extend(Path(root) / name for name in sorted(names) if name.endswith(".md"))
    return files


@contextlib.contextmanager
def vault_lock(vault: Path, timeout: float = 15.0):
    """Hold `<vault>/.deeppapernote.lock`, the lock DeepPaperNote takes while it saves."""
    with (vault / LOCK_NAME).open("a+b") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    if not stream.read(1):
                        stream.write(b"\0")
                        stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError("the vault lock is held by another DeepPaperNote process") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


# --- frontmatter -------------------------------------------------------------


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _flow_list(value: str) -> list[str]:
    items, current, quote = [], [], ""
    for ch in value[1:-1]:
        if quote:
            current.append(ch)
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [item for item in (_unquote(part) for part in items) if item]


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """(frontmatter block or None, body), on BOM-free LF text."""
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, text
    end = re.search(r"^---[ \t]*$", text[4:], flags=re.MULTILINE)
    if end is None:
        return None, text
    return text[4 : 4 + end.start()], text[4 + end.end() :]


def parse_frontmatter(block: str) -> dict[str, str | list[str]]:
    """Top-level scalars and lists; anything unexpected is skipped, never raised."""
    fields: dict[str, str | list[str]] = {}
    current: list[str] | None = None
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = ITEM_RE.match(line)
        if item and current is not None:
            current.append(_unquote(item.group(1)))
            continue
        match = KEY_RE.match(line)
        if match is None:
            current = None
            continue
        key, value = match.group(1), (match.group(2) or "").strip()
        if not value:
            current = []
            fields[key] = current
        elif value.startswith("[") and value.endswith("]") and not value.startswith("[["):
            current = None
            fields[key] = _flow_list(value)
        else:
            current = None
            fields[key] = _unquote(value)
    return fields


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part for part in re.split(r"[,\s]+", value.strip()) if part]
    return []


def note_tags(text: str) -> list[str] | None:
    """The note's tags, or None without frontmatter."""
    block, _ = split_frontmatter(text)
    if block is None:
        return None
    return [tag.lstrip("#") for tag in as_list(parse_frontmatter(block).get("tags"))]


def h1_title(body: str) -> str:
    match = H1_RE.search(body)
    return " ".join(match.group(1).split()) if match else ""
