#!/usr/bin/env python3
"""Resolve and validate device-local paper-glossary configuration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONFIG_DIRNAME = ".paper-glossary"
CONFIG_FILENAME = "config.json"


def default_config_path() -> Path:
    return Path.home() / CONFIG_DIRNAME / CONFIG_FILENAME


def find_vault_root(path: Path) -> Path | None:
    current = path.expanduser().resolve(strict=False)
    while not current.exists() and current != current.parent:
        current = current.parent
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate.resolve()
    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _validated_config_payload(
    payload: object,
    error: str,
    source_terms_dir: Path | None = None,
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise SystemExit(error)
    for field in ("vault_root", "terms_subdir"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(error)
    try:
        subdir = Path(payload["terms_subdir"])
        vault_path = Path(payload["vault_root"])
        if not vault_path.is_absolute():
            raise SystemExit(error)
        paths = (subdir,) if source_terms_dir is None else (subdir, source_terms_dir)
        if any(
            not part.strip()
            for path in paths
            for part in path.parts
            if part != path.anchor
        ):
            raise SystemExit(error)
        vault = vault_path.resolve(strict=False)
        terms_dir = (vault / subdir).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(error) from exc
    if subdir.anchor or terms_dir == vault:
        raise SystemExit(error)
    return {
        "vault_root": str(vault),
        "terms_subdir": payload["terms_subdir"],
    }


def configure_terms_dir(
    terms_dir: Path, config_path: Path | None = None
) -> dict[str, str]:
    resolved = terms_dir.expanduser().resolve(strict=False)
    vault = find_vault_root(resolved)
    if vault is None or not _is_within(resolved, vault):
        raise SystemExit(
            "Term directory must be inside an Obsidian vault containing .obsidian."
        )
    payload = _validated_config_payload(
        {
            "vault_root": str(vault),
            "terms_subdir": str(resolved.relative_to(vault)),
        },
        "Term directory must be a real child inside an Obsidian vault.",
        terms_dir.expanduser(),
    )
    resolved.mkdir(parents=True, exist_ok=True)
    target = (config_path or default_config_path()).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def load_config(config_path: Path | None = None) -> dict[str, str] | None:
    target = (config_path or default_config_path()).expanduser()
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid paper-glossary config: {target}") from exc
    return _validated_config_payload(
        payload, f"Invalid paper-glossary config object: {target}"
    )


def resolve_terms_dir(config: dict[str, str]) -> Path:
    vault = Path(config.get("vault_root", "")).expanduser().resolve(strict=False)
    terms_dir = (vault / config.get("terms_subdir", "")).resolve(strict=False)
    if (
        not (vault / ".obsidian").is_dir()
        or not terms_dir.is_dir()
        or not _is_within(terms_dir, vault)
        or find_vault_root(terms_dir) != vault
    ):
        raise SystemExit(
            "Configured Obsidian term directory is missing or invalid; configure it again."
        )
    return terms_dir


def validate_article(article: Path, config: dict[str, str]) -> dict[str, str]:
    resolved = article.expanduser().resolve()
    if resolved.suffix.lower() != ".md" or not resolved.is_file():
        raise SystemExit(f"Article Markdown not found: {resolved}")
    article_vault = find_vault_root(resolved)
    configured_vault = Path(config["vault_root"]).expanduser().resolve()
    if article_vault != configured_vault:
        raise SystemExit(
            "Article and term directory must be inside the same Obsidian vault."
        )
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return {"article_path": str(resolved), "article_sha256": digest}
