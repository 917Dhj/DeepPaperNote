#!/usr/bin/env python3
"""Locate a Zotero attachment file inside common local Zotero storage directories."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import emit, normalize_whitespace


DEFAULT_STORAGE_ROOTS = [
    "~/Zotero/storage",
    "~/Library/Application Support/Zotero/storage",
]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "locate zotero attachment")
    p.add_argument("--attachment-key", default="", help="Zotero attachment key such as GBH8G5JP.")
    p.add_argument("--filename", default="", help="Attachment filename when known.")
    p.add_argument(
        "--storage-roots",
        nargs="*",
        default=[],
        help="Optional Zotero storage roots. Defaults to common local Zotero paths.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def iter_storage_roots(custom_roots: list[str]) -> list[Path]:
    roots = custom_roots or DEFAULT_STORAGE_ROOTS
    resolved: list[Path] = []
    for root in roots:
        path = Path(root).expanduser().resolve()
        if path.exists() and path.is_dir():
            resolved.append(path)
    return resolved


def choose_pdf_file(directory: Path, filename_hint: str) -> Path | None:
    if filename_hint:
        candidate = directory / filename_hint
        if candidate.exists() and candidate.is_file():
            return candidate
    pdfs = sorted(
        [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
    )
    if len(pdfs) == 1:
        return pdfs[0]
    if filename_hint:
        hint = normalize_whitespace(filename_hint).lower()
        for pdf in pdfs:
            if normalize_whitespace(pdf.name).lower() == hint:
                return pdf
    return pdfs[0] if pdfs else None


def locate_attachment(attachment_key: str, filename: str, storage_roots: list[Path]) -> tuple[Path | None, Path | None]:
    filename = normalize_whitespace(filename)
    if attachment_key:
        for root in storage_roots:
            directory = root / attachment_key
            if directory.exists() and directory.is_dir():
                return directory, choose_pdf_file(directory, filename)

    if filename:
        lower_filename = filename.lower()
        for root in storage_roots:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                candidate = child / filename
                if candidate.exists() and candidate.is_file():
                    return child, candidate
                for pdf in child.glob("*.pdf"):
                    if pdf.name.lower() == lower_filename:
                        return child, pdf
    return None, None


def main() -> None:
    args = parser().parse_args()
    attachment_key = normalize_whitespace(args.attachment_key)
    filename = normalize_whitespace(args.filename)
    roots = iter_storage_roots(list(args.storage_roots))

    if not attachment_key and not filename:
        raise SystemExit("locate_zotero_attachment.py requires --attachment-key or --filename.")

    directory, pdf_path = locate_attachment(attachment_key, filename, roots)
    payload = {
        "status": "ok" if pdf_path else "not_found",
        "script": "locate_zotero_attachment.py",
        "attachment_key": attachment_key,
        "filename": filename,
        "searched_roots": [str(root) for root in roots],
        "storage_dir": str(directory) if directory else "",
        "local_pdf_path": str(pdf_path) if pdf_path else "",
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
