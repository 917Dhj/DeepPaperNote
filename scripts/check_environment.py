#!/usr/bin/env python3
"""Inspect the local DeepPaperNote environment and report setup readiness."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
from pathlib import Path

from common import emit, env_config_value, runtime_config


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
    config = runtime_config()

    obsidian_vault = str(config.get("obsidian_vault", "")).strip()
    obsidian_vault_exists = bool(obsidian_vault) and Path(obsidian_vault).expanduser().exists()

    tesseract_path = shutil.which("tesseract") or ""
    pdftoppm_path = shutil.which("pdftoppm") or ""

    payload = {
        "status": "ok",
        "script": "check_environment.py",
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
            "note": "If no Obsidian vault is configured, DeepPaperNote can still save notes under the current working directory.",
        },
        "zotero": {
            "local_hints": find_local_zotero_hints(),
            "mcp_available_from_script": False,
            "note": "Zotero MCP availability must be checked by Codex at runtime, not by this script.",
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
            "semantic_scholar_api_key_configured": bool(
                env_config_value("DEEPPAPERNOTE_SEMANTIC_SCHOLAR_API_KEY", "SEMANTIC_SCHOLAR_API_KEY")
            )
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
