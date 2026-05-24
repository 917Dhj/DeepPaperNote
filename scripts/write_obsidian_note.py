#!/usr/bin/env python3
"""Write the final Markdown note into an Obsidian-style vault."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from common import (
    emit,
    ensure_parent,
    maybe_load_json_record,
    resolve_domain_subdir,
    resolve_note_output_mode,
    resolve_obsidian_note_path,
    runtime_config,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "write obsidian note")
    p.add_argument("--input", default="", help="Metadata JSON path or JSON string.")
    p.add_argument("--content-file", default="", help="Path to the final Markdown content.")
    p.add_argument("--content", default="", help="Inline Markdown content.")
    p.add_argument("--stdin", action="store_true", help="Read Markdown content from stdin.")
    p.add_argument("--lint-json", default="", help="Optional lint JSON path. Refuse write if structure, style, or math gate failed.")
    p.add_argument(
        "--figure-decisions",
        default="",
        help="Optional figure/table decisions JSON. Insert decisions must have referenced materialized images.",
    )
    p.add_argument("--title", default="", help="Explicit title override.")
    p.add_argument("--output", default="", help="JSON status output path.")
    p.add_argument("--vault", default="", help="Target Obsidian vault path.")
    p.add_argument("--subdir", default="", help="Vault-relative subdirectory.")
    p.add_argument("--filename", default="", help="Explicit note filename.")
    p.add_argument("--asset-subdir", default="images", help="Asset folder name relative to the note directory.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    return p


def insert_decisions(decisions: dict) -> list[dict]:
    items = decisions.get("decisions", []) if isinstance(decisions, dict) else []
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("decision", "")).strip() == "insert"
    ]


def safe_image_filename(filename: str, source_image: Path) -> str:
    candidate = filename.strip() or source_image.name
    if (
        not candidate
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or Path(candidate).is_absolute()
    ):
        raise SystemExit(f"Unsafe figure image filename in insert decision: {candidate}")
    return candidate


def embed_target_matches(target: str, expected_relative: str) -> bool:
    normalized = target.strip().strip("<>").split("|", 1)[0]
    if normalized == expected_relative:
        return True
    return normalized.endswith(f"/{expected_relative}")


def note_references_image_embed(note_text: str, expected_relative: str) -> bool:
    markdown_targets = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", note_text)
    obsidian_targets = re.findall(r"!\[\[([^\]]+)\]\]", note_text)
    return any(
        embed_target_matches(target, expected_relative)
        for target in markdown_targets + obsidian_targets
    )


def materialize_insert_decisions(
    note_text: str,
    target_path: Path,
    decisions: dict,
    asset_subdir: str,
) -> list[dict]:
    materialized: list[dict] = []
    asset_dir = target_path.parent / asset_subdir
    for item in insert_decisions(decisions):
        source_value = str(item.get("source_image_path", "")).strip()
        source_image = Path(source_value).expanduser()
        if not source_value or not source_image.is_file():
            label = item.get("source_id") or item.get("label") or item.get("item_id") or "unknown"
            raise SystemExit(f"Insert decision source image does not exist for {label}: {source_value}")
        filename = safe_image_filename(
            str(item.get("source_image_filename", "")),
            source_image,
        )
        expected_relative = f"{asset_subdir}/{filename}"
        if not note_references_image_embed(note_text, expected_relative):
            label = item.get("source_id") or item.get("label") or item.get("item_id") or filename
            raise SystemExit(
                f"Insert decision for {label} is not referenced as an image embed: {expected_relative}."
            )
        asset_dir.mkdir(parents=True, exist_ok=True)
        dest_image = asset_dir / filename
        if dest_image.resolve().parent != asset_dir.resolve():
            raise SystemExit(f"Unsafe figure image destination: {dest_image}")
        if source_image.resolve() != dest_image.resolve():
            shutil.copy2(source_image, dest_image)
        materialized.append(
            {
                "source_id": item.get("source_id") or item.get("label") or item.get("item_id") or "",
                "source_image": str(source_image.resolve()),
                "dest_image_path": str(dest_image),
                "relative_markdown_path": expected_relative,
            }
        )
    return materialized


def main() -> None:
    args = parser().parse_args()

    record = maybe_load_json_record(args.input) or {}
    title = args.title or str(record.get("title", "")).strip()
    if not title:
        raise SystemExit("write_obsidian_note.py requires --title or metadata with a title.")

    if args.lint_json:
        lint = json.loads(Path(args.lint_json).expanduser().resolve().read_text(encoding="utf-8"))
        if not lint.get("passes_basic_structure", False):
            raise SystemExit("write_obsidian_note.py refused to write note because basic structure lint failed.")
        if not lint.get("passes_style_gate", False):
            raise SystemExit("write_obsidian_note.py refused to write note because style gate failed.")
        if not lint.get("passes_math_gate", False):
            raise SystemExit("write_obsidian_note.py refused to write note because math gate failed.")
        if "passes_figure_gate" in lint and not lint.get("passes_figure_gate", False):
            raise SystemExit("write_obsidian_note.py refused to write note because figure gate failed.")
        if "passes_plan_gate" in lint and not lint.get("passes_plan_gate", False):
            raise SystemExit("write_obsidian_note.py refused to write note because plan gate failed.")
        if "passes_substantive_content" in lint and not lint.get("passes_substantive_content", False):
            raise SystemExit("write_obsidian_note.py refused to write note because substantive content gate failed.")

    if args.content_file:
        note_text = Path(args.content_file).expanduser().resolve().read_text(encoding="utf-8")
    elif args.content:
        note_text = args.content
    elif args.stdin:
        note_text = sys.stdin.read()
    else:
        raise SystemExit("write_obsidian_note.py requires --content-file, --content, or --stdin.")

    config = runtime_config()
    if args.vault:
        config["obsidian_vault"] = args.vault
    resolved_subdir = resolve_domain_subdir(
        config,
        title=title,
        abstract=str(record.get("abstract", "")),
        subdir=args.subdir,
    )

    target_path = resolve_obsidian_note_path(
        config,
        title=title,
        subdir=resolved_subdir,
        filename=args.filename,
    )
    ensure_parent(target_path)
    asset_dir = target_path.parent / args.asset_subdir
    figure_decisions = maybe_load_json_record(args.figure_decisions) if args.figure_decisions else {}
    if args.figure_decisions and figure_decisions is None:
        raise SystemExit(f"Expected JSON object for --figure-decisions: {args.figure_decisions}")
    materialized_figures = (
        materialize_insert_decisions(
            note_text,
            target_path,
            figure_decisions,
            args.asset_subdir,
        )
        if figure_decisions
        else []
    )
    Path(target_path).write_text(note_text, encoding="utf-8")
    asset_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "ok",
        "script": "write_obsidian_note.py",
        "paper_id": args.paper_id or record.get("paper_id", ""),
        "title": title,
        "note_path": str(target_path),
        "subdir": resolved_subdir,
        "images_dir": str(asset_dir),
        "materialized_figures": materialized_figures,
    }
    output_mode, root_path = resolve_note_output_mode(config)
    payload["output_mode"] = output_mode
    payload["base_output_root"] = str(root_path)
    if config.get("obsidian_vault"):
        payload["vault"] = str(Path(config["obsidian_vault"]).expanduser().resolve())
    emit(payload, args.output)


if __name__ == "__main__":
    main()
