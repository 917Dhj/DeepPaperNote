#!/usr/bin/env python3
"""Write the final Markdown note into an Obsidian-style vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path

from _final_quality import (
    advance_state,
    canonical_note_text,
    require_recorded_pass,
    strict_json_loads,
    validate_quality,
    validate_readability,
)
from _frontmatter import FrontmatterError, parse_frontmatter
from _user_notes import (
    inspect_existing_user_notes,
    merge_user_notes,
    restore_generated_text,
    split_user_notes,
)
from _domain_routing import (
    DomainChoiceError,
    domain_overview,
    domain_tag_issue,
    resolve_domain_choice,
    saved_domain,
)
from _note_paths import (
    resolve_note_asset_dir,
    resolve_note_output_mode,
    resolve_obsidian_note_path,
)
from common import (
    emit,
    ensure_parent,
    file_sha256,
    json_input_sha256,
    maybe_load_json_record,
    runtime_config,
)
from lint_grounding import validate_figure_decisions
from lint_note import inspect_reference_hygiene
from localization import normalize_output_language, require_artifact_output_language
from glossary_terms import frontmatter_links_outside_glossary, glossary_followup
from vault_connections import generated_wikilinks, unresolved_wikilinks
from paper_archive import (
    ArchiveError,
    admit_directory,
    archive_lock,
    directory_candidates,
    new_record,
    pdf_identity,
    read_record,
    record_work_evidence,
    register_source,
    safe_path,
    select_directory,
    source_details,
    verify_pdf,
    work_identity,
    write_record,
)

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
        "--grounding-lint-json",
        default="",
        help="Required Grounding Lint JSON for Formal Save.",
    )
    p.add_argument("--plan-file", default="", help="Required Note Plan JSON file for Formal Save.")
    p.add_argument("--final-quality-review", default="", help="Required Final Quality Review JSON.")
    p.add_argument(
        "--final-readability-review", default="", help="Required Final Readability Review JSON.",
    )
    p.add_argument(
        "--record-final-quality-review", action="store_true",
        help="Validate and record a quality review without accessing a save target.",
    )
    p.add_argument(
        "--source-manifest",
        default="",
        help="Required Source Manifest JSON for Formal Save and Obsidian Save Target Admission.",
    )
    p.add_argument("--title", default="", help="Explicit title override.")
    p.add_argument("--output", default="", help="JSON status output path.")
    p.add_argument("--vault", default="", help="Target Obsidian vault path.")
    p.add_argument("--save-mode", choices=("workspace", "obsidian"), default="")
    p.add_argument("--papers-dir", default="", help="Vault-relative paper directory.")
    p.add_argument(
        "--domain", default="",
        help="Domain folder the model chose for a new paper directory; see references/domain-routing.md.",
    )
    p.add_argument(
        "--new-domain-reason", default="",
        help="Why no existing domain fits; required when --domain names a new domain.",
    )
    p.add_argument("--filename", default="", help="Explicit note filename.")
    p.add_argument("--asset-subdir", default="images", help="Asset folder name relative to the note directory.")
    p.add_argument("--target-directory", default="", help="Previously selected existing paper directory.")
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


def safe_image_filename(filename: str, label: str) -> str:
    candidate = filename.strip()
    if not candidate:
        raise SystemExit(
            f"Insert decision for {label} has no vault_image_filename; "
            "rerun plan_figure_table_decisions.py."
        )
    if (
        candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or Path(candidate).is_absolute()
    ):
        raise SystemExit(f"Unsafe figure image filename in insert decision: {candidate}")
    return candidate


def require_resolvable_links(
    note_text: str, output_language: str, output_mode: str, root_path: Path, config: dict
) -> None:
    """Every generated `[[link]]` must open a vault note; workspace notes carry none.

    My Notes is the user's, so links there are never checked.
    """
    split = split_user_notes(note_text, output_language)
    generated = split[0] if split is not None else note_text
    if output_mode != "obsidian":
        links = generated_wikilinks(generated)
        if links:
            raise SystemExit(
                "Workspace mode is not connected to a vault, so the note must not contain "
                f"[[links]]: {', '.join(links)}"
            )
        return
    missing = unresolved_wikilinks(generated, root_path)
    if missing:
        raise SystemExit(
            "These [[links]] do not match any file in the Obsidian vault; link only to "
            f"connection candidates or listed glossary terms: {', '.join(missing)}"
        )
    outside, status = frontmatter_links_outside_glossary(generated, config)
    if outside:
        reason = (
            "they are not notes in the paper-glossary terms directory"
            if status == "ok"
            else f"no paper-glossary library shares this vault ({status})"
        )
        raise SystemExit(
            "Frontmatter [[links]] may only name glossary terms listed in the bundle's "
            f"glossary_terms, but {reason}: {', '.join(outside)}"
        )


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
    replaced_images: list[dict] | None = None,
) -> list[dict]:
    """Copy each inserted image into the paper's asset directory.

    An existing image with other bytes is backed up and replaced; each
    replacement is appended to ``replaced_images`` so the caller can restore it
    on rollback and report the other notes that also embed it.
    """
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
        ):
            label = item.get("source_id") or item.get("label") or item.get("item_id") or "unknown"
            raise SystemExit(
                f"Insert decision for {label} does not match its reviewed asset SHA-256."
            )
        # The vault name is fixed at planning time from the label; a crop
        # repair replaces the source image but never this name.
        filename = safe_image_filename(
            str(item.get("vault_image_filename", "")),
            str(item.get("source_id") or item.get("label") or item.get("item_id") or "unknown"),
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
            if file_sha256(dest_image) == current_sha256:
                materialized.append(record)
                continue
            replacement = {
                "path": dest_image,
                "backup": backup_file(dest_image),
                "relative_path": record["relative_markdown_path"],
                "also_embedded_by": notes_embedding(
                    target_path, record["relative_markdown_path"]
                ),
            }
            if replaced_images is not None:
                replaced_images.append(replacement)
        elif created_paths is not None:
            created_paths.append(dest_image)
        shutil.copy2(source_image, dest_image)
        if file_sha256(dest_image) != current_sha256:
            raise SystemExit(
                f"Materialized image bytes do not match the reviewed asset SHA-256: "
                f"{dest_image.name}"
            )
        materialized.append(record)
    return materialized


def notes_embedding(target_path: Path, relative_image: str) -> list[str]:
    """Name the other notes beside ``target_path`` that embed ``relative_image``."""
    names = []
    for note in sorted(target_path.parent.glob("*.md")):
        if note.name == target_path.name or not note.is_file():
            continue
        text = note.read_text(encoding="utf-8", errors="replace")
        if note_references_image_embed(text, relative_image):
            names.append(note.name)
    return names


LINT_FAILURE_DETAIL_LIMIT = 20


def lint_issue_text(issue: object) -> str:
    if not isinstance(issue, dict):
        return str(issue)
    text = str(issue.get("reason") or issue.get("line") or issue.get("snippet") or issue)
    line_number = issue.get("line_number")
    return f"{text} (line {line_number})" if line_number else text


def lint_failure_message(lint: dict, gate: str, lint_path: str) -> str:
    detail_parts: list[str] = []
    reported: set[str] = set()
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
        for issue in lint.get(issue_key, []) or []:
            text = lint_issue_text(issue)
            part = f"{issue_key}: {text}"
            if part not in detail_parts:
                detail_parts.append(part)
            reported.add(text)
            if isinstance(issue, dict) and issue.get("reason"):
                reported.add(str(issue["reason"]))
    # Lint also copies some issue reasons into warnings; list only the rest.
    for warning in lint.get("warnings", []) or []:
        if warning and str(warning) not in reported and str(warning) not in detail_parts:
            detail_parts.append(str(warning))
    shown = detail_parts[:LINT_FAILURE_DETAIL_LIMIT]
    details = "; ".join(shown)
    if len(detail_parts) > len(shown):
        details += f"; and {len(detail_parts) - len(shown)} more"
    suffix = f" Details: {details}." if details else ""
    return f"write_obsidian_note.py refused to write note because {gate} gate failed.{suffix} See lint JSON: {lint_path}"


def require_lint_gate(lint: dict, key: str, gate: str, lint_path: str) -> None:
    if lint.get(key) is not True:
        raise SystemExit(lint_failure_message(lint, gate, lint_path))


def require_lint_report(path_value: str, producer: str, name: str, language: str) -> dict:
    if not path_value:
        raise SystemExit(f"Formal Save requires {name} with output_language.")
    try:
        report = json.loads(Path(path_value).expanduser().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Expected {name} JSON object: {path_value}") from exc
    if not isinstance(report, dict):
        raise SystemExit(f"Expected {name} JSON object: {path_value}")
    if report.get("script") != producer or report.get("status") != "ok":
        raise SystemExit(f"{name} requires a successful {producer} producer artifact.")
    try:
        require_artifact_output_language(report, name, language)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return report


def require_source_manifest(path_value: str) -> dict:
    if not path_value:
        raise SystemExit(
            "Formal Save or Obsidian Save Target Admission requires a Source Manifest with source_sha256."
        )
    try:
        manifest = maybe_load_json_record(path_value)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Expected successful Source Manifest JSON: {path_value}") from exc
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


def block_directory_conflict(
    args: argparse.Namespace,
    *,
    conflict_code: str,
    target_directories: list[Path],
    source_sha256: str,
    output_language: str,
) -> None:
    if args.output and any(
        Path(args.output).expanduser().resolve().is_relative_to(directory.resolve())
        for directory in target_directories
    ):
        raise SystemExit("JSON status output must stay outside conflicting paper directories.")
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
            "user_notes": existing_user_notes(target_path, output_language),
            "existing_read_date": existing_read_date(target_path),
            "source_sha256": source_sha256,
            "output_language": output_language,
        },
        args.output,
    )
    raise SystemExit(2)


def existing_read_date(target_path: Path) -> str:
    """The first-read date recorded in a note that would be replaced, or an empty string."""
    try:
        fields = parse_frontmatter(target_path.read_bytes().decode("utf-8", errors="replace"))
    except FrontmatterError:
        return ""
    value = (fields or {}).get("read_date", "")
    return value if isinstance(value, str) else ""


def existing_user_notes(target_path: Path, output_language: str) -> dict:
    """Summarize the user's My Notes in a note that would be replaced."""
    text = target_path.read_bytes().decode("utf-8", errors="replace")
    return inspect_existing_user_notes(text, output_language)


def recorded_saved_note_sha256(registry: dict | None, source_sha256: str, output_language: str) -> str:
    source = ((registry or {}).get("sources") or {}).get(source_sha256) or {}
    note = (source.get("notes") or {}).get(output_language) or {}
    return str(note.get("note_sha256", ""))


def choose_domain(args, config: dict, *, source_sha256: str, output_language: str) -> str:
    try:
        domain, args.new_domain = resolve_domain_choice(
            config, args.domain, args.new_domain_reason
        )
    except DomainChoiceError as exc:
        emit(
            {
                "status": "blocked",
                "script": "write_obsidian_note.py",
                "phase": "save_target_admission",
                "conflict_code": exc.code,
                "requires_user_confirmation": False,
                "message": exc.message,
                "domain_overview": domain_overview(config),
                "source_sha256": source_sha256,
                "output_language": output_language,
            },
            args.output,
        )
        raise SystemExit(2) from exc
    return domain


def resolve_obsidian_save_target(
    args: argparse.Namespace,
    config: dict,
    vault: Path,
    *,
    title: str,
    source_sha256: str,
    output_language: str,
) -> tuple[Path, str, str, bool, str]:
    archive_input = getattr(args, "archive_input", {"title": title})
    details = getattr(args, "source_details", {})
    identity_path = resolve_obsidian_note_path(config, title=title, filename=args.filename)
    resolved_subdir = ""
    try:
        candidates = directory_candidates(
            vault, archive_input, source_sha256, identity_path.parent.name
        )
        existing_dir = select_directory(candidates, getattr(args, "target_directory", ""))
        if existing_dir:
            registry = admit_directory(existing_dir, archive_input, source_sha256)
            if getattr(args, 'pdf_identity', None):
                record_work_evidence(registry['work'], source_sha256, args.pdf_identity)
            source = register_source(registry, source_sha256, details)
            notes = source["notes"]
            if output_language in notes:
                target_path = safe_path(existing_dir, notes[output_language]["filename"])
                if not target_path.is_file():
                    raise ArchiveError("recorded_language_note_missing", [existing_dir])
            else:
                target_path = safe_path(existing_dir, f"{source['note_stem']}.{output_language}.md")
            admission = (
                "reuse_source_directory"
                if read_record(existing_dir)
                else (
                    "reuse_pdf_directory"
                    if any(existing_dir.iterdir())
                    else "reuse_empty_same_name_directory"
                )
            )
            domain_routing_skipped = True
        else:
            resolved_subdir = choose_domain(
                args, config, source_sha256=source_sha256, output_language=output_language
            )
            target_path = resolve_obsidian_note_path(
                config, title=title, subdir=resolved_subdir, filename=args.filename
            )
            registry = new_record(title, target_path.stem, archive_input)
            source = register_source(registry, source_sha256, details)
            target_path = language_note_path(target_path, output_language)
            admission = "new_directory"
            domain_routing_skipped = False
        args.archive_registry = registry
        args.admitted_asset_subdir = source["asset_subdir"]
        if target_path.is_symlink() or not target_path.resolve().is_relative_to(vault.resolve()):
            raise ArchiveError("unsafe_archive_path", [target_path])
    except ArchiveError as exc:
        block_directory_conflict(
            args,
            conflict_code=exc.code,
            target_directories=[Path(p) for p in exc.paths] or [identity_path.parent],
            source_sha256=source_sha256,
            output_language=output_language,
        )

    require_safe_status_output(args, target_path)
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
    generated_note_sha256: str = "",
    registry: dict | None = None,
) -> Path:
    sidecar_path = target_path.parent / PAPER_DIRECTORY_SIDECAR
    payload = (
        registry
        or read_record(target_path.parent)
        or new_record(
            title,
            target_path.name.removesuffix(f".{output_language}{target_path.suffix}"),
            {"title": title, "paper_id": paper_id},
        )
    )
    source = register_source(payload, source_sha256, {})
    source["notes"][output_language] = {
        "filename": target_path.name,
        "note_sha256": note_sha256,
        "generated_note_sha256": generated_note_sha256 or note_sha256,
    }
    write_record(target_path.parent, payload)
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


def require_safe_status_output(args, target_path: Path | None = None) -> None:
    if not args.output:
        return
    protected = {
        Path(value).expanduser().resolve()
        for value in (
            args.content_file, args.plan_file, args.final_quality_review,
            args.final_readability_review, args.lint_json, args.grounding_lint_json,
            args.source_manifest, args.figure_decisions,
        )
        if value
    }
    if args.final_quality_review:
        protected.add(
            Path(args.final_quality_review).expanduser().resolve().with_suffix(".state.json")
        )
    output_path = Path(args.output).expanduser().resolve()
    if output_path in protected or (
        target_path is not None and output_path.is_relative_to(target_path.parent.resolve())
    ):
        raise SystemExit(
            "JSON status output must stay outside the paper directory and protected review inputs."
        )


def read_quality_inputs(
    args, language: str, *, lint_note_sha256: str | None = None,
) -> tuple[str, str, dict, str, Path]:
    for value, name in (
        (args.content_file, "--content-file"), (args.plan_file, "--plan-file"),
        (args.final_quality_review, "--final-quality-review"),
    ):
        if not value:
            raise ValueError(f"Final Quality Gate requires explicit {name}.")
    raw_note = Path(args.content_file).expanduser().read_bytes()
    note_text = canonical_note_text(raw_note)
    note_sha256 = hashlib.sha256(raw_note).hexdigest()
    if lint_note_sha256 is not None and lint_note_sha256 != note_sha256:
        raise ValueError(
            "write_obsidian_note.py refused to write note because the final note "
            "changed after Final Note Lint; rerun lint under the same output_language."
        )
    raw_plan = Path(args.plan_file).expanduser().read_bytes()
    plan = json.loads(raw_plan.decode("utf-8-sig"))
    review_path = Path(args.final_quality_review).expanduser().resolve()
    review = strict_json_loads(review_path.read_text(encoding="utf-8-sig"))
    review_id = validate_quality(
        review, note_sha256=note_sha256, plan_sha256=hashlib.sha256(raw_plan).hexdigest(),
        plan=plan, language=language,
    )
    return note_text, note_sha256, review, review_id, review_path.with_suffix(".state.json")


def load_quality_state(path: Path) -> dict | None:
    return strict_json_loads(path.read_text(encoding="utf-8-sig")) if path.exists() else None


def record_final_quality_review(args) -> None:
    if not args.language:
        raise SystemExit("Recording Final Quality Review requires explicit --language.")
    try:
        language = normalize_output_language(args.language)
        _, _, review, review_id, state_path = read_quality_inputs(args, language)
        require_safe_status_output(args)
        previous = load_quality_state(state_path)
        state = advance_state(previous, review, review_id, language=language)
        if state != previous:
            atomic_write_note(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    revision_allowed = bool(state["pending_note_sha256"]) and state["revisions_used"] < 2
    emit({
        "status": "ok" if review["verdict"] == "pass" else "revision_required",
        "script": "write_obsidian_note.py", "phase": "final_quality_review",
        "output_language": language, "verdict": review["verdict"],
        "revisions_used": state["revisions_used"],
        "revisions_remaining": 2 - state["revisions_used"],
        "revision_allowed": revision_allowed, "review_state_path": str(state_path),
    }, args.output)
    if review["verdict"] == "fail":
        raise SystemExit(1)


def main() -> None:
    args = parser().parse_args()
    if args.record_final_quality_review:
        if args.preflight:
            raise SystemExit("--preflight and --record-final-quality-review cannot be combined.")
        record_final_quality_review(args)
        return
    require_safe_status_output(args)
    config = runtime_config(
        cli_overrides={
            "output_language": args.language,
            "save_mode": args.save_mode or ("obsidian" if args.vault else ""),
            "obsidian_vault": args.vault,
            "papers_dir": args.papers_dir,
        }
    )
    output_language = normalize_output_language(
        args.language or str(config.get("output_language", "")) or None
    )
    output_mode, root_path = resolve_note_output_mode(config)

    record = maybe_load_json_record(args.input) or {}
    title = (
        args.title
        or str(
            (record.get("work_level_identity", {}) or {}).get("title")
            or record.get("title", "")
        ).strip()
    )
    if not title:
        raise SystemExit("write_obsidian_note.py requires --title or metadata with a title.")

    source_manifest = require_source_manifest(args.source_manifest)
    args.archive_input = {**record, **source_manifest, "title": title}
    if not args.target_directory:
        args.target_directory = (source_manifest.get("archive_source") or {}).get(
            "target_directory", ""
        )
    pdf_value = (source_manifest.get("pdf") or {}).get("path") or source_manifest.get(
        "pdf_path", ""
    )
    pdf_path = Path(pdf_value).expanduser() if pdf_value else None
    if pdf_path and (
        not pdf_path.is_file() or file_sha256(pdf_path) != source_manifest["source_sha256"]
    ):
        raise SystemExit("Source Manifest PDF does not match source_sha256.")
    if pdf_path:
        expected_work = work_identity(args.archive_input)
        try:
            observed = (
                verify_pdf(pdf_path, args.archive_input)
                if expected_work["identifiers"]
                else pdf_identity(pdf_path)
            )
            args.pdf_identity = observed
            record_work_evidence(expected_work, source_manifest['source_sha256'], observed)
            args.archive_input["work"] = expected_work
        except ArchiveError as exc:
            raise SystemExit(str(exc)) from exc
    args.source_details = source_details(args.archive_input, pdf_path)
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
            source_sha256=str(source_manifest["source_sha256"]),
            output_language=output_language,
        )
    else:
        resolved_subdir = choose_domain(
            args,
            config,
            source_sha256=str(source_manifest["source_sha256"]),
            output_language=output_language,
        )
        target_path = resolve_obsidian_note_path(
            config,
            title=title,
            subdir=resolved_subdir,
            filename=args.filename,
        )
        require_safe_status_output(args, target_path)
        args.admitted_asset_subdir = args.asset_subdir

    domain = resolved_subdir or saved_domain(config, target_path)
    new_domain = {"new_domain": getattr(args, "new_domain", False)}
    if new_domain["new_domain"]:
        new_domain["new_domain_reason"] = args.new_domain_reason.strip()
    if args.preflight:
        emit(
            {
                "status": "ok",
                "script": "write_obsidian_note.py",
                "phase": "save_target_admission",
                "admission": admission,
                "domain_routing_skipped": domain_routing_skipped,
                "domain": domain,
                **new_domain,
                "target_directory": str(target_path.parent),
                "note_path": str(target_path),
                "asset_subdir": args.admitted_asset_subdir,
                "source_sha256": str(source_manifest["source_sha256"]),
                "output_language": output_language,
                **(
                    {
                        "user_notes": existing_user_notes(target_path, output_language),
                        "existing_read_date": existing_read_date(target_path),
                    }
                    if target_path.is_file()
                    else {}
                ),
            },
            args.output,
        )
        return

    lint = require_lint_report(args.lint_json, "lint_note.py", "Final Note Lint", output_language)
    lint_path = str(Path(args.lint_json).expanduser().resolve())
    for key, gate in (
        ("passes_basic_structure", "basic structure"),
        ("passes_style_gate", "style"),
        ("passes_math_gate", "math"),
        ("passes_figure_gate", "figure"),
        ("passes_plan_gate", "plan"),
        ("passes_substantive_content", "substantive content"),
        ("passes_reference_hygiene_gate", "reference hygiene"),
    ):
        require_lint_gate(lint, key, gate, lint_path)
    grounding = require_lint_report(
        args.grounding_lint_json, "lint_grounding.py", "Grounding Lint", output_language,
    )
    require_lint_gate(grounding, "passes_grounding", "grounding", args.grounding_lint_json)
    if not args.plan_file or not Path(args.plan_file).expanduser().is_file():
        raise SystemExit("Formal Save requires an existing Note Plan JSON file via --plan-file.")
    try:
        note_plan = maybe_load_json_record(args.plan_file)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Expected Note Plan JSON object: {args.plan_file}") from exc
    if note_plan is None:
        raise SystemExit(f"Expected Note Plan JSON object: {args.plan_file}")
    try:
        require_artifact_output_language(note_plan, "Note Plan", output_language)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not args.figure_decisions:
        raise SystemExit("Formal Save requires Figure/Table Decisions with output_language.")
    try:
        figure_decisions = maybe_load_json_record(args.figure_decisions)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Expected JSON object for --figure-decisions: {args.figure_decisions}") from exc
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

    for report, field, value, name in (
        (lint, "note_plan_sha256", args.plan_file, "Final Note Lint Note Plan"),
        (grounding, "note_plan_sha256", args.plan_file, "Grounding Lint Note Plan"),
        (grounding, "source_manifest_sha256", args.source_manifest, "Grounding Lint Source Manifest"),
        (grounding, "figure_decisions_sha256", args.figure_decisions, "Grounding Lint Figure/Table Decisions"),
    ):
        current_sha256 = json_input_sha256(value)
        if not current_sha256 or report.get(field) != current_sha256:
            raise SystemExit(f"{name} SHA-256 does not match current input; rerun lint.")
    figure_issues = [
        item
        for item in validate_figure_decisions(source_manifest, figure_decisions, args.source_manifest)
        if item.get("severity", "error") == "error"
    ]
    if figure_issues:
        raise SystemExit(f"Figure/Table Decisions validation failed: {json.dumps(figure_issues)}")

    lint_note_sha256 = str(lint.get("note_sha256", "")).strip()
    if not lint_note_sha256:
        raise SystemExit("lint artifact requires note_sha256.")
    try:
        (
            note_text, note_sha256, quality_review, quality_id, quality_state_path,
        ) = read_quality_inputs(args, output_language, lint_note_sha256=lint_note_sha256)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    require_reference_hygiene(note_text, "before save")
    tag_issue = domain_tag_issue(note_text, domain)
    if tag_issue:
        raise SystemExit(tag_issue)
    try:
        state = load_quality_state(quality_state_path)
        require_recorded_pass(state, quality_review, quality_id, language=output_language)
        if not args.final_readability_review:
            raise ValueError("Formal Save requires --final-readability-review.")
        readability = strict_json_loads(
            Path(args.final_readability_review).expanduser().read_text(encoding="utf-8-sig")
        )
        validate_readability(readability, note_sha256=note_sha256, language=output_language)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    require_resolvable_links(note_text, output_language, output_mode, root_path, config)

    with archive_lock(root_path) if output_mode == "obsidian" else nullcontext():
        if pdf_path and file_sha256(pdf_path) != source_manifest["source_sha256"]:
            raise SystemExit("Source Manifest PDF changed before save.")
        overwrote_existing_note = bool(approved_existing_note_sha256)
        if output_mode == "obsidian":
            rechecked_target, _, _, _, rechecked_existing_sha256 = resolve_obsidian_save_target(
                args,
                config,
                root_path,
                title=title,
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

        asset_subdir = args.admitted_asset_subdir if output_mode == 'obsidian' else args.asset_subdir
        asset_dir = resolve_note_asset_dir(target_path, asset_subdir)
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
        replaced_images: list[dict] = []
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
                    replaced_images,
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
            existing_text = None
            if target_path.is_file():
                try:
                    existing_text = target_path.read_bytes().decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SystemExit(
                        "The existing note is not UTF-8, so its My Notes section cannot be kept."
                    ) from exc
            try:
                saved_text, user_notes = merge_user_notes(
                    note_text,
                    existing_text,
                    output_language,
                    recorded_saved_sha256=recorded_saved_note_sha256(
                        getattr(args, "archive_registry", None),
                        str(source_manifest["source_sha256"]),
                        output_language,
                    ) if output_mode == "obsidian" else "",
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            saved_note_sha256 = hashlib.sha256(saved_text.encode("utf-8")).hexdigest()
            note_attempted = True
            atomic_write_note(target_path, saved_text)
            written_text = target_path.read_text(encoding="utf-8")
            if (
                file_sha256(target_path) != saved_note_sha256
                or hashlib.sha256(
                    restore_generated_text(written_text, note_text, output_language).encode("utf-8")
                ).hexdigest() != note_sha256
            ):
                raise SystemExit("Saved note SHA-256 does not match the reviewed final draft.")
            require_reference_hygiene(
                restore_generated_text(written_text, note_text, output_language),
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
                    note_sha256=saved_note_sha256,
                    generated_note_sha256=note_sha256,
                    registry=args.archive_registry,
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
            for replaced in reversed(replaced_images):
                restore_file(replaced["path"], replaced["backup"])
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
            for replaced in replaced_images:
                if replaced["backup"] is not None:
                    replaced["backup"].unlink(missing_ok=True)

        payload = {
            "status": "ok",
            "script": "write_obsidian_note.py",
            "output_language": output_language,
            "paper_id": paper_id,
            "title": title,
            "note_path": str(target_path),
            "subdir": resolved_subdir,
            "domain": domain,
            **new_domain,
            "images_dir": str(asset_dir),
            "materialized_figures": materialized_figures,
            "replaced_images": [
                {"file": item["relative_path"], "also_embedded_by": item["also_embedded_by"]}
                for item in replaced_images
            ],
            "overwrote_existing_note": overwrote_existing_note,
            "admission": admission,
            "domain_routing_skipped": domain_routing_skipped,
            "final_quality_review": "pass",
            "final_readability_review": "pass",
            "reviewed_note_sha256": note_sha256,
            "saved_note_sha256": saved_note_sha256,
            "user_notes": {
                "status": user_notes["status"],
                "chars": user_notes["chars"],
                "sha256": user_notes["user_notes_sha256"],
                "legacy_format": user_notes["legacy_format"],
            },
        }
        if sidecar_path is not None:
            payload["sidecar_path"] = str(sidecar_path)
            payload["source_sha256"] = str(source_manifest["source_sha256"])
        payload["output_mode"] = output_mode
        payload["base_output_root"] = str(root_path)
        payload["glossary_followup"] = glossary_followup(
            config,
            source_manifest=(
                str(Path(args.source_manifest).expanduser().resolve())
                if Path(args.source_manifest).expanduser().is_file()
                else ""
            ),
            note_path=str(target_path),
            regenerated=overwrote_existing_note,
        )
        if config.get("obsidian_vault"):
            payload["vault"] = str(Path(config["obsidian_vault"]).expanduser().resolve())
        emit(payload, args.output)


if __name__ == "__main__":
    main()
