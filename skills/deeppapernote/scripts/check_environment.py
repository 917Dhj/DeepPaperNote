#!/usr/bin/env python3
"""Inspect the local DeepPaperNote environment for maintenance and troubleshooting."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path

from _zotero_local import probe_zotero_local_api
from common import emit, env_config_value, runtime_config
from user_configuration import inspect_configuration


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "check environment")
    p.add_argument("--output", default="", help="Optional JSON output path.")
    return p


def import_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def find_obsidian_candidates() -> list[str]:
    roots = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
    ]
    results: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob("*"):
                if not path.is_dir():
                    continue
                if path == root:
                    continue
                name = path.name.lower()
                if "obsidian" not in name and "vault" not in name:
                    continue
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                results.append(resolved)
                if len(results) >= 8:
                    return results
        except Exception:
            continue
    return results


def find_local_zotero_hints() -> list[str]:
    candidates = [
        Path.home() / "Zotero",
        Path.home() / "Library" / "Application Support" / "Zotero",
    ]
    hits: list[str] = []
    for path in candidates:
        if path.exists():
            hits.append(str(path.resolve()))
    return hits


def main() -> None:
    args = parser().parse_args()
    configuration = inspect_configuration()
    config = runtime_config() if configuration["state"] == "ready" else {}
    zotero_local_api = probe_zotero_local_api()

    obsidian_vault = str(config.get("obsidian_vault", "")).strip()
    obsidian_vault_exists = bool(obsidian_vault) and Path(obsidian_vault).expanduser().exists()

    tesseract_path = shutil.which("tesseract") or ""
    pdftoppm_path = shutil.which("pdftoppm") or ""

    payload = {
        "status": "ok",
        "script": "check_environment.py",
        "tool_role": "maintenance",
        "user_configuration": configuration,
        "python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
            "fitz_installed": import_available("fitz"),
            "pytesseract_installed": import_available("pytesseract"),
            "pillow_installed": import_available("PIL"),
        },
        "obsidian": {
            "configured": bool(obsidian_vault),
            "vault_path": obsidian_vault,
            "vault_exists": obsidian_vault_exists,
            "papers_dir": str(config.get("papers_dir", "")),
            "output_dir": str(config.get("output_dir", "")),
            "candidate_vaults": find_obsidian_candidates(),
        },
        "workspace_fallback": {
            "available": True,
            "current_working_directory": str(Path.cwd().resolve()),
            "workspace_output_dir": str(config.get("workspace_output_dir", "DeepPaperNote_output")),
            "note": (
                "With save_mode=workspace, DeepPaperNote saves under the current working directory."
            ),
        },
        "zotero": {
            "local_hints": find_local_zotero_hints(),
            "local_api": zotero_local_api,
            "local_api_available": bool(zotero_local_api.get("ready")),
            "local_api_status": str(zotero_local_api.get("status", "error")),
            "local_api_version": str(zotero_local_api.get("api_version", "")),
            "local_api_schema_version": str(zotero_local_api.get("schema_version", "")),
            "mcp_available_from_script": False,
            "session_integration_checked_by_script": False,
            "note": (
                "The built-in read-only Local API check is reported here. Session-scoped "
                "library integrations must still be checked by the active agent at runtime."
            ),
        },
        "ocr": {
            "tesseract_installed": bool(tesseract_path),
            "tesseract_path": tesseract_path,
            "pytesseract_installed": import_available("pytesseract"),
            "pillow_installed": import_available("PIL"),
            "pdftoppm_installed": bool(pdftoppm_path),
            "pdftoppm_path": pdftoppm_path,
        },
        "metadata": {
            "maintenance_utility": True,
            "semantic_scholar_api_key_configured": bool(
                env_config_value(
                    "DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"
                )
            ),
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
