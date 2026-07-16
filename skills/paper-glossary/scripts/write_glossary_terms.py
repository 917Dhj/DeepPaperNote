#!/usr/bin/env python3
"""Create or update central term-library Markdown notes."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_common import (
    elapsed_ms,
    emit,
    maybe_load_json_record,
    normalize_whitespace,
    validate_authorized_selection,
    validate_provenance_chain,
    writer_mappings_sha256,
)
from glossary_config import load_config, resolve_terms_dir, validate_article
from glossary_contracts import (
    GLOSSARY_CONFIDENCE_VALUES,
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_DISCLAIMER,
    GLOSSARY_OCCURRENCE_HEADING,
    GLOSSARY_TERM_TAG,
)
from glossary_library import (
    CONCEPT_FIELDS,
    _decode_frontmatter_scalar,
    _normalized_key,
    add_missing_concept_fields,
    build_alias_index as _library_build_alias_index,
    inspect_selected_terms,
    note_state,
    obsidian_safe_link_stem,
    read_frontmatter_aliases as _read_frontmatter_aliases,
    read_heading_name as _read_heading_name,
)

ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_FILENAME_COMPONENT_LENGTH = 240
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "write glossary terms")
    p.add_argument("--glossary", required=True, help="Glossary JSON path or JSON object.")
    p.add_argument("--inventory", required=True, help="Glossary inventory JSON path or JSON object.")
    p.add_argument("--config-path", default="", help="Optional device-local config path override.")
    p.add_argument("--source-manifest", required=True, help="Current source manifest.")
    p.add_argument("--raw-sections", default="", help="Optional current raw-sections JSONL.")
    p.add_argument(
        "--reviewed-shortlist", required=True, help="Saved reviewed-shortlist artifact."
    )
    p.add_argument("--triage", required=True, help="Saved authorized triage artifact.")
    p.add_argument("--article", default="", help="Optional explicit article Markdown path.")
    p.add_argument("--output", default="", help="Output JSON status path.")
    return p


def safe_term_filename(name: str) -> str:
    raw = obsidian_safe_link_stem(str(name))
    if not raw or raw in (".", "..") or raw.endswith((" ", ".")):
        raise SystemExit(f"Unsafe glossary filename: {raw!r}")
    cleaned = ILLEGAL_FILENAME_CHARS.sub(" ", raw)
    cleaned = normalize_whitespace(cleaned).strip(" .")
    if not cleaned or cleaned in (".", ".."):
        raise SystemExit(f"Unsafe glossary filename: {raw!r}")
    if cleaned.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise SystemExit(f"Unsafe glossary filename: reserved Windows name {raw!r}")
    component = f"{cleaned}.md"
    try:
        component_lengths = (
            len(component.encode("utf-16-le")) // 2,
            len(component.encode("utf-8")),
        )
    except UnicodeEncodeError:
        raise SystemExit(f"Unsafe glossary filename: invalid Unicode in {raw!r}") from None
    if any(length > MAX_FILENAME_COMPONENT_LENGTH for length in component_lengths):
        raise SystemExit(f"Unsafe glossary filename: component too long for {raw!r}")
    return cleaned


def _unique_term_path(terms_dir: Path, stem: str) -> Path:
    path = terms_dir / f"{stem}.md"
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = terms_dir / f"{stem}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def _frontmatter_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _alias_forms(entry: dict[str, Any]) -> list[str]:
    forms = [normalize_whitespace(str(entry.get("name", "")))]
    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list):
        raise SystemExit("Glossary entry aliases must be a list.")
    forms.extend(normalize_whitespace(str(alias)) for alias in aliases)
    seen: set[str] = set()
    ordered: list[str] = []
    for form in forms:
        key = _normalized_key(form)
        if form and key not in seen:
            seen.add(key)
            ordered.append(form)
    return ordered


def _concept_zone(entry: dict[str, Any]) -> list[str]:
    lines = [f"## {GLOSSARY_CONCEPT_HEADING}", f"- 定义：{entry.get('definition', '')}"]
    for label, key in (("详解", "elaboration"), ("直觉", "intuition"), ("与相邻概念的区别", "distinction")):
        value = normalize_whitespace(str(entry.get(key, "")))
        if value:
            lines.append(f"- {label}：{value}")
    lines.append(f"- 置信度：{entry.get('confidence', '')}")
    return lines


def occurrence_line(entry: dict[str, Any], paper_link: str) -> str:
    note = normalize_whitespace(str(entry.get("occurrence", "")))
    suffix = f"：{note}" if note else ""
    return f"- [[{paper_link}]]{suffix}"


def render_term_file(
    entry: dict[str, Any], paper_link: str, link_stem: str | None = None
) -> str:
    name = normalize_whitespace(str(entry.get("name", "")))
    actual_stem = name if link_stem is None else link_stem
    aliases = [
        alias for alias in _alias_forms(entry) if alias.casefold() != actual_stem.casefold()
    ]
    front = ["---", "aliases:"]
    front.extend(f"  - {_frontmatter_string(alias)}" for alias in aliases)
    front.extend([f"tags: [{GLOSSARY_TERM_TAG}]", "---", ""])
    body = [f"# {name}", "", GLOSSARY_DISCLAIMER, ""]
    body.extend(_concept_zone(entry))
    body.extend(["", f"## {GLOSSARY_OCCURRENCE_HEADING}", occurrence_line(entry, paper_link), ""])
    return "\n".join(front + body)


def upsert_term_file(
    entry: dict[str, Any], paper_link: str, terms_dir: Path, index: dict[str, Path]
) -> dict[str, Any]:
    existing = None
    for form in _alias_forms(entry):
        existing = index.get(form.lower())
        if existing is not None:
            break
    if existing is not None and existing.is_file():
        text = existing.read_text(encoding="utf-8-sig")
        updated = append_occurrence(text, entry, paper_link)
        if updated != text:
            existing.write_text(updated, encoding="utf-8")
        return {
            "name": entry.get("name", ""),
            "file": str(existing),
            "action": "updated" if updated != text else "unchanged",
            "link_stem": existing.stem,
        }

    name = normalize_whitespace(str(entry.get("name", "")))
    terms_dir.mkdir(parents=True, exist_ok=True)
    path = _unique_term_path(terms_dir, safe_term_filename(name))
    path.write_text(render_term_file(entry, paper_link, path.stem), encoding="utf-8")
    for form in _alias_forms(entry):
        index.setdefault(form.lower(), path)
    index.setdefault(path.stem.lower(), path)
    return {"name": name, "file": str(path), "action": "created", "link_stem": path.stem}


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _read_note_snapshot(path: Path) -> tuple[str, bool, bytes, tuple[int, int, int, int]]:
    try:
        identity_before = _file_identity(path)
        raw = path.read_bytes()
        identity_after = _file_identity(path)
        if identity_before != identity_after:
            raise SystemExit(f"Glossary note changed while planning: {path}")
        return (
            raw.decode("utf-8-sig"),
            raw.startswith(b"\xef\xbb\xbf"),
            raw,
            identity_after,
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"Unable to read glossary note {path}: {exc}") from None


def append_occurrence(text: str, entry: dict[str, Any], paper_link: str) -> str:
    line_ending = "\r\n" if "\r\n" in text else "\n"
    line = occurrence_line(entry, paper_link)
    heading = re.search(
        rf"(?m)^##\s+{re.escape(GLOSSARY_OCCURRENCE_HEADING)}\s*$(?:\r?\n)?", text
    )
    if heading is not None:
        following = re.search(r"(?m)^##\s+", text[heading.end() :])
        position = heading.end() + following.start() if following else len(text)
        section = text[heading.end() : position]
        occurrence = re.search(
            rf"(?m)^[ \t]*-[ \t]+\[\[{re.escape(paper_link)}\]\]", section
        )
        if occurrence is not None:
            return text
        prefix = "" if text[:position].endswith(("\n", "\r")) else line_ending
        suffix = "" if text[position:].startswith(("\n", "\r")) else line_ending
        return text[:position] + prefix + line + line_ending + suffix + text[position:]
    separator = "" if not text else (line_ending if text.endswith(("\n", "\r")) else line_ending * 2)
    if text and text.endswith(("\n", "\r")):
        separator = line_ending
    return text + separator + f"## {GLOSSARY_OCCURRENCE_HEADING}{line_ending}{line}{line_ending}"


# Existing consumers import this name from this module. The implementation lives
# in glossary_library so inventory and write paths use identical alias matching.
build_alias_index = _library_build_alias_index


def _entry_forms(entry: dict[str, Any], inventory_item: dict[str, Any]) -> list[str]:
    values: list[Any] = [entry.get("name", "")]
    values.extend(inventory_item.get("surface_forms", []))
    aliases = entry.get("aliases", [])
    if isinstance(aliases, list):
        values.extend(aliases)
    forms: list[str] = []
    seen: set[str] = set()
    for value in values:
        form = normalize_whitespace(str(value))
        key = _normalized_key(form)
        if form and key not in seen:
            seen.add(key)
            forms.append(form)
    return forms


def _entries_by_name(glossary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = glossary.get("entries", [])
    if not isinstance(entries, list):
        raise SystemExit("Glossary 'entries' must be a list.")
    indexed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Glossary entries must contain objects.")
        name = normalize_whitespace(str(entry.get("name", "")))
        key = name.casefold()
        if not name or key in indexed:
            raise SystemExit("Glossary entry names must be unique and non-empty.")
        _alias_forms(entry)
        indexed[key] = entry
    return indexed


def _inventory_by_term(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = inventory.get("results", [])
    if not isinstance(results, list):
        raise SystemExit("Inventory 'results' must be a list.")
    indexed: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            raise SystemExit("Inventory results must contain objects.")
        term = normalize_whitespace(str(item.get("term", "")))
        if not term or term.casefold() in indexed:
            raise SystemExit("Inventory terms must be unique and non-empty.")
        if not isinstance(item.get("surface_forms"), list):
            raise SystemExit(f"Inventory surface_forms must be a list for term: {term}")
        indexed[term.casefold()] = item
    return indexed


def _inventory_files_match(external_item: dict[str, Any], fresh_item: dict[str, Any]) -> bool:
    external_value = str(external_item.get("file", ""))
    fresh_value = str(fresh_item.get("file", ""))
    if not external_value or not fresh_value:
        return external_value == fresh_value
    try:
        return Path(external_value).expanduser().samefile(Path(fresh_value).expanduser())
    except OSError:
        return False


def _bound_forms(entry: dict[str, Any], inventory_item: dict[str, Any]) -> list[str]:
    entry_name = normalize_whitespace(str(entry.get("name", "")))
    inventory_term = normalize_whitespace(str(inventory_item.get("term", "")))
    if entry_name.casefold() != inventory_term.casefold():
        raise SystemExit(
            f"Inventory term does not match entry name: {inventory_term!r} != {entry_name!r}"
        )
    inventory_forms = inventory_item.get("surface_forms", [])
    if not isinstance(inventory_forms, list) or not inventory_forms:
        raise SystemExit(f"Inventory surface_forms must be a non-empty list for term: {inventory_term}")
    exact_inventory: list[str] = []
    for value in inventory_forms:
        if not isinstance(value, str):
            raise SystemExit(f"Inventory surface_forms must contain strings: {inventory_term}")
        if not value or normalize_whitespace(value) != value:
            raise SystemExit(f"Inventory surface_forms must contain exact values: {inventory_term}")
        if value in exact_inventory:
            raise SystemExit(f"Inventory surface_forms must not contain duplicates: {inventory_term}")
        exact_inventory.append(value)
    if inventory_term not in exact_inventory:
        raise SystemExit(f"Inventory canonical name must be present in surface_forms: {entry_name}")
    return exact_inventory


def _validated_fresh_inventory(
    glossary: dict[str, Any], inventory: dict[str, Any], terms_dir: Path
) -> dict[str, dict[str, Any]]:
    external = _inventory_by_term(inventory)
    entries = _entries_by_name(glossary)
    if set(entries) != set(external):
        raise SystemExit("Inventory terms must exactly match glossary entry names.")
    selected = []
    for key, item in external.items():
        entry = entries[key]
        selected.append(
            {
                "term": normalize_whitespace(str(entry["name"])),
                "surface_forms": _bound_forms(entry, item),
            }
        )
    fresh_items = inspect_selected_terms(selected, terms_dir)
    fresh = _inventory_by_term({"results": fresh_items})
    checked_fields = ("state", "link_stem", "missing_fields")
    for key, external_item in external.items():
        fresh_item = fresh.get(key)
        if fresh_item is None:
            raise SystemExit(f"Inventory mismatch for term: {external_item['term']}")
        mismatch = any(external_item.get(field) != fresh_item.get(field) for field in checked_fields)
        mismatch = mismatch or not _inventory_files_match(external_item, fresh_item)
        if mismatch:
            raise SystemExit(f"Inventory mismatch for term: {external_item['term']}")
    return fresh


def _entry_patch(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        field: entry[field]
        for field in CONCEPT_FIELDS
        if normalize_whitespace(str(entry.get(field, "")))
    }


def _valid_confidence(value: Any) -> bool:
    normalized = normalize_whitespace(str(value))
    return normalized in GLOSSARY_CONFIDENCE_VALUES


def _preflight_entries(
    glossary: dict[str, Any], inventory_by_term: dict[str, dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    entries = glossary.get("entries", [])
    if not isinstance(entries, list):
        raise SystemExit("Glossary 'entries' must be a list.")
    planned: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Glossary entries must contain objects.")
        name = normalize_whitespace(str(entry.get("name", "")))
        if not name or name.casefold() in seen:
            raise SystemExit("Glossary entry names must be unique and non-empty.")
        seen.add(name.casefold())
        inventory_item = inventory_by_term.get(name.casefold())
        if inventory_item is None:
            raise SystemExit(f"No inventory item found for term: {name}")
        operation = entry.get("operation")
        state = inventory_item.get("state")
        occurrence = normalize_whitespace(str(entry.get("occurrence", "")))
        if not occurrence:
            raise SystemExit(f"Operation for {name} requires occurrence data.")
        patch = _entry_patch(entry)
        if operation == "create":
            if state != "new":
                raise SystemExit(f"Invalid operation create for inventory state {state}: {name}")
            if not normalize_whitespace(str(entry.get("definition", ""))) or not _valid_confidence(
                entry.get("confidence", "")
            ):
                raise SystemExit(f"Create for {name} requires definition and valid confidence.")
        elif operation == "enrich":
            if state != "existing_thin":
                raise SystemExit(f"Invalid operation enrich for inventory state {state}: {name}")
            missing = set(inventory_item.get("missing_fields", []))
            if not set(patch).issubset(missing):
                raise SystemExit(f"Enrich for {name} may only add inventory missing fields.")
            if "confidence" in missing and not _valid_confidence(entry.get("confidence", "")):
                raise SystemExit(f"Enrich for {name} requires valid confidence when confidence is missing.")
        elif operation == "reuse":
            if state != "existing_complete":
                raise SystemExit(f"Invalid operation reuse for inventory state {state}: {name}")
            if patch:
                raise SystemExit(f"reuse for {name} cannot replace concept fields.")
        else:
            raise SystemExit(f"Invalid operation for {name}: {operation}")
        if state != "new" and not Path(str(inventory_item.get("file", ""))).is_file():
            raise SystemExit(f"Inventory file is missing for term: {name}")
        planned.append((entry, inventory_item))
    return planned


def _contained_existing_path(path_value: Any, terms_dir: Path) -> Path:
    try:
        path = Path(str(path_value)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"Unable to resolve glossary target {path_value}: {exc}") from None
    if not path.is_relative_to(terms_dir) or not path.is_file():
        raise SystemExit(f"Glossary target is outside terms directory: {path}")
    return path


def _allocate_create_path(terms_dir: Path, stem: str, reserved: set[Path]) -> Path:
    counter = 1
    while True:
        suffix = "" if counter == 1 else f"-{counter}"
        candidate = (terms_dir / f"{stem}{suffix}.md").resolve()
        if not candidate.is_relative_to(terms_dir):
            raise SystemExit(f"Glossary target is outside terms directory: {candidate}")
        if candidate not in reserved and not candidate.exists():
            return candidate
        counter += 1


def _prepare_write_plans(
    glossary: dict[str, Any],
    inventory: dict[str, Any],
    terms_dir: Path,
    paper_link: str,
) -> list[dict[str, Any]]:
    root = terms_dir.expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise SystemExit(f"Terms directory is not a directory: {root}")
    fresh_inventory = _validated_fresh_inventory(glossary, inventory, root)
    entries = _preflight_entries(glossary, fresh_inventory)
    library_index = _library_build_alias_index(root)
    target_owners: dict[Path, str] = {}
    logical_owners: dict[str, str] = {}
    reserved: set[Path] = set()
    plans: list[dict[str, Any]] = []

    for entry, inventory_item in entries:
        operation = str(entry["operation"])
        name = normalize_whitespace(str(entry["name"]))
        existing_path = (
            None
            if operation == "create"
            else _contained_existing_path(inventory_item["file"], root)
        )
        collision_forms = _entry_forms(entry, inventory_item)
        for form in collision_forms:
            key = _normalized_key(form)
            library_owner = library_index.get(key)
            if library_owner is not None and (
                existing_path is None or not library_owner.samefile(existing_path)
            ):
                raise SystemExit(
                    f"Glossary alias collision for '{form}' with existing note {library_owner}."
                )
            owner = logical_owners.get(key)
            if owner is not None and owner != name:
                raise SystemExit(f"Duplicate logical term '{form}' for {owner} and {name}.")
            logical_owners[key] = name

        if operation == "create":
            path = _allocate_create_path(
                root, safe_term_filename(str(entry.get("name", ""))), reserved
            )
            text = render_term_file(entry, paper_link, path.stem)
            had_bom = False
            original_bytes = None
            identity = None
            fields_added = [field for field in CONCEPT_FIELDS if field in _entry_patch(entry)]
            action = "created"
            occurrence_added = True
            changed = True
        else:
            path = existing_path
            assert path is not None
            text, had_bom, original_bytes, identity = _read_note_snapshot(path)
            current_state, current_missing = note_state(text)
            if (
                current_state != inventory_item["state"]
                or current_missing != inventory_item["missing_fields"]
            ):
                raise SystemExit(f"Inventory mismatch for term: {name}")
            enriched, fields_added = add_missing_concept_fields(text, _entry_patch(entry))
            updated = append_occurrence(enriched, entry, paper_link)
            occurrence_added = updated != enriched
            changed = updated != text
            text = updated
            if fields_added:
                action = "enriched"
            elif occurrence_added:
                action = "updated"
            else:
                action = "unchanged"

        owner = target_owners.get(path)
        if owner is not None:
            raise SystemExit(f"Duplicate target {path} for {owner} and {name}.")
        target_owners[path] = name
        reserved.add(path)
        plans.append(
            {
                "path": path,
                "text": text,
                "had_bom": had_bom,
                "operation": operation,
                "original_bytes": original_bytes,
                "identity": identity,
                "changed": changed,
                "result": {
                    "name": name,
                    "forms": list(inventory_item["surface_forms"]),
                    "file": str(path),
                    "action": action,
                    "link_stem": path.stem,
                    "fields_added": fields_added,
                    "occurrence_added": occurrence_added,
                },
            }
        )
    return plans


def _encoded_plan_text(plan: dict[str, Any]) -> bytes:
    prefix = b"\xef\xbb\xbf" if plan["had_bom"] else b""
    return prefix + str(plan["text"]).encode("utf-8")


def _stage_existing_temp(plan: dict[str, Any]) -> Path:
    path = Path(plan["path"])
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_encoded_plan_text(plan))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, path.stat().st_mode)
        return temp_path
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _verify_plans_unchanged(plans: list[dict[str, Any]], terms_dir: Path) -> None:
    for plan in plans:
        path = Path(plan["path"])
        if plan["operation"] == "create":
            if path.exists() or path.is_symlink():
                raise SystemExit(f"Create target appeared after planning: {path}")
            try:
                parent = path.parent.resolve(strict=True)
            except OSError as exc:
                raise SystemExit(f"Unable to resolve create target parent {path.parent}: {exc}") from None
            if parent != terms_dir or not path.resolve().is_relative_to(terms_dir):
                raise SystemExit(f"Glossary target is outside terms directory: {path}")
            continue

        try:
            resolved = path.resolve(strict=True)
            identity_before = _file_identity(path)
            raw = path.read_bytes()
            identity_after = _file_identity(path)
        except OSError as exc:
            raise SystemExit(f"Glossary note changed after planning: {path}: {exc}") from None
        if (
            resolved != path
            or not resolved.is_relative_to(terms_dir)
            or identity_before != identity_after
            or identity_after != plan["identity"]
            or raw != plan["original_bytes"]
        ):
            raise SystemExit(f"Glossary note changed after planning: {path}")


def _close_reservations(reservations: list[tuple[dict[str, Any], int]]) -> None:
    for _, descriptor in reservations:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _remove_created_paths(plans: list[dict[str, Any]]) -> None:
    for plan in plans:
        Path(plan["path"]).unlink(missing_ok=True)


def _commit_write_plans(plans: list[dict[str, Any]], terms_dir: Path) -> None:
    terms_dir.mkdir(parents=True, exist_ok=True)
    try:
        resolved_root = terms_dir.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"Unable to resolve terms directory {terms_dir}: {exc}") from None
    if resolved_root != terms_dir or not resolved_root.is_dir():
        raise SystemExit(f"Terms directory changed after planning: {terms_dir}")

    staged: list[dict[str, Any]] = []
    reservations: list[tuple[dict[str, Any], int]] = []
    created_plans: list[dict[str, Any]] = []
    try:
        for plan in plans:
            if plan["operation"] != "create" and plan["changed"]:
                plan["temp_path"] = _stage_existing_temp(plan)
                staged.append(plan)

        _verify_plans_unchanged(plans, terms_dir)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        for plan in plans:
            if plan["operation"] == "create" and plan["changed"]:
                try:
                    descriptor = os.open(plan["path"], flags, 0o666)
                except FileExistsError:
                    raise SystemExit(f"Create target appeared during commit: {plan['path']}") from None
                reservations.append((plan, descriptor))

        for plan, descriptor in reservations:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(_encoded_plan_text(plan))
                handle.flush()
                os.fsync(handle.fileno())
            created_plans.append(plan)
        reservations.clear()

        for plan in staged:
            os.replace(plan["temp_path"], plan["path"])
            plan["temp_path"] = None
    except BaseException:
        reserved_plans = [plan for plan, _ in reservations]
        _close_reservations(reservations)
        _remove_created_paths(created_plans + reserved_plans)
        raise
    finally:
        for plan in staged:
            temp_path = plan.get("temp_path")
            if temp_path is not None:
                Path(temp_path).unlink(missing_ok=True)


def write_glossary_entries(
    glossary: dict[str, Any], inventory: dict[str, Any], terms_dir: Path, paper_link: str
) -> dict[str, Any]:
    validate_provenance_chain(inventory, inventory.get("results"))
    plans = _prepare_write_plans(glossary, inventory, terms_dir, paper_link)
    planned_mappings = [
        (plan["result"]["name"], plan["result"]["forms"]) for plan in plans
    ]
    inventory_mappings = [
        (item["term"], item["surface_forms"]) for item in inventory["results"]
    ]
    if planned_mappings != inventory_mappings:
        raise SystemExit(
            "Planned glossary mappings must exactly match the ordered inventory "
            "term and surface_forms projection."
        )
    _commit_write_plans(plans, terms_dir.expanduser().resolve())
    return {"status": "ok", "results": [plan["result"] for plan in plans]}


def _validated_wiki_link(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
        or any(character in value for character in "[]|#^")
    ):
        raise SystemExit(f"{label} must be a non-empty wiki-link-safe value.")
    return value


def _writer_context(
    paper_id: str, article_value: str, config: dict[str, str]
) -> dict[str, str]:
    if article_value:
        article = validate_article(Path(article_value), config)["article_path"]
        paper_link = Path(article).stem
    else:
        article = ""
        paper_link = paper_id
    return {
        "paper_id": paper_id,
        "paper_link": _validated_wiki_link(paper_link, "Derived backlink"),
        "article_path": article,
    }


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    config = load_config(Path(args.config_path) if args.config_path else None)
    if config is None:
        raise SystemExit("Paper-glossary configuration is missing; configure it first.")
    terms_dir = resolve_terms_dir(config)
    inventory = maybe_load_json_record(args.inventory)
    if inventory is None:
        raise SystemExit(f"Expected JSON object or JSON file path for --inventory: {args.inventory}")
    current = validate_authorized_selection(
        inventory,
        inventory.get("results"),
        args.triage,
        args.source_manifest,
        args.raw_sections,
        args.reviewed_shortlist,
    )
    context = _writer_context(current["paper_id"], args.article, config)
    glossary = maybe_load_json_record(args.glossary)
    if glossary is None:
        raise SystemExit(f"Expected JSON object or JSON file path for --glossary: {args.glossary}")

    result = write_glossary_entries(
        glossary, inventory, terms_dir, context["paper_link"]
    )
    mappings_digest = writer_mappings_sha256(
        current["provenance"],
        result["results"],
        context,
        current["triage_sha256"],
    )
    emit({
        **result,
        "script": "write_glossary_terms.py",
        "paper_id": current["paper_id"],
        "provenance": current["provenance"],
        "context": context,
        "triage_sha256": current["triage_sha256"],
        "mappings_sha256": mappings_digest,
        "terms_dir": str(terms_dir),
        "paper_link": context["paper_link"],
        "article_path": context["article_path"],
        "links": [f"[[{item['link_stem']}]]" for item in result["results"]],
        "elapsed_ms": elapsed_ms(started),
    }, args.output)


if __name__ == "__main__":
    main()
