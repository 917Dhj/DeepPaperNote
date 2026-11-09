"""Resolve where a note is saved: the save target, the domain folders, and the note path."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Any

from common import slugify_filename


def configured_obsidian_vault(config: dict[str, Any]) -> Path | None:
    if str(config.get("save_mode", "")).strip() == "workspace":
        return None
    vault = str(config.get("obsidian_vault", "")).strip()
    if not vault:
        return None
    vault_path = Path(vault).expanduser().resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RuntimeError(f"Configured Obsidian vault does not exist: {vault_path}")
    return vault_path


def require_obsidian_vault(config: dict[str, Any]) -> Path:
    vault_path = configured_obsidian_vault(config)
    if vault_path is None:
        raise RuntimeError("Missing Obsidian Vault in User Configuration or the current Run Override.")
    return vault_path


def resolve_note_output_mode(config: dict[str, Any]) -> tuple[str, Path]:
    save_mode = str(config.get("save_mode", "")).strip()
    if save_mode == "obsidian":
        return ("obsidian", require_obsidian_vault(config))
    if not save_mode:
        vault_path = configured_obsidian_vault(config)
        if vault_path is not None:
            return ("obsidian", vault_path)
    workspace_root = Path.cwd().resolve()
    output_dir = str(config.get("workspace_output_dir", "DeepPaperNote_output")).strip() or "DeepPaperNote_output"
    output_path = workspace_root / Path(
        *safe_relative_path_parts(output_dir, "workspace_output_dir")
    )
    return ("workspace", require_path_within(workspace_root, output_path, "workspace_output_dir"))


def safe_relative_path_parts(value: str | Path, field: str) -> tuple[str, ...]:
    raw = str(value).strip()
    if not raw:
        return ()
    windows_path = PureWindowsPath(raw)
    if (
        Path(raw).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise RuntimeError(
            f"Unsafe {field}: expected a relative path inside the Save Target: {raw}"
        )
    parts = tuple(part for part in re.split(r"[\\/]+", raw) if part and part != ".")
    if ".." in parts:
        raise RuntimeError(
            f"Unsafe {field}: expected a relative path inside the Save Target: {raw}"
        )
    return parts


def require_path_within(root: str | Path, path: str | Path, field: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise RuntimeError(f"Unsafe {field}: path escapes the Save Target: {path}") from exc
    return Path(path)


def resolve_note_asset_dir(note_path: str | Path, asset_subdir: str) -> Path:
    asset_subdir_parts = safe_relative_path_parts(asset_subdir, "asset_subdir")
    if not asset_subdir_parts:
        raise RuntimeError(
            "Unsafe asset_subdir: expected a relative directory inside the Save Target"
        )
    note_dir = Path(note_path).parent
    return require_path_within(
        note_dir,
        note_dir / Path(*asset_subdir_parts),
        "asset_subdir",
    )


def is_probable_paper_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(
        (path / marker).exists()
        for marker in (
            f"{path.name}.md",
            f"{path.name}.zh-CN.md",
            f"{path.name}.en.md",
            ".deeppapernote.json",
        )
    )


def existing_domain_dirs(config: dict[str, Any]) -> list[str]:
    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    base_dir = root_path / Path(papers_dir) if output_mode == "obsidian" else root_path
    if not base_dir.exists() or not base_dir.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if is_probable_paper_folder(child):
            continue
        names.append(child.name)
    return names


def resolve_obsidian_note_path(
    config: dict[str, Any],
    *,
    title: str,
    subdir: str = "",
    filename: str = "",
) -> Path:
    def path_from_parts(parts: tuple[str, ...]) -> Path:
        return Path(*parts) if parts else Path()

    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    papers_dir_parts = safe_relative_path_parts(papers_dir, "papers_dir")
    relative_dir = path_from_parts(papers_dir_parts) if output_mode == "obsidian" else Path()
    if subdir:
        relative_dir = relative_dir / path_from_parts(safe_relative_path_parts(subdir, "subdir"))
    note_slug = slugify_filename(title)
    target_name = filename.strip() or f"{note_slug}.md"
    target_name_parts = safe_relative_path_parts(target_name, "filename")
    target_name_path = path_from_parts(target_name_parts)
    folder_name = target_name_path.stem or note_slug
    target_path = root_path / relative_dir / folder_name / target_name_path
    save_target = (
        root_path / path_from_parts(papers_dir_parts)
        if output_mode == "obsidian"
        else root_path
    )
    require_path_within(root_path, save_target, "papers_dir")
    return require_path_within(save_target, target_path, "note path")
