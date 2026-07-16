#!/usr/bin/env python3
"""Add one safe glossary wiki link per selected term to an explicit article."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_common import (
    elapsed_ms,
    emit,
    load_json_file,
    validate_authorized_selection,
    writer_mappings_sha256,
)
from glossary_config import load_config, resolve_terms_dir, validate_article
from glossary_library import _normalized_key, build_alias_index


REFERENCE_HEADING_RE = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]+(?:references|bibliography|参考文献)[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__ or "link glossary terms")
    command.add_argument("--input", required=True, help="Explicit article Markdown path.")
    command.add_argument("--write-result", required=True, help="Successful writer result JSON path.")
    command.add_argument("--expected-sha256", required=True, help="Preview-time article SHA-256.")
    command.add_argument("--config-path", default="", help="Device-local configuration path.")
    command.add_argument("--source-manifest", required=True, help="Current source manifest.")
    command.add_argument("--raw-sections", default="", help="Optional current raw-sections JSONL.")
    command.add_argument(
        "--reviewed-shortlist", required=True, help="Saved reviewed-shortlist artifact."
    )
    command.add_argument("--triage", required=True, help="Saved authorized triage artifact.")
    command.add_argument("--output", default="", help="Output JSON status path.")
    return command


def term_pattern(form: str) -> re.Pattern[str]:
    escaped = re.escape(form)
    if form.isascii():
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _line_end(text: str, start: int) -> int:
    newline = text.find("\n", start)
    return len(text) if newline == -1 else newline + 1


def _offset_in_spans(offset: int, spans: list[tuple[int, int]]) -> bool:
    for start, end in spans:
        if offset < start:
            return False
        if offset < end:
            return True
    return False


def _list_content_start(content: str) -> int:
    position = 0
    while True:
        marker = re.match(
            r"(?:[*+-]|\d{1,9}[.)])(?:[ \t]+|$)", content[position:]
        )
        if marker is None:
            return position
        position += marker.end()


def _fenced_code_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    opener: tuple[str, int, int, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        content_end = offset + len(line.rstrip("\r\n"))
        line_content = _reference_line_content_start(text, offset)
        if line_content is None:
            content = ""
            quote_depth = -1
        else:
            content_start, quote_depth = line_content
            content = text[content_start:content_end]
        if opener is None:
            list_content = content[_list_content_start(content) :]
            match = re.match(r"(`{3,}|~{3,})", list_content)
            if match:
                marker = match.group(1)
                opener = (marker[0], len(marker), offset, quote_depth)
        else:
            closer = re.fullmatch(r"(`+|~+)[ \t]*", content)
            if (
                closer
                and closer.group(1)[0] == opener[0]
                and len(closer.group(1)) >= opener[1]
                and quote_depth == opener[3]
            ):
                spans.append((opener[2], offset + len(line)))
                opener = None
        offset += len(line)
    if opener is not None:
        spans.append((opener[2], len(text)))
    return spans


def _frontmatter_span(text: str) -> tuple[int, int] | None:
    lines = text.splitlines(keepends=True)
    if not lines or not re.fullmatch(r"---[ \t]*", lines[0].rstrip("\r\n")):
        return None
    offset = len(lines[0])
    for line in lines[1:]:
        if re.fullmatch(r"(?:---|\.\.\.)[ \t]*", line.rstrip("\r\n")):
            return 0, offset + len(line)
        offset += len(line)
    return 0, len(text)


def _inline_code_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("`", cursor)
        if start == -1:
            break
        opener_end = start
        while opener_end < len(text) and text[opener_end] == "`":
            opener_end += 1
        if _offset_in_spans(start, protected):
            cursor = opener_end
            continue
        delimiter_length = opener_end - start
        search = opener_end
        matched = False
        while search < len(text):
            closer = text.find("`", search)
            if closer == -1:
                break
            closer_end = closer
            while closer_end < len(text) and text[closer_end] == "`":
                closer_end += 1
            if (
                closer_end - closer == delimiter_length
                and not _offset_in_spans(closer, protected)
            ):
                spans.append((start, closer_end))
                cursor = closer_end
                matched = True
                break
            search = closer_end
        if not matched:
            cursor = opener_end
    return spans


def _markdown_link_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        label_start = text.find("[", cursor)
        if label_start == -1:
            break
        if _offset_in_spans(label_start, protected):
            cursor = label_start + 1
            continue
        depth = 1
        position = label_start + 1
        while position < len(text) and depth:
            if text[position] == "\\":
                position += 2
                continue
            if text[position] == "[":
                depth += 1
            elif text[position] == "]":
                depth -= 1
            position += 1
        if depth or position >= len(text) or text[position] != "(":
            cursor = label_start + 1
            continue
        destination_depth = 1
        position += 1
        while position < len(text) and destination_depth:
            if text[position] == "\\":
                position += 2
                continue
            if text[position] == "(":
                destination_depth += 1
            elif text[position] == ")":
                destination_depth -= 1
            position += 1
        if destination_depth:
            cursor = label_start + 1
            continue
        start = label_start - 1 if label_start and text[label_start - 1] == "!" else label_start
        spans.append((start, position))
        cursor = position
    return spans


def _scan_markdown_label(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "[":
        return None
    depth = 1
    position = start + 1
    while position < len(text) and depth:
        if text[position] == "\\":
            position += 2
            continue
        if text[position] in "\r\n":
            return None
        if text[position] == "[":
            depth += 1
        elif text[position] == "]":
            depth -= 1
        position += 1
    if depth:
        return None
    return text[start + 1 : position - 1], position


def _reference_label_key(label: str) -> str:
    unescaped = re.sub(r"\\(.)", r"\1", label)
    return " ".join(unescaped.split()).casefold()


def _skip_spaces_tabs(text: str, position: int) -> int:
    while position < len(text) and text[position] in " \t":
        position += 1
    return position


def _after_line_ending(text: str, position: int) -> int | None:
    if text.startswith("\r\n", position):
        return position + 2
    if position < len(text) and text[position] in "\r\n":
        return position + 1
    return None


def _scan_reference_destination(text: str, position: int) -> int | None:
    if position >= len(text):
        return None
    if text[position] == "<":
        position += 1
        while position < len(text):
            if text[position] == "\\" and position + 1 < len(text):
                position += 2
                continue
            if text[position] == ">":
                return position + 1
            if text[position] in "<>\r\n":
                return None
            position += 1
        return None

    start = position
    depth = 0
    while position < len(text) and text[position] not in " \t\r\n":
        if text[position] == "\\" and position + 1 < len(text):
            position += 2
            continue
        if text[position] == "(":
            depth += 1
        elif text[position] == ")":
            if depth == 0:
                return None
            depth -= 1
        position += 1
    return position if position > start and depth == 0 else None


def _scan_reference_title(text: str, position: int) -> int | None:
    closer = {'"': '"', "'": "'", "(": ")"}.get(
        text[position] if position < len(text) else ""
    )
    if closer is None:
        return None
    position += 1
    while position < len(text):
        if text[position] == "\\" and position + 1 < len(text):
            position += 2
            continue
        if text[position] == closer:
            trailing = _skip_spaces_tabs(text, position + 1)
            if trailing == len(text) or _after_line_ending(text, trailing) is not None:
                return _line_end(text, trailing)
            return None
        next_line = _after_line_ending(text, position)
        if next_line is not None:
            content = _skip_spaces_tabs(text, next_line)
            if content == len(text) or _after_line_ending(text, content) is not None:
                return None
            position = next_line
            continue
        position += 1
    return None


def _reference_line_content_start(
    text: str, line_start: int, required_quote_depth: int | None = None
) -> tuple[int, int] | None:
    content_end = line_start + len(
        text[line_start : _line_end(text, line_start)].rstrip("\r\n")
    )
    position = line_start
    quote_depth = 0
    while True:
        indent_start = position
        while position < content_end and text[position] in " \t":
            position += 1
        if position - indent_start > 3:
            return None
        if position >= content_end or text[position] != ">":
            break
        quote_depth += 1
        position += 1
        if position < content_end and text[position] in " \t":
            position += 1
    if required_quote_depth is not None and quote_depth != required_quote_depth:
        return None
    return position, quote_depth


def _indented_code_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    while offset < len(text):
        line_end = _line_end(text, offset)
        content_end = offset + len(text[offset:line_end].rstrip("\r\n"))
        position = offset
        quote_depth = 0
        while True:
            marker = position
            spaces = 0
            while marker < content_end and text[marker] == " " and spaces < 3:
                marker += 1
                spaces += 1
            if marker >= content_end or text[marker] != ">":
                break
            quote_depth += 1
            position = marker + 1
            if position < content_end and text[position] in " \t":
                position += 1
        if quote_depth == 0:
            position = offset
        if (
            not _offset_in_spans(offset, protected)
            and (
                text.startswith("    ", position)
                or (position < content_end and text[position] == "\t")
            )
        ):
            spans.append((offset, line_end))
        offset = line_end
    return spans


def _heading_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    while offset < len(text):
        line_end = _line_end(text, offset)
        line_content = _reference_line_content_start(text, offset)
        if line_content is not None and not _offset_in_spans(offset, protected):
            content_start, quote_depth = line_content
            content = text[content_start:line_end].rstrip("\r\n")
            heading = content[_list_content_start(content) :]
            if re.match(r"#{1,6}(?:[ \t]+|$)", heading):
                spans.append((offset, line_end))
            elif content.strip() and line_end < len(text):
                underline_end = _line_end(text, line_end)
                underline_content = _reference_line_content_start(
                    text, line_end, required_quote_depth=quote_depth
                )
                if (
                    underline_content is not None
                    and not _offset_in_spans(line_end, protected)
                ):
                    underline_start, _ = underline_content
                    underline = text[underline_start:underline_end].rstrip("\r\n")
                    if re.fullmatch(r"(?:=+|-+)[ \t]*", underline):
                        spans.append((offset, underline_end))
        offset = line_end
    return spans


def _scan_reference_definition(
    text: str, line_start: int, protected: list[tuple[int, int]]
) -> tuple[str, int] | None:
    content_end = line_start + len(
        text[line_start : _line_end(text, line_start)].rstrip("\r\n")
    )
    line_content = _reference_line_content_start(text, line_start)
    if line_content is None:
        return None
    start, quote_depth = line_content
    if _offset_in_spans(start, protected):
        return None
    label = _scan_markdown_label(text, start)
    if label is None:
        return None
    value, position = label
    if not value or position >= content_end or text[position] != ":":
        return None

    position = _skip_spaces_tabs(text, position + 1)
    next_line = _after_line_ending(text, position)
    if next_line is not None:
        continuation = _reference_line_content_start(
            text, next_line, required_quote_depth=quote_depth
        )
        if continuation is None:
            return None
        position, _ = continuation
    destination_end = _scan_reference_destination(text, position)
    if destination_end is None:
        return None
    block_end = _line_end(text, destination_end)

    title_start = _skip_spaces_tabs(text, destination_end)
    if title_start < len(text) and text[title_start] not in "\r\n":
        if title_start == destination_end:
            return None
        title_end = _scan_reference_title(text, title_start)
        if title_end is None:
            return None
        block_end = title_end
    else:
        title_line = _after_line_ending(text, title_start)
        if title_line is not None:
            continuation = _reference_line_content_start(
                text, title_line, required_quote_depth=quote_depth
            )
            if continuation is not None:
                possible_title, _ = continuation
                title_end = _scan_reference_title(text, possible_title)
                if title_end is not None:
                    block_end = title_end
    return _reference_label_key(value), block_end


def _markdown_reference_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    definitions: set[str] = set()
    spans: list[tuple[int, int]] = []
    offset = 0
    while offset < len(text):
        definition = _scan_reference_definition(text, offset, protected)
        if definition is not None:
            label, end = definition
            definitions.add(label)
            spans.append((offset, end))
        offset = _line_end(text, offset)

    cursor = 0
    while cursor < len(text):
        start = text.find("[", cursor)
        if start == -1:
            break
        if _offset_in_spans(start, protected):
            cursor = start + 1
            continue
        label = _scan_markdown_label(text, start)
        if label is None:
            cursor = start + 1
            continue
        value, position = label
        reference_key = _reference_label_key(value)
        end = position
        if position < len(text) and text[position] == "[":
            reference = _scan_markdown_label(text, position)
            if reference is None:
                cursor = position + 1
                continue
            reference_value, end = reference
            reference_key = _reference_label_key(reference_value or value)
        if value and reference_key in definitions:
            link_start = start - 1 if start and text[start - 1] == "!" else start
            spans.append((link_start, end))
        cursor = end
    return spans


_MARKDOWN_AUTOLINK = re.compile(
    r"<(?:"
    r"[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\x00-\x20]*"
    r"|[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
    r")>"
)


def _markdown_autolink_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    return [
        match.span()
        for match in _MARKDOWN_AUTOLINK.finditer(text)
        if not _offset_in_spans(match.start(), protected)
    ]


_HTML_VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

_HTML_LINKABLE_TEXT_ELEMENTS = {"b", "em", "i", "strong"}


def _scan_html_tag(
    text: str, start: int
) -> tuple[str, int, bool, bool, bool] | None:
    position = start + 1
    closing = position < len(text) and text[position] == "/"
    if closing:
        position += 1
    name_match = re.match(r"[A-Za-z][A-Za-z0-9:-]*", text[position:])
    if name_match is None:
        return None
    name = name_match.group(0).casefold()
    position += name_match.end()
    if position < len(text) and not (
        text[position].isspace() or text[position] in "/>"
    ):
        return None

    quote = ""
    while position < len(text):
        character = text[position]
        if quote:
            if character == quote:
                quote = ""
        elif character in ("'", '"'):
            quote = character
        elif character == ">":
            before_close = text[start + 1 : position].rstrip()
            self_closing = not closing and before_close.endswith("/")
            return name, position + 1, closing, self_closing, True
        position += 1
    return name, len(text), closing, False, False


def _html_spans(
    text: str, protected: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    malformed_start: int | None = None
    cursor = 0
    while cursor < len(text):
        start = text.find("<", cursor)
        if start == -1:
            break
        if _offset_in_spans(start, protected):
            cursor = start + 1
            continue
        if text.startswith("<!--", start):
            comment_end = text.find("-->", start + 4)
            if comment_end == -1:
                spans.append((start, len(text)))
                break
            spans.append((start, comment_end + 3))
            cursor = comment_end + 3
            continue
        tag = _scan_html_tag(text, start)
        if tag is None:
            cursor = start + 1
            continue
        name, end, closing, self_closing, terminated = tag
        spans.append((start, end))
        if not terminated:
            break
        if closing:
            if stack and stack[-1][0] == name:
                element_name, element_start = stack.pop()
                if element_name not in _HTML_LINKABLE_TEXT_ELEMENTS:
                    spans.append((element_start, end))
                if malformed_start is not None and not stack:
                    spans.append((malformed_start, end))
                    malformed_start = None
            elif stack and malformed_start is None:
                malformed_start = min(element_start for _, element_start in stack)
        elif not self_closing and name not in _HTML_VOID_ELEMENTS:
            stack.append((name, start))
        cursor = end
    if stack or malformed_start is not None:
        open_starts = [start for _, start in stack]
        if malformed_start is not None:
            open_starts.append(malformed_start)
        spans.append((min(open_starts), len(text)))
    return spans


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted((start, end) for start, end in spans if start < end):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _wiki_link_context(
    text: str, protected: list[tuple[int, int]]
) -> tuple[list[tuple[int, int]], set[str]]:
    spans: list[tuple[int, int]] = []
    targets: set[str] = set()
    for match in re.finditer(r"\[\[([^\]\r\n]*)\]\]", text):
        if _offset_in_spans(match.start(), protected):
            continue
        spans.append(match.span())
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.add(target.casefold())
    return spans, targets


def _protected_context(text: str) -> tuple[list[tuple[int, int]], set[str]]:
    spans = _fenced_code_spans(text)
    frontmatter = _frontmatter_span(text)
    if frontmatter:
        spans.append(frontmatter)
    spans = _merge_spans(spans)

    spans = _merge_spans([*spans, *_indented_code_spans(text, spans)])
    spans = _merge_spans([*spans, *_inline_code_spans(text, spans)])
    spans = _merge_spans([*spans, *_markdown_autolink_spans(text, spans)])
    spans = _merge_spans([*spans, *_html_spans(text, spans)])
    spans = _merge_spans([*spans, *_markdown_link_spans(text, spans)])
    spans = _merge_spans([*spans, *_markdown_reference_spans(text, spans)])
    wiki_spans, targets = _wiki_link_context(text, spans)
    spans = _merge_spans([*spans, *wiki_spans])
    high_priority_spans = spans

    headings = _heading_spans(text, spans)
    spans = _merge_spans([*spans, *headings])
    html_tags = [
        match.span()
        for match in re.finditer(r"<[^>\r\n]+>", text)
        if not _offset_in_spans(match.start(), spans)
    ]
    spans = _merge_spans([*spans, *html_tags])
    urls = [
        match.span()
        for match in re.finditer(r"https?://[^\s<>\]\)]+", text)
        if not _offset_in_spans(match.start(), spans)
    ]
    spans = _merge_spans([*spans, *urls])
    references = next(
        (
            match
            for match in REFERENCE_HEADING_RE.finditer(text)
            if not _offset_in_spans(match.start(), high_priority_spans)
        ),
        None,
    )
    if references:
        spans.append((references.start(), len(text)))
    return _merge_spans(spans), targets


def protected_spans(text: str) -> list[tuple[int, int]]:
    spans, _ = _protected_context(text)
    return spans


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < protected_end and end > protected_start for protected_start, protected_end in spans)


def _normalized_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    by_target: dict[str, dict[str, Any]] = {}
    seen_forms: dict[str, set[str]] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise SystemExit("Writer results must contain objects.")
        link_stem = str(mapping.get("link_stem", "")).strip()
        forms = mapping.get("forms", [])
        if not link_stem or not isinstance(forms, list):
            raise SystemExit("Writer result requires link_stem and forms.")
        target_key = link_stem.casefold()
        item = by_target.get(target_key)
        if item is None:
            item = {"link_stem": link_stem, "forms": []}
            by_target[target_key] = item
            seen_forms[target_key] = set()
            normalized.append(item)
        for value in forms:
            if not isinstance(value, str) or not value.strip():
                raise SystemExit(f"Writer result has an invalid form for {link_stem}.")
            form = value.strip()
            key = form.casefold()
            if key not in seen_forms[target_key]:
                seen_forms[target_key].add(key)
                item["forms"].append(form)
        if not item["forms"]:
            raise SystemExit(f"Writer result has no forms for {link_stem}.")
    return normalized


def _write_atomically(path: Path, data: bytes, original: bytes) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.read_bytes() != original:
            raise SystemExit(f"Article changed while linking: {path}")
        os.replace(temp_path, path)
        replaced = True
    finally:
        if not replaced:
            temp_path.unlink(missing_ok=True)


def link_article_terms(
    article: Path, mappings: list[dict[str, Any]], expected_sha256: str
) -> dict[str, Any]:
    path = article.expanduser().resolve()
    original = path.read_bytes()
    actual_sha256 = hashlib.sha256(original).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SystemExit(f"Article changed since preview: {path}")

    had_bom = original.startswith(b"\xef\xbb\xbf")
    text = original[3 if had_bom else 0 :].decode("utf-8")
    protected, targets = _protected_context(text)
    normalized = _normalized_mappings(mappings)
    planned: list[tuple[int, int, str]] = []
    planned_targets: set[str] = set()
    statuses: dict[int, str] = {}

    order = sorted(
        range(len(normalized)),
        key=lambda index: max(len(form) for form in normalized[index]["forms"]),
        reverse=True,
    )
    for index in order:
        mapping = normalized[index]
        link_stem = mapping["link_stem"]
        target_key = link_stem.casefold()
        if target_key in targets or target_key in planned_targets:
            statuses[index] = "already_linked"
            continue
        matched = None
        for form in sorted(mapping["forms"], key=len, reverse=True):
            for candidate in term_pattern(form).finditer(text):
                if _overlaps(candidate.start(), candidate.end(), protected):
                    continue
                if _overlaps(candidate.start(), candidate.end(), [(start, end) for start, end, _ in planned]):
                    continue
                matched = candidate
                break
            if matched is not None:
                break
        if matched is None:
            statuses[index] = "not_found"
            continue
        surface = matched.group(0)
        replacement = f"[[{link_stem}]]" if surface == link_stem else f"[[{link_stem}|{surface}]]"
        planned.append((matched.start(), matched.end(), replacement))
        planned_targets.add(target_key)
        statuses[index] = "linked"

    if planned:
        updated = text
        for start, end, replacement in sorted(planned, reverse=True):
            updated = updated[:start] + replacement + updated[end:]
        data = (b"\xef\xbb\xbf" if had_bom else b"") + updated.encode("utf-8")
        _write_atomically(path, data, original)

    results = [
        {"link_stem": mapping["link_stem"], "status": statuses[index]}
        for index, mapping in enumerate(normalized)
    ]
    summary = {status: sum(item["status"] == status for item in results) for status in ("linked", "already_linked", "not_found")}
    return {"status": "ok", "article_path": str(path), "results": results, "summary": summary}


def _validated_writer_results(
    path: Path,
    terms_dir: Path,
    article_path: str,
    source_manifest: str,
    raw_sections: str,
    reviewed_shortlist: str,
    triage_artifact: str,
) -> list[dict[str, Any]]:
    payload = load_json_file(path)
    results = payload.get("results")
    if (
        payload.get("status") != "ok"
        or payload.get("script") != "write_glossary_terms.py"
        or not isinstance(results, list)
    ):
        raise SystemExit("Linker requires a successful writer result with results.")
    provenance = payload.get("provenance")
    context = payload.get("context")
    if not isinstance(provenance, dict) or not isinstance(context, dict):
        raise SystemExit("Writer result requires provenance and article context.")
    current = validate_authorized_selection(
        payload,
        results,
        triage_artifact,
        source_manifest,
        raw_sections,
        reviewed_shortlist,
        term_field="name",
        forms_field="forms",
    )
    triage_digest = payload.get("triage_sha256")
    if triage_digest != current["triage_sha256"]:
        raise SystemExit("Writer triage identity does not match the authorized artifact.")
    if payload.get("mappings_sha256") != writer_mappings_sha256(
        provenance, results, context, triage_digest
    ):
        raise SystemExit("Writer mapping digest does not match the ordered mappings.")
    expected_context = {
        "paper_id": current["paper_id"],
        "paper_link": Path(article_path).stem,
        "article_path": article_path,
    }
    if not context.get("article_path"):
        raise SystemExit("Linker requires a writer artifact with bound article context.")
    if context != expected_context:
        raise SystemExit("Writer article context does not match the explicit article.")

    root = terms_dir.resolve(strict=True)
    index = build_alias_index(root)
    seen_paths: set[Path] = set()
    seen_stems: set[str] = set()
    for item in results:
        file_value = item.get("file")
        link_stem = item.get("link_stem")
        forms = item.get("forms")
        if (
            not isinstance(file_value, str)
            or not file_value
            or not isinstance(link_stem, str)
            or not link_stem
            or not isinstance(forms, list)
            or not forms
        ):
            raise SystemExit("Writer mapping requires file, link_stem, and forms.")
        unresolved = Path(file_value).expanduser()
        try:
            resolved = unresolved.resolve(strict=True)
        except OSError as exc:
            raise SystemExit(f"Writer mapping glossary file is invalid: {file_value}: {exc}") from None
        if (
            not unresolved.is_absolute()
            or file_value != str(resolved)
            or not resolved.is_file()
            or resolved.suffix.lower() != ".md"
            or not resolved.is_relative_to(root)
        ):
            raise SystemExit(f"Writer mapping file is outside the configured glossary: {file_value}")
        if link_stem != resolved.stem:
            raise SystemExit("Writer mapping link_stem does not match its glossary file stem.")
        if resolved in seen_paths or link_stem.casefold() in seen_stems:
            raise SystemExit("Writer mappings must have unique glossary files and stems.")
        seen_paths.add(resolved)
        seen_stems.add(link_stem.casefold())
        for form in forms:
            if not isinstance(form, str) or not form:
                raise SystemExit("Writer mapping forms must be non-empty strings.")
            owner = index.get(_normalized_key(form))
            if owner is None or not owner.samefile(resolved):
                raise SystemExit(
                    f"Writer mapping form does not resolve to its glossary file: {form}"
                )
    return results


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    config = load_config(Path(args.config_path)) if args.config_path else load_config()
    if config is None:
        raise SystemExit("Paper-glossary is not configured; configure a term directory first.")
    terms_dir = resolve_terms_dir(config)
    article_info = validate_article(Path(args.input), config)
    article = Path(article_info["article_path"])
    result = link_article_terms(
        article,
        _validated_writer_results(
            Path(args.write_result),
            terms_dir,
            article_info["article_path"],
            args.source_manifest,
            args.raw_sections,
            args.reviewed_shortlist,
            args.triage,
        ),
        args.expected_sha256,
    )
    emit(
        {
            **result,
            "script": "link_glossary_terms.py",
            "elapsed_ms": elapsed_ms(started),
        },
        args.output,
    )


if __name__ == "__main__":
    main()
