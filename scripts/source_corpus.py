#!/usr/bin/env python3
"""Source Corpus loader, validator, and deterministic derived views."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SOURCE_CORPUS_ISSUE_SEVERITY = "error"


class SourceCorpusLoadError(RuntimeError):
    """Raised when the source manifest itself cannot be constructed."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _issue(code: str, *, message: str, path: str = "", **details: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "code": code,
        "severity": SOURCE_CORPUS_ISSUE_SEVERITY,
        "message": message,
    }
    if path:
        issue["path"] = path
    issue.update(details)
    return issue


def _copy_record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


def _record_has_appendix_hint(record: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(record.get(key, ""))
        for key in ("kind", "title", "section_id")
    ).lower()
    return any(
        token in searchable
        for token in ("appendix", "appendices", "supplementary", "附录", "补充材料")
    )


def _resolve_manifest_path(source_manifest_path: str | Path) -> Path:
    return Path(source_manifest_path).expanduser().resolve()


def _resolve_raw_sections_path(manifest_path: Path, manifest: dict[str, Any]) -> Path | None:
    raw_path_value = str(manifest.get("raw_sections_path", "")).strip()
    if not raw_path_value:
        return None
    raw_path = Path(raw_path_value).expanduser()
    if not raw_path.is_absolute():
        raw_path = manifest_path.parent / raw_path
    return raw_path.resolve()


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SourceCorpusLoadError(f"source manifest not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceCorpusLoadError(f"source manifest is invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise SourceCorpusLoadError(f"source manifest must be a JSON object: {path}")
    return data


def _load_raw_sections(
    raw_sections_path: Path | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if raw_sections_path is None:
        return [], [
            _issue(
                "source_corpus_raw_sections_missing",
                message="source_manifest.raw_sections_path is missing",
                path="raw_sections_path",
            )
        ]
    if not raw_sections_path.is_file():
        return [], [
            _issue(
                "source_corpus_raw_sections_missing",
                message="raw sections JSONL file is missing",
                path=str(raw_sections_path),
            )
        ]

    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_sections_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            issues.append(
                _issue(
                    "source_corpus_raw_sections_invalid_jsonl",
                    message="raw sections JSONL line is invalid JSON",
                    path=str(raw_sections_path),
                    line=line_number,
                )
            )
            continue
        if not isinstance(parsed, dict):
            issues.append(
                _issue(
                    "source_corpus_raw_sections_invalid_jsonl",
                    message="raw sections JSONL line must be a JSON object",
                    path=str(raw_sections_path),
                    line=line_number,
                )
            )
            continue
        records.append(parsed)
    return records, issues


@dataclass(frozen=True)
class SourceCorpus:
    manifest_path: Path
    manifest: dict[str, Any]
    raw_sections_path: Path | None
    raw_sections: list[dict[str, Any]]
    load_issues: list[dict[str, Any]] = field(default_factory=list)

    def full_text(self) -> str:
        return "\n\n".join(
            str(record.get("text", "")).strip()
            for record in self.raw_sections
            if str(record.get("text", "")).strip()
        )

    def section_map(self) -> dict[str, dict[str, Any]]:
        raw_by_section = {
            str(record.get("section_id", "")): record
            for record in self.raw_sections
            if str(record.get("section_id", "")).strip()
        }
        sections: dict[str, dict[str, Any]] = {}
        for section in _copy_list(self.manifest.get("sections")):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("section_id", "")).strip()
            if not section_id:
                continue
            record = dict(section)
            raw_record = raw_by_section.get(section_id)
            if raw_record is not None:
                record.update({"text": raw_record.get("text", ""), "raw_record": dict(raw_record)})
            sections[section_id] = record
        for section_id, raw_record in raw_by_section.items():
            if section_id not in sections:
                sections[section_id] = dict(raw_record)
        return sections

    def caption_items(self) -> list[dict[str, Any]]:
        captions = self.manifest.get("captions", {})
        if not isinstance(captions, dict):
            return []
        items: list[dict[str, Any]] = []
        for manifest_key, kind in (("figures", "figure"), ("tables", "table")):
            for item in _copy_list(captions.get(manifest_key)):
                if isinstance(item, dict):
                    items.append({"kind": kind, **dict(item)})
        return items

    def appendix_pages(self) -> list[dict[str, Any]]:
        appendix_index = self.manifest.get("appendix_index", {})
        coverage = self.manifest.get("coverage", {})
        start_page = None
        if isinstance(appendix_index, dict):
            start_page = _positive_int(appendix_index.get("start_page"))
        if start_page is None and isinstance(coverage, dict):
            start_page = _positive_int(coverage.get("appendix_start_page"))
        if start_page is None:
            return []
        return [
            dict(page)
            for page in _copy_list(self.manifest.get("pages"))
            if isinstance(page, dict) and (_positive_int(page.get("page")) or 0) >= start_page
        ]

    def appendix_text_pages(self) -> list[dict[str, Any]]:
        appendix_index = self.manifest.get("appendix_index", {})
        coverage = self.manifest.get("coverage", {})
        start_page = None
        if isinstance(appendix_index, dict):
            start_page = _positive_int(appendix_index.get("start_page"))
        if start_page is None and isinstance(coverage, dict):
            start_page = _positive_int(coverage.get("appendix_start_page"))

        pages: list[dict[str, Any]] = []
        seen: set[tuple[int, str, str]] = set()
        for record in self.raw_sections:
            text = str(record.get("text", "")).strip()
            page_start = _positive_int(record.get("page_start"))
            page_end = _positive_int(record.get("page_end")) or page_start
            if not text or page_start is None or page_end is None:
                continue

            is_appendix = _record_has_appendix_hint(record)
            if start_page is not None:
                if page_end < start_page:
                    continue
                page_number = max(page_start, start_page)
            elif is_appendix:
                page_number = page_start
            else:
                continue

            section_id = str(record.get("section_id", "")).strip()
            title = str(record.get("title", "")).strip()
            marker = (page_number, section_id, text)
            if marker in seen:
                continue
            seen.add(marker)
            page = {"page": page_number, "text": text}
            if section_id:
                page["section_id"] = section_id
            if title:
                page["title"] = title
            pages.append(page)
        return pages

    def coverage(self) -> dict[str, Any]:
        return _copy_record(self.manifest.get("coverage"))

    def truncation(self) -> dict[str, Any]:
        coverage = self.coverage()
        text_truncated = bool(
            coverage.get("text_truncated") or coverage.get("truncated_due_to_page_limit")
        )
        return {
            "total_pages": coverage.get("total_pages"),
            "text_max_pages": coverage.get("text_max_pages"),
            "text_pages_extracted": coverage.get("text_pages_extracted"),
            "text_pages_scanned": coverage.get("text_pages_scanned"),
            "text_truncated": text_truncated,
            "truncated_due_to_page_limit": bool(
                coverage.get("truncated_due_to_page_limit") or text_truncated
            ),
            "partial_reading_accepted": False,
        }

    def language_hint(self) -> str:
        return str(self.manifest.get("language_hint", "") or "unknown")

    def math_index(self) -> list[Any]:
        return _copy_list(self.manifest.get("math_index"))

    def text_hash_metadata(self) -> dict[str, Any]:
        return {
            "manifest_text_hash_sha256": str(self.manifest.get("text_hash_sha256", "")),
            "raw_full_text_hash_sha256": _sha256_text(self.full_text()),
            "section_hashes_sha256": {
                str(record.get("section_id", "")): str(record.get("text_hash_sha256", ""))
                for record in self.raw_sections
                if str(record.get("section_id", "")).strip()
            },
        }


def load_source_corpus(source_manifest_path: str | Path) -> SourceCorpus:
    manifest_path = _resolve_manifest_path(source_manifest_path)
    manifest = _load_manifest(manifest_path)
    raw_sections_path = _resolve_raw_sections_path(manifest_path, manifest)
    raw_sections, load_issues = _load_raw_sections(raw_sections_path)
    return SourceCorpus(
        manifest_path=manifest_path,
        manifest=manifest,
        raw_sections_path=raw_sections_path,
        raw_sections=raw_sections,
        load_issues=load_issues,
    )


def _section_location_issue(record: dict[str, Any], *, source: str, index: int) -> dict[str, Any] | None:
    section_id = str(record.get("section_id", "")).strip()
    page_start = _positive_int(record.get("page_start"))
    page_end = _positive_int(record.get("page_end"))
    if not section_id or page_start is None or page_end is None or page_start > page_end:
        return _issue(
            "source_corpus_section_location_invalid",
            message="section record has invalid section id or page range",
            path=f"{source}[{index}]",
            section_id=section_id,
        )
    return None


def _validate_section_locations(corpus: SourceCorpus) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    manifest_sections = _copy_list(corpus.manifest.get("sections"))
    for index, section in enumerate(manifest_sections):
        if not isinstance(section, dict):
            issues.append(
                _issue(
                    "source_corpus_section_location_invalid",
                    message="manifest section must be a JSON object",
                    path=f"sections[{index}]",
                )
            )
            continue
        issue = _section_location_issue(section, source="sections", index=index)
        if issue is not None:
            issues.append(issue)
    for index, record in enumerate(corpus.raw_sections):
        issue = _section_location_issue(record, source="raw_sections", index=index)
        if issue is not None:
            issues.append(issue)
    return issues


def _validate_page_locations(corpus: SourceCorpus) -> list[dict[str, Any]]:
    sections = set(corpus.section_map())
    issues: list[dict[str, Any]] = []
    for index, page in enumerate(_copy_list(corpus.manifest.get("pages"))):
        if not isinstance(page, dict):
            issues.append(
                _issue(
                    "source_corpus_page_location_invalid",
                    message="page record must be a JSON object",
                    path=f"pages[{index}]",
                )
            )
            continue
        page_number = _positive_int(page.get("page"))
        section_ids = page.get("section_ids", [])
        if (
            page_number is None
            or not isinstance(section_ids, list)
            or any(str(section_id) not in sections for section_id in section_ids)
        ):
            issues.append(
                _issue(
                    "source_corpus_page_location_invalid",
                    message="page record has invalid page number or section ids",
                    path=f"pages[{index}]",
                    page=page.get("page"),
                )
            )
    return issues


def _caption_page_values(item: dict[str, Any]) -> list[Any]:
    pages = item.get("pages")
    if isinstance(pages, list) and pages:
        return pages
    if "page" in item:
        return [item.get("page")]
    return []


def _validate_caption_locations(corpus: SourceCorpus) -> list[dict[str, Any]]:
    sections = set(corpus.section_map())
    coverage = corpus.coverage()
    total_pages = _positive_int(coverage.get("total_pages")) if coverage else None
    issues: list[dict[str, Any]] = []
    for index, item in enumerate(corpus.caption_items()):
        pages = _caption_page_values(item)
        valid_pages = [_positive_int(page) for page in pages]
        section_id = str(item.get("section_id", "")).strip()
        page_out_of_range = total_pages is not None and any(
            page is not None and page > total_pages for page in valid_pages
        )
        if (
            not pages
            or any(page is None for page in valid_pages)
            or page_out_of_range
            or (section_id and section_id not in sections)
        ):
            issues.append(
                _issue(
                    "source_corpus_caption_location_invalid",
                    message="caption record has invalid page or section location",
                    path=f"captions[{index}]",
                    caption_id=item.get("id", ""),
                )
            )
    return issues


def _validate_hashes(corpus: SourceCorpus) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    raw_by_section = {
        str(record.get("section_id", "")): record
        for record in corpus.raw_sections
        if str(record.get("section_id", "")).strip()
    }
    for index, record in enumerate(corpus.raw_sections):
        expected_hash = str(record.get("text_hash_sha256", "")).strip()
        if expected_hash and expected_hash != _sha256_text(str(record.get("text", ""))):
            issues.append(
                _issue(
                    "source_corpus_section_hash_mismatch",
                    message="raw section text hash does not match raw section text",
                    path=f"raw_sections[{index}].text_hash_sha256",
                    section_id=record.get("section_id", ""),
                )
            )
    for index, section in enumerate(_copy_list(corpus.manifest.get("sections"))):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id", "")).strip()
        manifest_hash = str(section.get("text_hash_sha256", "")).strip()
        raw_record = raw_by_section.get(section_id)
        if raw_record is None or not manifest_hash:
            continue
        raw_hash = str(raw_record.get("text_hash_sha256", "")).strip()
        if raw_hash and manifest_hash != raw_hash:
            issues.append(
                _issue(
                    "source_corpus_section_hash_mismatch",
                    message="manifest section hash does not match raw section hash",
                    path=f"sections[{index}].text_hash_sha256",
                    section_id=section_id,
                )
            )
    return issues


def validate_source_corpus(corpus: SourceCorpus) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = [dict(issue) for issue in corpus.load_issues]
    if not corpus.full_text():
        issues.append(
            _issue(
                "source_corpus_empty_text",
                message="raw sections do not contain extracted source text",
                path="raw_sections",
            )
        )
    issues.extend(_validate_section_locations(corpus))
    issues.extend(_validate_page_locations(corpus))
    issues.extend(_validate_caption_locations(corpus))
    issues.extend(_validate_hashes(corpus))
    return issues
