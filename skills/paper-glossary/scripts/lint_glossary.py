#!/usr/bin/env python3
"""Validate central term-library Markdown notes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_contracts import (
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_CONFIDENCE_VALUES,
    GLOSSARY_DISCLAIMER,
    GLOSSARY_LABEL_CONFIDENCE,
    GLOSSARY_LABEL_DEFINITION,
    GLOSSARY_OCCURRENCE_HEADING,
)
from glossary_common import elapsed_ms, emit

DISCLAIMER_KEYPHRASE = "非某篇论文"
OCCURRENCE_LINK_RE = re.compile(r"(?m)^\s*-\s*\[\[[^\]]+\]\]")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "lint glossary notes")
    p.add_argument(
        "--input",
        action="append",
        default=[],
        help="Term note Markdown path. Repeat for multiple changed notes.",
    )
    p.add_argument("--terms-dir", default="", help="Folder of term notes to lint.")
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def _issue(code: str, **details: Any) -> dict[str, Any]:
    payload = {"code": code}
    payload.update(details)
    return payload


def _section_body(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(heading)}\s*$", line.strip()):
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^##\s+", lines[index].strip()):
            end = index
            break
    return "\n".join(lines[start:end])


def _field_value(body: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*(.+)", body)
    return match.group(1).strip() if match else ""


def _has_valid_confidence(body: str) -> bool:
    value = _field_value(body, GLOSSARY_LABEL_CONFIDENCE)
    return value in GLOSSARY_CONFIDENCE_VALUES


def lint_term_file_text(text: str) -> dict[str, Any]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    issues: list[dict[str, Any]] = []

    concept = _section_body(text, GLOSSARY_CONCEPT_HEADING)
    occurrence = _section_body(text, GLOSSARY_OCCURRENCE_HEADING)

    if "[!warning]" not in text or DISCLAIMER_KEYPHRASE not in text.replace(" ", ""):
        issues.append(_issue("term_disclaimer_missing"))
    if concept is None:
        issues.append(_issue("term_concept_zone_missing"))
    else:
        if not _field_value(concept, GLOSSARY_LABEL_DEFINITION):
            issues.append(_issue("term_definition_missing"))
        if not _has_valid_confidence(concept):
            issues.append(_issue("term_confidence_invalid"))
    if occurrence is None:
        issues.append(_issue("term_occurrence_zone_missing"))
    elif not OCCURRENCE_LINK_RE.search(occurrence):
        issues.append(_issue("term_occurrence_reference_missing"))

    return {"passes": not issues, "issues": issues}


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    if not args.input and not args.terms_dir:
        raise SystemExit("lint_glossary.py requires --input or --terms-dir.")

    files: list[Path] = []
    seen: set[Path] = set()
    for value in args.input:
        path = Path(value).expanduser().resolve()
        if path not in seen:
            seen.add(path)
            files.append(path)
    if args.terms_dir:
        terms_dir = Path(args.terms_dir).expanduser().resolve()
        if not terms_dir.is_dir():
            raise SystemExit(f"--terms-dir must be an existing directory: {terms_dir}")
        for path in sorted(terms_dir.glob("*.md")):
            path = path.resolve()
            if path not in seen:
                seen.add(path)
                files.append(path)
    if not files:
        raise SystemExit("No glossary markdown files found.")

    results: list[dict[str, Any]] = []
    for path in files:
        result = lint_term_file_text(path.read_text(encoding="utf-8-sig"))
        results.append({"path": str(path), **result})

    passed = sum(1 for result in results if result["passes"])
    emit(
        {
            "status": "ok",
            "script": "lint_glossary.py",
            "passes_glossary": all(result["passes"] for result in results),
            "files": results,
            "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
            "elapsed_ms": elapsed_ms(started),
        },
        args.output,
    )


if __name__ == "__main__":
    main()
