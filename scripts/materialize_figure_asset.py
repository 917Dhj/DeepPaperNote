#!/usr/bin/env python3
"""Copy a chosen figure candidate into the Obsidian vault and return embed markup."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from common import emit, maybe_load_json_record, resolve_note_output_mode, resolve_obsidian_note_path, runtime_config


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "materialize figure asset")
    p.add_argument("--source-image", required=True, help="Source image path selected by the model.")
    p.add_argument("--input", default="", help="Optional metadata JSON path or JSON string.")
    p.add_argument("--title", default="", help="Explicit paper title.")
    p.add_argument("--vault", default="", help="Target Obsidian vault path.")
    p.add_argument("--subdir", default="", help="Vault-relative note subdirectory.")
    p.add_argument("--filename", default="", help="Optional note filename override.")
    p.add_argument("--asset-subdir", default="images", help="Asset folder name relative to the note directory.")
    p.add_argument("--label", default="", help="Optional human-readable label for the figure.")
    p.add_argument("--output", default="", help="JSON output path.")
    return p


def main() -> None:
    args = parser().parse_args()
    record = maybe_load_json_record(args.input) or {}
    title = args.title or str(record.get("title", "")).strip()
    if not title:
        raise SystemExit("materialize_figure_asset.py requires --title or metadata with a title.")

    config = runtime_config()
    if args.vault:
        config["obsidian_vault"] = args.vault

    note_path = resolve_obsidian_note_path(
        config,
        title=title,
        subdir=args.subdir,
        filename=args.filename,
    )
    source_image = Path(args.source_image).expanduser().resolve()
    if not source_image.exists():
        raise SystemExit(f"Source image does not exist: {source_image}")

    asset_dir = note_path.parent / args.asset_subdir
    asset_dir.mkdir(parents=True, exist_ok=True)
    dest_image = asset_dir / source_image.name
    shutil.copy2(source_image, dest_image)

    output_mode, root_root = resolve_note_output_mode(config)
    relative_from_note = dest_image.relative_to(note_path.parent)
    relative_markdown_embed = f"![{args.label or source_image.stem}]({relative_from_note.as_posix()})"
    absolute_markdown_embed = f"![{args.label or source_image.stem}]({dest_image})"

    payload = {
        "status": "ok",
        "script": "materialize_figure_asset.py",
        "title": title,
        "note_path": str(note_path),
        "source_image": str(source_image),
        "dest_image_path": str(dest_image),
        "absolute_markdown_embed": absolute_markdown_embed,
        "relative_markdown_embed": relative_markdown_embed,
        "label": args.label,
        "output_mode": output_mode,
    }

    if output_mode == "obsidian":
        vault_relative = dest_image.relative_to(root_root)
        payload["vault_relative_image_path"] = vault_relative.as_posix()
        payload["obsidian_embed"] = f"![[{vault_relative.as_posix()}]]"
    emit(payload, args.output)


if __name__ == "__main__":
    main()
