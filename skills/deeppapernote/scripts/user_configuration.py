#!/usr/bin/env python3
"""Inspect and persist DeepPaperNote's device-local User Configuration."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

OUTPUT_LANGUAGES = {"zh-CN", "en"}
SAVE_MODES = {"workspace", "obsidian"}
KNOWN_FIELDS = ("output_language", "save_mode", "obsidian_vault", "papers_dir")
ALWAYS_REQUIRED = ("output_language", "save_mode")
ENV_FIELDS = {
    "output_language": "DEEPPAPERNOTE_OUTPUT_LANGUAGE",
    "save_mode": "DEEPPAPERNOTE_SAVE_MODE",
    "obsidian_vault": "DEEPPAPERNOTE_OBSIDIAN_VAULT",
    "papers_dir": "DEEPPAPERNOTE_PAPERS_DIR",
}


class ConfigurationWriteError(RuntimeError):
    """Raised when a Preference Change cannot be durably verified."""


class ConfigurationValidationError(ConfigurationWriteError):
    """Raised when a Preference Change still needs user input or repair."""

    def __init__(
        self,
        result: dict[str, Any],
        message: str = "Preference Change is incomplete or invalid.",
    ) -> None:
        super().__init__(message)
        self.result = result


def user_config_path() -> Path:
    override = os.environ.get("DEEPPAPERNOTE_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".deeppapernote" / "config.json"


def default_shell_paths() -> tuple[Path, ...]:
    home = Path.home()
    return tuple(
        home / name
        for name in (".zshenv", ".zprofile", ".zshrc", ".bash_profile", ".bashrc")
    )


def _clean_values(values: Mapping[str, Any] | None) -> dict[str, str]:
    if not values:
        return {}
    return {
        field: str(values[field]).strip()
        for field in KNOWN_FIELDS
        if field in values and str(values[field]).strip()
    }


def _migration_candidates(
    environ: Mapping[str, str], shell_paths: Sequence[Path]
) -> dict[str, dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for field, name in ENV_FIELDS.items():
        value = environ.get(name, "").strip()
        if value and _migration_value_supported(field, value):
            candidates[field] = {"value": value, "source": "process_environment"}
    for path in shell_paths:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for field, name in ENV_FIELDS.items():
            if field in candidates:
                continue
            pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}=(.*)$")
            for line in reversed(lines):
                match = pattern.match(line)
                if not match:
                    continue
                value = match.group(1).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]
                if value and _migration_value_supported(field, value):
                    candidates[field] = {"value": value, "source": str(path)}
                break
    return candidates


def _issue(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def _safe_relative_path(value: str) -> bool:
    native = Path(value)
    windows = PureWindowsPath(value)
    if native.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        return False
    parts = tuple(part for part in re.split(r"[\\/]+", value) if part and part != ".")
    return bool(parts) and ".." not in parts


def _migration_value_supported(field: str, value: str) -> bool:
    if field == "output_language":
        return value in OUTPUT_LANGUAGES
    if field == "save_mode":
        return value in SAVE_MODES
    if field == "obsidian_vault":
        try:
            vault = Path(value).expanduser()
        except (OSError, RuntimeError):
            return False
        return vault.is_absolute() and vault.is_dir()
    if field == "papers_dir":
        return _safe_relative_path(value)
    return False


def _validate(configuration: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    missing: list[str] = []
    for field in ALWAYS_REQUIRED:
        if not str(configuration.get(field, "")).strip():
            missing.append(field)
    language = str(configuration.get("output_language", "")).strip()
    save_mode = str(configuration.get("save_mode", "")).strip()
    if language and language not in OUTPUT_LANGUAGES:
        issues.append(_issue("output_language", "invalid_enum", "Expected zh-CN or en."))
    if save_mode and save_mode not in SAVE_MODES:
        issues.append(_issue("save_mode", "invalid_enum", "Expected workspace or obsidian."))
    if save_mode == "obsidian":
        vault = str(configuration.get("obsidian_vault", "")).strip()
        papers_dir = str(configuration.get("papers_dir", "")).strip()
        if not vault:
            missing.append("obsidian_vault")
        else:
            vault_path = Path(vault).expanduser()
            if not vault_path.is_absolute() or not vault_path.is_dir():
                issues.append(
                    _issue(
                        "obsidian_vault",
                        "missing_vault",
                        "Expected an existing absolute directory.",
                    )
                )
        if not papers_dir:
            missing.append("papers_dir")
        elif not _safe_relative_path(papers_dir):
            issues.append(
                _issue(
                    "papers_dir",
                    "unsafe_path",
                    "Expected a safe relative path inside the Vault.",
                )
            )
    return issues, missing


def _blocked_result(path: Path, code: str, message: str) -> dict[str, Any]:
    return {
        "state": "blocked",
        "config_path": str(path),
        "affected_fields": ["configuration"],
        "prompt_fields": [],
        "migration_candidates": {},
        "warnings": [],
        "issues": [_issue("configuration", code, message)],
    }


def _repair_result(
    path: Path,
    configuration: Mapping[str, Any],
    issues: list[dict[str, str]],
    missing: list[str],
) -> dict[str, Any]:
    affected = [issue["field"] for issue in issues]
    for field in missing:
        if field not in affected:
            affected.append(field)
    result: dict[str, Any] = {
        "state": "invalid" if issues else "needs_input" if missing else "ready",
        "config_path": str(path),
        "affected_fields": affected,
        "prompt_fields": [field for field in KNOWN_FIELDS if field in affected],
        "migration_candidates": {},
        "warnings": [],
        "configuration": dict(configuration),
    }
    if issues:
        result["issues"] = issues
    return result


def _read_configuration(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, f"unreadable:{exc}"
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        return None, f"malformed:{exc}"
    if not isinstance(value, dict):
        return None, "non_object:Expected a JSON object."
    return value, ""


def _path_is_writable(path: Path) -> bool:
    candidate = path.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return os.access(candidate, os.W_OK)


def inspect_configuration(
    *,
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    shell_paths: Sequence[Path] | None = None,
) -> dict[str, Any]:
    path = Path(config_path or user_config_path()).expanduser()
    environment = os.environ if environ is None else environ
    if not _path_is_writable(path):
        return _blocked_result(path, "unwritable", "User Configuration is not writable.")
    if not path.exists():
        return {
            "state": "needs_input",
            "config_path": str(path),
            "affected_fields": list(ALWAYS_REQUIRED),
            "prompt_fields": list(ALWAYS_REQUIRED),
            "migration_candidates": _migration_candidates(
                environment, default_shell_paths() if shell_paths is None else shell_paths
            ),
            "warnings": [],
        }

    configuration, read_error = _read_configuration(path)
    if read_error.startswith("unreadable:"):
        return _blocked_result(path, "unreadable", read_error.partition(":")[2])
    if read_error:
        code, _, message = read_error.partition(":")
        return {
            "state": "invalid",
            "config_path": str(path),
            "affected_fields": ["configuration"],
            "prompt_fields": list(ALWAYS_REQUIRED),
            "migration_candidates": {},
            "warnings": [],
            "issues": [_issue("configuration", code, message)],
        }

    assert configuration is not None
    issues, missing = _validate(configuration)
    return _repair_result(path, configuration, issues, missing)


def resolve_preferences(
    *,
    config_path: str | Path | None = None,
    explicit_overrides: Mapping[str, Any] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    path = Path(config_path or user_config_path()).expanduser()
    configuration, read_error = _read_configuration(path)
    if read_error or configuration is None:
        raise RuntimeError(f"User Configuration is not readable and valid: {read_error}")
    environment = os.environ if environ is None else environ
    layers = (
        ("user_configuration", _clean_values(configuration)),
        (
            "process_environment",
            {
                field: environment.get(name, "").strip()
                for field, name in ENV_FIELDS.items()
                if environment.get(name, "").strip()
            },
        ),
        ("cli", _clean_values(cli_overrides)),
        ("explicit_request", _clean_values(explicit_overrides)),
    )
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for source, layer in layers:
        for field, value in layer.items():
            values[field] = value
            sources[field] = source
    issues, missing = _validate(values)
    return {"values": values, "sources": sources, "issues": issues, "missing": missing}


def _invalid_backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = path.with_name(f"{path.stem}.invalid-{stamp}{path.suffix}")
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}.invalid-{stamp}-{counter}{path.suffix}")
        counter += 1
    return candidate


def _atomic_write(path: Path, configuration: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(configuration, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except OSError as exc:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except OSError:
                pass
        raise ConfigurationWriteError(f"User Configuration write is blocked: {exc}") from exc


def persist_preferences(
    preferences: Mapping[str, Any],
    *,
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    replace_invalid: bool = False,
) -> dict[str, Any]:
    path = Path(config_path or user_config_path()).expanduser()
    if not _path_is_writable(path):
        raise ConfigurationWriteError("User Configuration is not writable.")
    existing: dict[str, Any] = {}
    if path.exists():
        loaded, read_error = _read_configuration(path)
        if read_error.startswith("unreadable:"):
            raise ConfigurationWriteError(f"User Configuration is unreadable: {read_error}")
        if read_error:
            if not replace_invalid:
                raise ConfigurationValidationError(
                    inspect_configuration(config_path=path, environ=environ),
                    "Invalid User Configuration requires an explicitly confirmed replacement.",
                )
            backup = _invalid_backup_path(path)
            try:
                shutil.copy2(path, backup)
            except OSError as exc:
                raise ConfigurationWriteError(
                    f"Could not preserve invalid User Configuration: {exc}"
                ) from exc
        else:
            assert loaded is not None
            existing = loaded
    updates = _clean_values(preferences)
    candidate = {**existing, **updates}
    issues, missing = _validate(candidate)
    if issues or missing:
        raise ConfigurationValidationError(_repair_result(path, candidate, issues, missing))
    unknown = sorted(set(existing) - set(KNOWN_FIELDS))
    _atomic_write(path, candidate)
    reread, read_error = _read_configuration(path)
    if read_error or reread != candidate:
        raise ConfigurationWriteError(
            "User Configuration readback did not match the persisted values."
        )
    result = inspect_configuration(config_path=path, environ=environ)
    if result["state"] != "ready":
        raise ConfigurationWriteError("Persisted User Configuration did not pass validation.")
    if unknown:
        result["warnings"] = [
            f"Preserved unknown configuration fields: {', '.join(unknown)}"
        ]
    return result


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--set-output-language", choices=sorted(OUTPUT_LANGUAGES))
    argument_parser.add_argument("--set-save-mode", choices=sorted(SAVE_MODES))
    argument_parser.add_argument("--set-vault")
    argument_parser.add_argument("--set-papers-dir")
    argument_parser.add_argument("--replace-invalid", action="store_true")
    return argument_parser


def main() -> None:
    args = parser().parse_args()
    preferences = {
        field: value
        for field, value in {
            "output_language": args.set_output_language,
            "save_mode": args.set_save_mode,
            "obsidian_vault": args.set_vault,
            "papers_dir": args.set_papers_dir,
        }.items()
        if value is not None
    }
    try:
        result = (
            persist_preferences(preferences, replace_invalid=args.replace_invalid)
            if preferences
            else inspect_configuration()
        )
    except ConfigurationValidationError as exc:
        result = exc.result
    except ConfigurationWriteError as exc:
        result = _blocked_result(user_config_path(), "write_failed", str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["state"] != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
