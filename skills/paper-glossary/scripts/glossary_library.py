from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from glossary_common import normalize_whitespace
from glossary_contracts import (
    GLOSSARY_CONCEPT_HEADING,
    GLOSSARY_LABEL_CONFIDENCE,
    GLOSSARY_LABEL_DEFINITION,
)

CONCEPT_FIELDS = {
    "definition": GLOSSARY_LABEL_DEFINITION,
    "elaboration": "\u8be6\u89e3\uff1a",
    "intuition": "\u76f4\u89c9\uff1a",
    "distinction": "\u4e0e\u76f8\u90bb\u6982\u5ff5\u7684\u533a\u522b\uff1a",
    "confidence": GLOSSARY_LABEL_CONFIDENCE,
}

OBSIDIAN_LINK_STEM_TRANSLATION = str.maketrans(
    {
        "#": "＃",
        "^": "＾",
        "[": "［",
        "]": "］",
        "|": "｜",
        ":": "：",
        "%": "％",
    }
)


def obsidian_safe_link_stem(value: str) -> str:
    return value.translate(OBSIDIAN_LINK_STEM_TRANSLATION)


OPTIONAL_CONCEPT_FIELDS = ("elaboration", "intuition", "distinction")


def _decode_frontmatter_scalar(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise SystemExit("Malformed frontmatter scalar: empty value")
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"'):
            raise SystemExit(f"Malformed frontmatter scalar: {raw}")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            raise SystemExit(f"Malformed frontmatter scalar: {raw}") from None
        if not isinstance(decoded, str):
            raise SystemExit(f"Malformed frontmatter scalar: {raw}")
        result = normalize_whitespace(decoded)
    elif raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise SystemExit(f"Malformed frontmatter scalar: {raw}")
        inner = raw[1:-1]
        decoded_chars: list[str] = []
        index = 0
        while index < len(inner):
            if inner[index] == "'":
                if index + 1 >= len(inner) or inner[index + 1] != "'":
                    raise SystemExit(f"Malformed frontmatter scalar: {raw}")
                decoded_chars.append("'")
                index += 2
                continue
            decoded_chars.append(inner[index])
            index += 1
        result = normalize_whitespace("".join(decoded_chars))
    else:
        if any(character in raw for character in "[]{}\"'#"):
            raise SystemExit(f"Malformed frontmatter scalar: {raw}")
        result = normalize_whitespace(raw)
    if not result:
        raise SystemExit(f"Malformed frontmatter scalar: {raw}")
    return result


def _split_inline_aliases(content: str) -> list[str]:
    if not content.strip():
        return []
    items: list[str] = []
    start = 0
    quote = ""
    index = 0
    while index < len(content):
        character = content[index]
        if quote == '"':
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = ""
        elif quote == "'":
            if character == quote:
                if index + 1 < len(content) and content[index + 1] == quote:
                    index += 2
                    continue
                quote = ""
        elif character in ("'", '"'):
            quote = character
        elif character == ",":
            item = content[start:index].strip()
            if not item:
                raise SystemExit("Malformed aliases metadata: empty inline item.")
            items.append(item)
            start = index + 1
        index += 1
    if quote:
        raise SystemExit("Malformed aliases metadata: unclosed quote.")
    item = content[start:].strip()
    if not item:
        raise SystemExit("Malformed aliases metadata: empty inline item.")
    items.append(item)
    return items


def _frontmatter_block(text: str, source: Path | None = None) -> str | None:
    opening = re.match(r"\A---[ \t]*(?:\r?\n|$)", text)
    if opening is None:
        return None
    closing = re.search(r"(?m)^---[ \t]*\r?$", text[opening.end() :])
    if closing is None:
        location = f" in {source}" if source is not None else ""
        raise SystemExit(f"Unclosed frontmatter{location}.")
    return text[opening.end() : opening.end() + closing.start()]


def read_frontmatter_aliases(text: str, source: Path | None = None) -> list[str]:
    block = _frontmatter_block(text, source)
    if block is None:
        return []
    lines = block.splitlines()
    declarations = [
        (index, match.group(1).strip())
        for index, line in enumerate(lines)
        if (match := re.match(r"^aliases\s*:(.*)$", line))
    ]
    if not declarations:
        return []
    location = f" in {source}" if source is not None else ""
    if len(declarations) != 1:
        raise SystemExit(f"Unsupported aliases metadata{location}: duplicate aliases key.")
    declaration_index, value = declarations[0]
    if value:
        if not value.startswith("[") or not value.endswith("]"):
            raise SystemExit(f"Unsupported aliases metadata{location}: expected a list.")
        return [
            _decode_frontmatter_scalar(item)
            for item in _split_inline_aliases(value[1:-1])
        ]

    aliases: list[str] = []
    for line in lines[declaration_index + 1 :]:
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            break
        item = re.match(r"^[ \t]+-[ \t]+(.+?)[ \t]*$", line)
        if item is None:
            raise SystemExit(f"Unsupported aliases metadata{location}: expected list items.")
        aliases.append(_decode_frontmatter_scalar(item.group(1)))
    return aliases


def read_heading_name(text: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    return normalize_whitespace(match.group(1)) if match else ""


def _normalized_key(value: str) -> str:
    return unicodedata.normalize("NFKC", normalize_whitespace(value)).casefold()


def read_glossary_note(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"Unable to read glossary note {path}: {exc}") from None


def build_alias_index(terms_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    root = terms_dir.expanduser().resolve()
    if not root.is_dir():
        return index
    for unresolved in sorted(root.glob("*.md"), key=lambda item: item.name.casefold()):
        try:
            path = unresolved.resolve(strict=True)
        except OSError as exc:
            raise SystemExit(f"Unable to resolve glossary note {unresolved}: {exc}") from None
        if not path.is_relative_to(root) or not path.is_file():
            raise SystemExit(f"Glossary note resolves outside terms directory: {unresolved}")
        text = read_glossary_note(path)
        keys = {_normalized_key(unresolved.stem)}
        keys.update(_normalized_key(alias) for alias in read_frontmatter_aliases(text, path))
        heading = read_heading_name(text)
        if heading:
            keys.add(_normalized_key(heading))
        for key in keys:
            existing = index.get(key)
            if existing is not None and existing != path:
                raise SystemExit(
                    f"Glossary key collision for '{key}' between {existing} and {path}."
                )
            index[key] = path
    return index


def _section_bounds(text: str) -> tuple[int, int] | None:
    heading = re.search(
        rf"(?m)^##\s+{re.escape(GLOSSARY_CONCEPT_HEADING)}\s*$(?:\r?\n)?", text
    )
    if heading is None:
        return None
    following = re.search(r"(?m)^##\s+", text[heading.end() :])
    end = heading.end() + following.start() if following else len(text)
    return heading.end(), end


def _field_present(section: str, label: str) -> bool:
    return bool(
        re.search(rf"(?m)^[ \t]*(?:-[ \t]*)?{re.escape(label)}[ \t]*\S", section)
    )


def missing_concept_fields(text: str) -> list[str]:
    bounds = _section_bounds(text)
    if bounds is None:
        return list(CONCEPT_FIELDS)
    section = text[bounds[0] : bounds[1]]
    return [field for field, label in CONCEPT_FIELDS.items() if not _field_present(section, label)]


def note_state(text: str) -> tuple[str, list[str]]:
    missing = missing_concept_fields(text)
    optional_present = sum(field not in missing for field in OPTIONAL_CONCEPT_FIELDS)
    required_missing = any(field in missing for field in ("definition", "confidence"))
    state = "existing_thin" if required_missing or optional_present < 2 else "existing_complete"
    return state, missing


def _line_ending(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _field_line(field: str, value: Any, line_ending: str) -> str:
    return f"- {CONCEPT_FIELDS[field]}{normalize_whitespace(str(value))}{line_ending}"


def _field_lines(fields: list[str], patch: dict[str, Any], line_ending: str) -> str:
    return "".join(_field_line(field, patch[field], line_ending) for field in fields)


def add_missing_concept_fields(text: str, patch: dict[str, Any]) -> tuple[str, list[str]]:
    missing = set(missing_concept_fields(text))
    fields_added = [
        field
        for field in CONCEPT_FIELDS
        if field in missing and normalize_whitespace(str(patch.get(field, "")))
    ]
    if not fields_added:
        return text, []

    line_ending = _line_ending(text)
    bounds = _section_bounds(text)
    if bounds is None:
        prefix = "" if not text else (line_ending if text.endswith(("\n", "\r")) else line_ending * 2)
        if text and text.endswith(("\n", "\r")):
            prefix = line_ending
        section = f"## {GLOSSARY_CONCEPT_HEADING}{line_ending}"
        return text + prefix + section + _field_lines(fields_added, patch, line_ending), fields_added

    start, end = bounds
    section = text[start:end]
    existing_confidence = re.search(
        rf"(?m)^\s*(?:-\s*)?{re.escape(CONCEPT_FIELDS['confidence'])}", section
    )
    optional_fields = [field for field in OPTIONAL_CONCEPT_FIELDS if field in fields_added]
    confidence_fields = [field for field in ("confidence",) if field in fields_added]
    definition_fields = [field for field in ("definition",) if field in fields_added]
    insertions: list[tuple[int, str]] = []
    if definition_fields:
        insertions.append((start, _field_lines(definition_fields, patch, line_ending)))
    if optional_fields:
        position = start + existing_confidence.start() if existing_confidence else end
        insertions.append((position, _field_lines(optional_fields, patch, line_ending)))
    if confidence_fields:
        insertions.append((end, _field_lines(confidence_fields, patch, line_ending)))
    updated = text
    for position, insertion in sorted(insertions, key=lambda item: item[0], reverse=True):
        updated = updated[:position] + insertion + updated[position:]
    return updated, fields_added


def _surface_forms(item: dict[str, Any]) -> list[str]:
    term = item.get("term")
    surface_forms = item.get("surface_forms")
    if not isinstance(term, str) or not term or normalize_whitespace(term) != term:
        raise SystemExit("Selected term must be a non-empty normalized string.")
    if not isinstance(surface_forms, list) or not surface_forms:
        raise SystemExit(f"surface_forms must be a non-empty list for term: {term}")
    forms: list[str] = []
    for value in surface_forms:
        if not isinstance(value, str) or not value or normalize_whitespace(value) != value:
            raise SystemExit(f"surface_forms must contain exact non-empty strings: {term}")
        if value in forms:
            raise SystemExit(f"surface_forms must not contain duplicates: {term}")
        forms.append(value)
    if term not in forms:
        raise SystemExit(f"surface_forms must contain the exact selected term: {term}")
    return forms


def inspect_selected_terms(selected: list[dict[str, Any]], terms_dir: Path) -> list[dict[str, Any]]:
    index = build_alias_index(terms_dir)
    results: list[dict[str, Any]] = []
    for item in selected:
        if not isinstance(item, dict):
            raise SystemExit("Selected terms must contain objects with surface_forms.")
        term = item.get("term")
        if not isinstance(term, str):
            raise SystemExit("Selected term must be a string with surface_forms.")
        forms = _surface_forms(item)
        matches = {
            index[_normalized_key(form)]
            for form in forms
            if _normalized_key(form) in index
        }
        if len(matches) > 1:
            raise SystemExit(
                f"Selected forms resolve to multiple glossary notes for term: {term}"
            )
        path = next(iter(matches), None)
        if path is None:
            results.append(
                {
                    "term": term,
                    "surface_forms": forms,
                    "state": "new",
                    "file": "",
                    "link_stem": term,
                    "missing_fields": [],
                }
            )
            continue
        safe_stem = obsidian_safe_link_stem(path.stem)
        if safe_stem != path.stem:
            raise SystemExit(
                f"Existing glossary note has an Obsidian-unsafe filename: {path.name}; "
                f"rename it to {safe_stem}.md before continuing."
            )
        text = read_glossary_note(path)
        state, missing = note_state(text)
        results.append(
            {
                "term": term,
                "surface_forms": forms,
                "state": state,
                "file": str(path),
                "link_stem": path.stem,
                "missing_fields": missing,
            }
        )
    return results
