#!/usr/bin/env python3
"""Create or update `<vault>/DeepPaperNote/research-memory.md` from confirmed answers.

`--create CONTENT.json` renders a new file and requires `--expected-sha256 absent`.
`--update CHANGES.json` edits only the listed items and requires the SHA-256 the
interview started from, so a hand edit made during the interview is never lost.
`--dry-run` returns the resulting text and a diff without writing.
See references/file-contract.md for both JSON shapes.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import memory_format
from memory_vault import h1_title, locate, memory_path, sha256_file, split_frontmatter


class Refused(Exception):
    pass


def _resolve_evidence(vault: Path, observations: list[dict] | None) -> list[dict] | None:
    """Replace each evidence target with (target, title); every target must be a vault note."""
    if observations is None:
        return None
    wanted = {str(target) for item in observations for target in item.get("evidence") or []}
    titles: dict[str, str] = {}
    if wanted:
        for path in vault.rglob("*.md"):
            if path.stem in wanted and path.stem not in titles:
                _, body = split_frontmatter(path.read_text(encoding="utf-8-sig", errors="replace"))
                titles[path.stem] = h1_title(body) or path.stem
    missing = sorted(wanted - titles.keys())
    if missing:
        raise Refused(f"Evidence links match no note in the vault: {', '.join(missing)}")
    return [
        {**item, "evidence": [(str(target), titles[str(target)]) for target in item.get("evidence") or []]}
        for item in observations
    ]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".research-memory.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def run(args: argparse.Namespace) -> dict:
    located = locate(vault=args.vault or None)
    if located["status"] != "ok":
        raise Refused(f"No usable vault ({located['status']}); pass --vault.")
    vault = Path(located["vault"])
    path = memory_path(vault)
    current = sha256_file(path)
    payload = json.loads(Path(args.create or args.update).read_text(encoding="utf-8"))
    if args.create:
        if args.expected_sha256 != "absent" or current:
            raise Refused("research-memory.md already exists; rerun the aggregate and update it instead.")
        language = args.language or located["language"]
        before = ""
        content = {**payload, "observations": _resolve_evidence(vault, payload.get("observations") or [])}
        after = memory_format.render_new(content, language, today=args.today)
    else:
        if not current or current != args.expected_sha256:
            raise Refused(
                "research-memory.md changed since the interview read it; rerun the aggregate, "
                "show the user the current file, and confirm the changes again."
            )
        before = path.read_text(encoding="utf-8")
        changes = {**payload, "observations": _resolve_evidence(vault, payload.get("observations"))}
        after = memory_format.apply_changes(before, changes, today=args.today)
    parsed = memory_format.parse(after)
    if parsed["language"] is None:
        raise Refused("The result lost its research-memory sections; nothing was written.")
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True),
            fromfile="research-memory.md (current)", tofile="research-memory.md (new)",
        )
    )
    written = not args.dry_run and after != before
    if written:
        _atomic_write(path, after)
    return {
        "status": "ok",
        "written": written,
        "path": str(path),
        "sha256_before": current,
        "sha256_after": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "diff": diff,
        "text": after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", default="", help="Confirmed content JSON for a new file.")
    mode.add_argument("--update", default="", help="Confirmed change list JSON for an existing file.")
    parser.add_argument("--expected-sha256", required=True, help="Hash the interview read, or 'absent'.")
    parser.add_argument("--vault", default="", help="Obsidian vault; defaults to DeepPaperNote's configuration.")
    parser.add_argument("--language", default="", help="zh-CN or en, for a new file.")
    parser.add_argument("--today", default=date.today().isoformat(), help="YYYY-MM-DD for `updated`.")
    parser.add_argument("--dry-run", action="store_true", help="Return text and diff without writing.")
    args = parser.parse_args()
    try:
        result = run(args)
    except (Refused, ValueError, OSError) as exc:
        sys.stdout.write(json.dumps({"status": "refused", "reason": str(exc)}, ensure_ascii=False) + "\n")
        raise SystemExit(1) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
