#!/usr/bin/env python3
"""Shared helpers for DeepPaperNote scripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from user_configuration import (
    inspect_configuration,
    resolve_preferences,
    resolve_run_overrides,
)

SHELL_CONFIG_FILES = [
    Path.home() / ".zshenv",
    Path.home() / ".zprofile",
    Path.home() / ".zshrc",
    Path.home() / ".bash_profile",
    Path.home() / ".bashrc",
]

try:
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", help="Primary input path, JSON artifact, or identifier.")
    parser.add_argument("--output", help="Output path for JSON or Markdown.")
    parser.add_argument("--paper-id", help="Canonical paper id if already known.")
    return parser


def ensure_parent(path: str | Path) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def file_sha256(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        return ""
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_input_sha256(value: str | Path) -> str:
    text = str(value)
    if text.lstrip().startswith("{"):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return file_sha256(value)


def emit(payload: dict[str, Any], output_path: str | None = None) -> None:
    if output_path:
        ensure_parent(output_path)
        Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        # ASCII JSON reads back under any console encoding, such as cp1252 on Windows.
        print(json.dumps(payload, indent=2))


def load_json_file(path: str | Path) -> dict[str, Any]:
    # utf-8-sig transparently strips a UTF-8 BOM (e.g. files written by
    # PowerShell Out-File / Notepad on Windows) that would otherwise make
    # json.loads raise "Unexpected UTF-8 BOM". It is a no-op for BOM-less files.
    data = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("Expected a JSON object.")
    return data


def maybe_load_json_record(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    path = Path(stripped).expanduser()
    if path.exists() and path.is_file() and path.suffix.lower() == ".json":
        return load_json_file(path)
    return None


def require_ok_input_artifact(record: dict[str, Any], consumer: str) -> dict[str, Any]:
    status = normalize_whitespace(str(record.get("status", ""))).lower()
    if status and status != "ok":
        producer = normalize_whitespace(str(record.get("script", ""))) or "unknown producer"
        message = f"{consumer} refuses non-ok input artifact from {producer}: status={status}"
        raise SystemExit(message)
    return record


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def strip_tags(text: str) -> str:
    return normalize_whitespace(re.sub(r"<[^>]+>", " ", text or ""))


def normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", normalize_whitespace(text).lower()).strip()


def slugify_filename(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text or "paper_note"


def shell_config_value(name: str) -> str:
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}=(.*)$")
    for path in SHELL_CONFIG_FILES:
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except Exception:
            continue
        for raw_line in reversed(lines):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = pattern.match(line)
            if not match:
                continue
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value.strip()
    return ""


def env_config_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    disable_shell_fallback = os.environ.get("DEEPPAPERNOTE_DISABLE_SHELL_CONFIG", "").strip().lower()
    if disable_shell_fallback in {"1", "true", "yes", "on"}:
        return default
    for name in names:
        value = shell_config_value(name)
        if value:
            return value
    return default


def runtime_config(
    *,
    explicit_overrides: dict[str, Any] | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = resolve_run_overrides(
        explicit_overrides=explicit_overrides,
        cli_overrides=cli_overrides,
    )
    if resolved["issues"] or resolved["missing"]:
        inspection = inspect_configuration()
        if inspection["state"] != "ready":
            raise RuntimeError(json.dumps(inspection, ensure_ascii=False, sort_keys=True))
        resolved = resolve_preferences(
            explicit_overrides=explicit_overrides,
            cli_overrides=cli_overrides,
        )
        if resolved["issues"] or resolved["missing"]:
            raise RuntimeError(json.dumps(resolved, ensure_ascii=False, sort_keys=True))
    return {
        "obsidian_vault": "",
        "papers_dir": "",
        **resolved["values"],
        "output_dir": env_config_value("DEEPPAPERNOTE_OUTPUT_DIR", default="tmp/DeepPaperNote"),
        "workspace_output_dir": env_config_value(
            "DEEPPAPERNOTE_WORKSPACE_OUTPUT_DIR",
            default="DeepPaperNote_output",
        ),
    }


def default_pdf_path(record: dict[str, Any], dest_dir: str | None = None) -> Path:
    config = runtime_config()
    base_dir = Path(dest_dir or config["output_dir"]).expanduser().resolve() / "pdfs"
    base_dir.mkdir(parents=True, exist_ok=True)
    title = str(record.get("title") or record.get("paper_id") or "paper")
    return base_dir / f"{slugify_filename(title)}.pdf"


def default_assets_dir(record: dict[str, Any], dest_dir: str | None = None) -> Path:
    config = runtime_config()
    base_dir = Path(dest_dir or config["output_dir"]).expanduser().resolve() / "assets"
    title = str(record.get("title") or record.get("paper_id") or "paper")
    asset_dir = base_dir / slugify_filename(title)
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir


