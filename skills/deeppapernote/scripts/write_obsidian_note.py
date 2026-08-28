#!/usr/bin/env python3
"""Write the final Markdown note into an Obsidian-style vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
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

PAPER_DIRECTORY_SIDECAR = ".deeppapernote.json"
SOURCE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_FILE_ATTRIBUTE_HIDDEN = 0x2
WINDOWS_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


def ensure_sidecar_hidden(
    path: Path,
    *,
    platform: str | None = None,
    get_attributes=None,
    set_attributes=None,
) -> None:
    if (platform or os.name) != "nt":
        return
    if (get_attributes is None) != (set_attributes is None):
        raise ValueError("get_attributes and set_attributes must be provided together")

    if get_attributes is None:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_attributes = kernel32.GetFileAttributesW
        get_attributes.argtypes = [ctypes.c_wchar_p]
        get_attributes.restype = ctypes.c_uint32
        set_attributes = kernel32.SetFileAttributesW
        set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        set_attributes.restype = ctypes.c_int

        def fail() -> None:
            raise ctypes.WinError(ctypes.get_last_error())

    else:

        def fail() -> None:
            raise OSError(f"Could not set Windows Hidden attribute: {path}")

    path_value = str(path)
    current = int(get_attributes(path_value))
    if current == WINDOWS_INVALID_FILE_ATTRIBUTES:
        fail()
    if not set_attributes(path_value, current | WINDOWS_FILE_ATTRIBUTE_HIDDEN):
        fail()
    verified = int(get_attributes(path_value))
    if (
        verified == WINDOWS_INVALID_FILE_ATTRIBUTES
        or not verified & WINDOWS_FILE_ATTRIBUTE_HIDDEN
    ):
        fail()


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
    p.add_argument(
        "--source-manifest",
        default="",
        help="Required Source Manifest JSON for Obsidian Save Target Admission.",
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
    p.add_argument(
        "--preflight",
        action="store_true",
        help="Resolve the Obsidian Save Target without writing files.",
    )
    p.add_argument(
        "--overwrite-existing-note",
        action="store_true",
        help="Overwrite a same-language note after explicit user confirmation.",
    )
    p.add_argument(
        "--expected-existing-note-sha256",
        default="",
        help="SHA-256 returned by the conflict that the user approved overwriting.",
    )
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
    created_paths: list[Path] | None = None,
) -> list[dict]:
    asset_dir = target_path.parent / asset_subdir
    pending: list[tuple[Path, Path, str, dict]] = []
    planned_hashes: dict[Path, str] = {}
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
        dest_image = asset_dir / filename
        if dest_image.resolve().parent != asset_dir.resolve():
            raise SystemExit(f"Unsafe figure image destination: {dest_image}")
        existing_planned_sha256 = planned_hashes.get(dest_image)
        if existing_planned_sha256 and existing_planned_sha256 != current_sha256:
            raise SystemExit(
                f"Insert decisions assign different bytes to the same image: {filename}"
            )
        planned_hashes[dest_image] = current_sha256
        if dest_image.is_file() and file_sha256(dest_image) != current_sha256:
            raise SystemExit(
                f"Refusing to save because an existing paper-local image has different bytes: "
                f"{filename}"
            )
        pending.append(
            (
                source_image,
                dest_image,
                current_sha256,
                {
                    "source_id": item.get("source_id")
                    or item.get("label")
                    or item.get("item_id")
                    or "",
                    "source_image": str(source_image.resolve()),
                    "dest_image_path": str(dest_image),
                    "relative_markdown_path": expected_relative,
                    "reviewed_asset_sha256": current_sha256,
                },
            )
        )

    if pending:
        asset_dir.mkdir(parents=True, exist_ok=True)
    materialized: list[dict] = []
    for source_image, dest_image, current_sha256, record in pending:
        if dest_image.is_file():
            if file_sha256(dest_image) != current_sha256:
                raise SystemExit(
                    f"Refusing to save because an existing paper-local image has different bytes: "
                    f"{dest_image.name}"
                )
        elif source_image.resolve() != dest_image.resolve():
            if created_paths is not None:
                created_paths.append(dest_image)
            shutil.copy2(source_image, dest_image)
        if file_sha256(dest_image) != current_sha256:
            raise SystemExit(
                f"Materialized image bytes do not match the reviewed asset SHA-256: "
                f"{dest_image.name}"
            )
        materialized.append(record)
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


def require_source_manifest(path_value: str) -> dict:
    if not path_value:
        raise SystemExit(
            "Obsidian Save Target Admission requires a Source Manifest with source_sha256."
        )
    manifest = maybe_load_json_record(path_value)
    if manifest is None or str(manifest.get("status", "")).strip() != "ok":
        raise SystemExit(f"Expected successful Source Manifest JSON: {path_value}")
    source_sha256 = str(manifest.get("source_sha256", "")).strip().lower()
    if not SOURCE_SHA256_RE.fullmatch(source_sha256):
        raise SystemExit("Source Manifest requires a 64-character source_sha256.")
    manifest["source_sha256"] = source_sha256
    return manifest


def language_note_path(target_path: Path, output_language: str) -> Path:
    suffix = target_path.suffix or ".md"
    stem = target_path.stem
    if stem.endswith(f".{output_language}"):
        return target_path
    return target_path.with_name(f"{stem}.{output_language}{suffix}")


def same_name_directories(vault: Path, directory_name: str) -> list[Path]:
    return sorted(
        {
            path.resolve()
            for path in vault.rglob("*")
            if (
                path.is_dir()
                and path.name == directory_name
                and path.resolve().is_relative_to(vault.resolve())
            )
        }
    )


def read_paper_directory_sidecar(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("artifact_type") != "deeppapernote_paper_directory"
        or payload.get("schema_version") != 1
        or not SOURCE_SHA256_RE.fullmatch(str(payload.get("source_sha256", "")))
        or not str(payload.get("note_stem", "")).strip()
        or Path(str(payload.get("note_stem", ""))).name != payload.get("note_stem")
    ):
        return None
    return payload


def source_directories(vault: Path, source_sha256: str) -> list[tuple[Path, dict]]:
    matches: list[tuple[Path, dict]] = []
    for sidecar_path in vault.rglob(PAPER_DIRECTORY_SIDECAR):
        if not sidecar_path.resolve().is_relative_to(vault.resolve()):
            continue
        payload = read_paper_directory_sidecar(sidecar_path)
        if payload is not None and payload["source_sha256"] == source_sha256:
            matches.append((sidecar_path.parent.resolve(), payload))
    return sorted(matches, key=lambda item: str(item[0]))


def block_directory_conflict(
    args: argparse.Namespace,
    *,
    conflict_code: str,
    target_directories: list[Path],
    source_sha256: str,
    output_language: str,
) -> None:
    payload = {
        "status": "blocked",
        "script": "write_obsidian_note.py",
        "conflict_code": conflict_code,
        "requires_user_confirmation": False,
        "target_directory": str(target_directories[0]),
        "matching_directories": [str(path) for path in target_directories],
        "source_sha256": source_sha256,
        "output_language": output_language,
    }
    emit(payload, args.output)
    raise SystemExit(2)


def block_note_conflict(
    args: argparse.Namespace,
    target_path: Path,
    *,
    conflict_code: str,
    source_sha256: str,
    output_language: str,
) -> None:
    emit(
        {
            "status": "blocked",
            "script": "write_obsidian_note.py",
            "conflict_code": conflict_code,
            "requires_user_confirmation": True,
            "target_directory": str(target_path.parent),
            "existing_note_path": str(target_path),
            "existing_note_sha256": file_sha256(target_path),
            "source_sha256": source_sha256,
            "output_language": output_language,
        },
        args.output,
    )
    raise SystemExit(2)


def resolve_obsidian_save_target(
    args: argparse.Namespace,
    config: dict,
    vault: Path,
    *,
    title: str,
    abstract: str,
    source_sha256: str,
    output_language: str,
) -> tuple[Path, str, str, bool, str]:
    source_matches = source_directories(vault, source_sha256)
    if len(source_matches) > 1:
        block_directory_conflict(
            args,
            conflict_code="multiple_source_directories",
            target_directories=[path for path, _ in source_matches],
            source_sha256=source_sha256,
            output_language=output_language,
        )

    resolved_subdir = ""
    recorded_language_target = False
    if source_matches:
        existing_dir, sidecar = source_matches[0]
        notes = sidecar.get("notes", {})
        if not isinstance(notes, dict):
            block_directory_conflict(
                args,
                conflict_code="invalid_language_note_record",
                target_directories=[existing_dir],
                source_sha256=source_sha256,
                output_language=output_language,
            )
        if output_language in notes:
            note_record = notes[output_language]
            filename = (
                str(note_record.get("filename", "")).strip()
                if isinstance(note_record, dict)
                else ""
            )
            if (
                not filename
                or filename in {".", ".."}
                or "/" in filename
                or "\\" in filename
                or Path(filename).is_absolute()
                or Path(filename).suffix.lower() != ".md"
            ):
                block_directory_conflict(
                    args,
                    conflict_code="invalid_language_note_record",
                    target_directories=[existing_dir],
                    source_sha256=source_sha256,
                    output_language=output_language,
                )
            target_path = existing_dir / filename
            recorded_language_target = True
            if not target_path.is_file():
                block_directory_conflict(
                    args,
                    conflict_code="recorded_language_note_missing",
                    target_directories=[existing_dir],
                    source_sha256=source_sha256,
                    output_language=output_language,
                )
        else:
            target_path = existing_dir / f"{sidecar['note_stem']}.md"
        admission = "reuse_source_directory"
        domain_routing_skipped = True
    else:
        identity_path = resolve_obsidian_note_path(
            config,
            title=title,
            filename=args.filename,
        )
        name_matches = same_name_directories(vault, identity_path.parent.name)
        if len(name_matches) > 1:
            block_directory_conflict(
                args,
                conflict_code="multiple_same_name_directories",
                target_directories=name_matches,
                source_sha256=source_sha256,
                output_language=output_language,
            )
        if name_matches:
            existing_dir = name_matches[0]
            if any(existing_dir.iterdir()):
                existing_sidecar = read_paper_directory_sidecar(
                    existing_dir / PAPER_DIRECTORY_SIDECAR
                )
                block_directory_conflict(
                    args,
                    conflict_code=(
                        "same_name_different_source"
                        if existing_sidecar is not None
                        else "unidentified_same_name_directory"
                    ),
                    target_directories=name_matches,
                    source_sha256=source_sha256,
                    output_language=output_language,
                )
            target_path = existing_dir / identity_path.name
            admission = "reuse_empty_same_name_directory"
            domain_routing_skipped = True
        else:
            resolved_subdir = resolve_domain_subdir(
                config,
                title=title,
                abstract=abstract,
                subdir=args.subdir,
            )
            target_path = resolve_obsidian_note_path(
                config,
                title=title,
                subdir=resolved_subdir,
                filename=args.filename,
            )
            admission = "new_directory"
            domain_routing_skipped = False

    if not recorded_language_target:
        target_path = language_note_path(target_path, output_language)
    approved_existing_note_sha256 = ""
    if target_path.is_file():
        existing_note_sha256 = file_sha256(target_path)
        if not args.overwrite_existing_note:
            block_note_conflict(
                args,
                target_path,
                conflict_code="same_language_note_exists",
                source_sha256=source_sha256,
                output_language=output_language,
            )
        expected_sha256 = args.expected_existing_note_sha256.strip().lower()
        if not SOURCE_SHA256_RE.fullmatch(expected_sha256):
            raise SystemExit(
                "--overwrite-existing-note requires a 64-character "
                "--expected-existing-note-sha256 from the conflict response."
            )
        if existing_note_sha256 != expected_sha256:
            block_note_conflict(
                args,
                target_path,
                conflict_code="stale_overwrite_confirmation",
                source_sha256=source_sha256,
                output_language=output_language,
            )
        approved_existing_note_sha256 = existing_note_sha256
        admission = "overwrite_same_language_note"
    elif args.overwrite_existing_note:
        raise SystemExit(
            "--overwrite-existing-note is only valid when the target language note exists."
        )

    return (
        target_path,
        resolved_subdir,
        admission,
        domain_routing_skipped,
        approved_existing_note_sha256,
    )


def write_paper_directory_sidecar(
    target_path: Path,
    *,
    paper_id: str,
    title: str,
    source_sha256: str,
    output_language: str,
    note_sha256: str,
) -> Path:
    sidecar_path = target_path.parent / PAPER_DIRECTORY_SIDECAR
    payload = read_paper_directory_sidecar(sidecar_path) or {
        "artifact_type": "deeppapernote_paper_directory",
        "schema_version": 1,
        "paper_id": paper_id,
        "title": title,
        "source_sha256": source_sha256,
        "note_stem": target_path.name.removesuffix(f".{output_language}{target_path.suffix}"),
        "notes": {},
    }
    if payload["source_sha256"] != source_sha256:
        raise SystemExit(f"Paper directory sidecar source mismatch: {sidecar_path}")
    notes = payload.get("notes")
    if not isinstance(notes, dict):
        notes = {}
        payload["notes"] = notes
    notes[output_language] = {
        "filename": target_path.name,
        "note_sha256": note_sha256,
    }
    fd, temp_name = tempfile.mkstemp(
        dir=sidecar_path.parent,
        prefix=f"{PAPER_DIRECTORY_SIDECAR}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp_path, sidecar_path)
    finally:
        temp_path.unlink(missing_ok=True)
    ensure_sidecar_hidden(sidecar_path)
    return sidecar_path


def atomic_write_note(path: Path, note_text: str) -> None:
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(note_text)
        if path.is_file():
            shutil.copymode(path, temp_path)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def backup_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    fd, backup_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".backup",
    )
    os.close(fd)
    backup_path = Path(backup_name)
    try:
        shutil.copy2(path, backup_path)
    except BaseException:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


def restore_file(path: Path, backup_path: Path | None) -> None:
    if backup_path is None:
        path.unlink(missing_ok=True)
    else:
        os.replace(backup_path, path)


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
    output_mode, root_path = resolve_note_output_mode(config)

    record = maybe_load_json_record(args.input) or {}
    title = args.title or str(record.get("title", "")).strip()
    if not title:
        raise SystemExit("write_obsidian_note.py requires --title or metadata with a title.")

    source_manifest = (
        require_source_manifest(args.source_manifest) if output_mode == "obsidian" else {}
    )
    admission = "workspace"
    domain_routing_skipped = False
    approved_existing_note_sha256 = ""
    if output_mode == "obsidian":
        (
            target_path,
            resolved_subdir,
            admission,
            domain_routing_skipped,
            approved_existing_note_sha256,
        ) = resolve_obsidian_save_target(
            args,
            config,
            root_path,
            title=title,
            abstract=str(record.get("abstract", "")),
            source_sha256=str(source_manifest["source_sha256"]),
            output_language=output_language,
        )
    else:
        if args.preflight:
            raise SystemExit("--preflight requires Obsidian save mode.")
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

    if args.preflight:
        emit(
            {
                "status": "ok",
                "script": "write_obsidian_note.py",
                "phase": "save_target_admission",
                "admission": admission,
                "domain_routing_skipped": domain_routing_skipped,
                "target_directory": str(target_path.parent),
                "note_path": str(target_path),
                "source_sha256": str(source_manifest["source_sha256"]),
                "output_language": output_language,
            },
            args.output,
        )
        return

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

    overwrote_existing_note = bool(approved_existing_note_sha256)
    if output_mode == "obsidian":
        # ponytail: this closes sequential TOCTOU changes; add a Vault lock only
        # if concurrent DeepPaperNote writers must be fully serialized.
        rechecked_target, _, _, _, rechecked_existing_sha256 = resolve_obsidian_save_target(
            args,
            config,
            root_path,
            title=title,
            abstract=str(record.get("abstract", "")),
            source_sha256=str(source_manifest["source_sha256"]),
            output_language=output_language,
        )
        if (
            rechecked_target.resolve() != target_path.resolve()
            or rechecked_existing_sha256 != approved_existing_note_sha256
        ):
            block_directory_conflict(
                args,
                conflict_code="save_target_changed",
                target_directories=[target_path.parent, rechecked_target.parent],
                source_sha256=str(source_manifest["source_sha256"]),
                output_language=output_language,
            )

    asset_dir = resolve_note_asset_dir(target_path, args.asset_subdir)
    asset_subdir = asset_dir.relative_to(target_path.parent).as_posix()
    asset_directory_existed = asset_dir.exists()
    ensure_parent(target_path)
    paper_id = (
        args.paper_id
        or str(source_manifest.get("paper_id", ""))
        or str(record.get("paper_id", ""))
    )
    sidecar_path = (
        target_path.parent / PAPER_DIRECTORY_SIDECAR
        if output_mode == "obsidian"
        else None
    )
    note_backup = None
    sidecar_backup = None
    created_assets: list[Path] = []
    note_attempted = False
    sidecar_attempted = False
    try:
        note_backup = backup_file(target_path)
        sidecar_backup = backup_file(sidecar_path) if sidecar_path is not None else None
        materialized_figures = (
            materialize_insert_decisions(
                note_text,
                target_path,
                figure_decisions,
                asset_subdir,
                created_assets,
            )
            if figure_decisions
            else []
        )
        if (
            approved_existing_note_sha256
            and file_sha256(target_path) != approved_existing_note_sha256
        ):
            block_note_conflict(
                args,
                target_path,
                conflict_code="stale_overwrite_confirmation",
                source_sha256=str(source_manifest["source_sha256"]),
                output_language=output_language,
            )
        note_attempted = True
        atomic_write_note(target_path, note_text)
        require_reference_hygiene(
            target_path.read_text(encoding="utf-8"),
            "after save",
        )
        asset_dir.mkdir(parents=True, exist_ok=True)
        if sidecar_path is not None:
            sidecar_attempted = True
            write_paper_directory_sidecar(
                target_path,
                paper_id=paper_id,
                title=title,
                source_sha256=str(source_manifest["source_sha256"]),
                output_language=output_language,
                note_sha256=note_sha256,
            )
    except BaseException:
        if sidecar_attempted and sidecar_path is not None:
            restore_file(sidecar_path, sidecar_backup)
            if sidecar_backup is not None:
                try:
                    ensure_sidecar_hidden(sidecar_path)
                except OSError:
                    pass
        if note_attempted:
            restore_file(target_path, note_backup)
        for created_asset in reversed(created_assets):
            created_asset.unlink(missing_ok=True)
        if not asset_directory_existed:
            try:
                asset_dir.rmdir()
            except OSError:
                pass
        raise
    finally:
        if note_backup is not None:
            note_backup.unlink(missing_ok=True)
        if sidecar_backup is not None:
            sidecar_backup.unlink(missing_ok=True)

    payload = {
        "status": "ok",
        "script": "write_obsidian_note.py",
        "output_language": output_language,
        "paper_id": paper_id,
        "title": title,
        "note_path": str(target_path),
        "subdir": resolved_subdir,
        "images_dir": str(asset_dir),
        "materialized_figures": materialized_figures,
        "overwrote_existing_note": overwrote_existing_note,
        "admission": admission,
        "domain_routing_skipped": domain_routing_skipped,
    }
    if sidecar_path is not None:
        payload["sidecar_path"] = str(sidecar_path)
        payload["source_sha256"] = str(source_manifest["source_sha256"])
    payload["output_mode"] = output_mode
    payload["base_output_root"] = str(root_path)
    if config.get("obsidian_vault"):
        payload["vault"] = str(Path(config["obsidian_vault"]).expanduser().resolve())
    emit(payload, args.output)


if __name__ == "__main__":
    main()
