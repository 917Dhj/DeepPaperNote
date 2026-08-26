#!/usr/bin/env python3
"""Write the final Markdown note into an Obsidian-style vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from common import (
    emit,
    ensure_parent,
    file_sha256,
    maybe_load_json_record,
    resolve_domain_subdir,
    resolve_note_asset_dir,
    resolve_note_output_mode,
    resolve_obsidian_note_path,
    runtime_config,
)
from lint_note import inspect_reference_hygiene
from localization import normalize_output_language, require_artifact_output_language


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "write obsidian note")
    p.add_argument("--input", default="", help="Metadata JSON path or JSON string.")
    p.add_argument("--content-file", default="", help="Path to the final Markdown content.")
    p.add_argument("--content", default="", help="Inline Markdown content.")
    p.add_argument("--stdin", action="store_true", help="Read Markdown content from stdin.")
    p.add_argument(
        "--lint-json",
        default="",
        help="Required Final Note Lint JSON for Formal Save.",
    )
    p.add_argument(
        "--figure-decisions",
        default="",
        help="Required Figure/Table Decisions JSON for Formal Save.",
    )
    p.add_argument("--title", default="", help="Explicit title override.")
    p.add_argument("--output", default="", help="JSON status output path.")
    p.add_argument("--vault", default="", help="Target Obsidian vault path.")
    p.add_argument("--save-mode", choices=("workspace", "obsidian"), default="")
    p.add_argument("--papers-dir", default="", help="Vault-relative paper directory.")
    p.add_argument("--subdir", default="", help="Vault-relative subdirectory.")
    p.add_argument("--filename", default="", help="Explicit note filename.")
    p.add_argument("--asset-subdir", default="images", help="Asset folder name relative to the note directory.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    p.add_argument("--language", default="", help="Run Override for output language: en or zh-CN.")
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


def require_reference_hygiene(note_text: str, stage: str) -> None:
    issues = inspect_reference_hygiene(note_text)
    if not issues:
        return
    first = issues[0]
    match = str(first.get("match", "")).strip()
    line_number = first.get("line_number", "")
    detail = f": {match}" if match else ""
    line_detail = f" on line {line_number}" if line_number else ""
    raise SystemExit(
        f"write_obsidian_note.py refused to write note because reference hygiene gate failed"
        f" {stage}{line_detail}{detail}."
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
        current_sha256 = file_sha256(source_image)
        review = item.get("visual_review", {})
        if (
            not isinstance(review, dict)
            or str(review.get("status", "")).strip() != "pass"
            or str(review.get("reviewed_asset_sha256", "")).strip() != current_sha256
            or str(item.get("source_image_sha256", "")).strip() != current_sha256
        ):
            label = item.get("source_id") or item.get("label") or item.get("item_id") or "unknown"
            raise SystemExit(
                f"Insert decision for {label} does not match its reviewed asset SHA-256."
            )
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
        if file_sha256(dest_image) != current_sha256:
            raise SystemExit(
                f"Materialized image bytes do not match the reviewed asset SHA-256: {filename}"
            )
        materialized.append(
            {
                "source_id": item.get("source_id") or item.get("label") or item.get("item_id") or "",
                "source_image": str(source_image.resolve()),
                "dest_image_path": str(dest_image),
                "relative_markdown_path": expected_relative,
                "reviewed_asset_sha256": current_sha256,
            }
        )
    return materialized


def lint_failure_message(lint: dict, gate: str, lint_path: str) -> str:
    detail_parts: list[str] = []
    for warning in lint.get("warnings", []) or []:
        if warning:
            detail_parts.append(str(warning))
    for issue_key in (
        "core_info_structure_issues",
        "figure_structure_issues",
        "planning_artifact_issues",
        "substantive_content_issues",
        "mixed_language_issues",
        "mechanical_translation_artifact_issues",
        "linebreak_issues",
        "code_math_issues",
        "math_render_issues",
        "reference_hygiene_issues",
    ):
        issues = lint.get(issue_key, []) or []
        if not issues:
            continue
        first = issues[0]
        if isinstance(first, dict):
            reason = first.get("reason") or first.get("line") or first.get("snippet") or first
            detail_parts.append(f"{issue_key}: {reason}")
        else:
            detail_parts.append(f"{issue_key}: {first}")
    details = "; ".join(detail_parts[:4])
    suffix = f" Details: {details}." if details else ""
    return f"write_obsidian_note.py refused to write note because {gate} gate failed.{suffix} See lint JSON: {lint_path}"


def require_lint_gate(lint: dict, key: str, gate: str, lint_path: str) -> None:
    if not lint.get(key, False):
        raise SystemExit(lint_failure_message(lint, gate, lint_path))


def main() -> None:
    args = parser().parse_args()
    config = runtime_config(
        cli_overrides={
            "output_language": args.language,
            "save_mode": args.save_mode or ("obsidian" if args.vault else ""),
            "obsidian_vault": args.vault,
            "papers_dir": args.papers_dir,
        }
    )
    output_language = normalize_output_language(args.language or str(config.get("output_language", "")) or None)

    record = maybe_load_json_record(args.input) or {}
    title = args.title or str(record.get("title", "")).strip()
    if not title:
        raise SystemExit("write_obsidian_note.py requires --title or metadata with a title.")

    if not args.lint_json:
        raise SystemExit("Formal Save requires Final Note Lint with output_language.")
    lint_path = str(Path(args.lint_json).expanduser().resolve())
    # utf-8-sig tolerates a BOM in the lint JSON (e.g. produced/edited on
    # Windows) that would otherwise crash json.loads before any gate check.
    lint = json.loads(Path(lint_path).read_text(encoding="utf-8-sig"))
    try:
        require_artifact_output_language(lint, "lint artifact", output_language)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    require_lint_gate(lint, "passes_basic_structure", "basic structure", lint_path)
    require_lint_gate(lint, "passes_style_gate", "style", lint_path)
    require_lint_gate(lint, "passes_math_gate", "math", lint_path)
    if "passes_figure_gate" in lint and not lint.get("passes_figure_gate", False):
        raise SystemExit(lint_failure_message(lint, "figure", lint_path))
    if "passes_plan_gate" in lint and not lint.get("passes_plan_gate", False):
        raise SystemExit(lint_failure_message(lint, "plan", lint_path))
    if "passes_substantive_content" in lint and not lint.get("passes_substantive_content", False):
        raise SystemExit(lint_failure_message(lint, "substantive content", lint_path))
    if "passes_reference_hygiene_gate" in lint and not lint.get("passes_reference_hygiene_gate", False):
        raise SystemExit(lint_failure_message(lint, "reference hygiene", lint_path))

    if not args.figure_decisions:
        raise SystemExit("Formal Save requires Figure/Table Decisions with output_language.")
    figure_decisions = maybe_load_json_record(args.figure_decisions)
    if figure_decisions is None:
        raise SystemExit(f"Expected JSON object for --figure-decisions: {args.figure_decisions}")
    try:
        require_artifact_output_language(
            figure_decisions,
            "Figure/Table Decisions",
            output_language,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.content_file:
        # utf-8-sig strips a leading BOM so it is never written into the saved
        # note (a leading BOM breaks Obsidian frontmatter / the H1 title).
        note_text = Path(args.content_file).expanduser().resolve().read_text(encoding="utf-8-sig")
    elif args.content:
        note_text = args.content
    elif args.stdin:
        note_text = sys.stdin.read()
    else:
        raise SystemExit("write_obsidian_note.py requires --content-file, --content, or --stdin.")
    note_text = note_text.replace("\r\n", "\n")
    lint_note_sha256 = str(lint.get("note_sha256", "")).strip()
    if not lint_note_sha256:
        raise SystemExit("lint artifact requires note_sha256.")
    note_sha256 = hashlib.sha256(note_text.encode("utf-8")).hexdigest()
    if lint_note_sha256 != note_sha256:
        raise SystemExit(
            "write_obsidian_note.py refused to write note because the final note "
            "changed after Final Note Lint; rerun lint under the same output_language."
        )
    require_reference_hygiene(note_text, "before save")

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
    asset_dir = resolve_note_asset_dir(target_path, args.asset_subdir)
    asset_subdir = asset_dir.relative_to(target_path.parent).as_posix()
    ensure_parent(target_path)
    materialized_figures = (
        materialize_insert_decisions(
            note_text,
            target_path,
            figure_decisions,
            asset_subdir,
        )
        if figure_decisions
        else []
    )
    Path(target_path).write_text(note_text, encoding="utf-8")
    require_reference_hygiene(Path(target_path).read_text(encoding="utf-8"), "after save")
    asset_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "ok",
        "script": "write_obsidian_note.py",
        "output_language": output_language,
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
