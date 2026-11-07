"""Read title and identifier hints from a local PDF."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _identity import (
    candidate_priority_score,
    choose_best_title_match,
    clean_local_pdf_stem,
    extract_arxiv_id,
    extract_doi,
    is_probable_local_pdf_artifact_title,
    normalize_identity_title,
    publication_quality_score,
    title_similarity,
)
from _pdf_text import clean_pdf_line
from common import (
    fitz,
    normalize_whitespace,
)

TITLE_MIN_LETTER_SHARE = 0.6
TITLE_MAX_GARBLE_SHARE = 0.05
TITLE_GARBLE_CHARS = set("!\"#$%*<=>@[\\]^_`{|}~")
TITLE_LINE_SIZE_RATIO = 0.9
TITLE_LINE_SPACING = 1.6
TITLE_FOOTNOTE_MARKS_RE = re.compile(r"[\s*∗†‡§¶]+$")
CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")


def is_mostly_letters(text: str) -> bool:
    """Tell readable words from a garbled text layer, which decodes to stray symbols."""
    visible = [char for char in TITLE_FOOTNOTE_MARKS_RE.sub("", text) if not char.isspace()]
    if not visible:
        return False
    letters = sum(1 for char in visible if char.isalpha())
    garble = sum(1 for char in visible if char in TITLE_GARBLE_CHARS)
    return (
        letters / len(visible) >= TITLE_MIN_LETTER_SHARE
        and garble / len(visible) <= TITLE_MAX_GARBLE_SHARE
    )


def is_plausible_pdf_title_line(line: str) -> bool:
    normalized = clean_pdf_line(line)
    lower = normalized.lower()
    # A Chinese title has no spaces between words, so only its length counts.
    single_word = len(normalized.split()) < 2 and not CJK_CHAR_RE.search(normalized)
    if len(normalized) < 8 or (len(normalized) < 20 and single_word):
        return False
    if not is_mostly_letters(normalized):
        return False
    if normalized.count(",") >= 3:
        return False
    if any(token in lower for token in ["doi.org/", "http://", "https://", "www.", "check for updates"]):
        return False
    if lower in {"abstract", "article", "preprint"}:
        return False
    if lower.startswith("npj |") or lower.startswith("arxiv:") or lower.startswith("submitted to"):
        return False
    if any(re.search(pattern, lower) for pattern in LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS):
        return False
    if " doi:" in lower or lower.startswith("doi:"):
        return False
    return True


def join_title_lines(lines: list[str]) -> str:
    title = ""
    for line in lines:
        if not title:
            title = line
        elif title.endswith("-") and line[:1].islower():
            title = title[:-1] + line
        elif CJK_CHAR_RE.match(title[-1]) and CJK_CHAR_RE.match(line[0]):
            title += line
        else:
            title = f"{title} {line}"
    return TITLE_FOOTNOTE_MARKS_RE.sub("", title)


def first_page_title_from_layout(page: Any) -> str:
    """Return the first page's title: its largest plausible line plus the adjacent lines set
    in the same type, so a journal name or volume line printed above it is passed over."""
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return ""
    lines = []
    for block in blocks:
        for line in block.get("lines", []):
            if tuple(line.get("dir", (1.0, 0.0))) != (1.0, 0.0):
                continue
            spans = line.get("spans", [])
            text = clean_pdf_line("".join(str(span.get("text", "")) for span in spans))
            if text:
                sizes = [
                    float(span.get("size", 0))
                    for span in spans
                    if str(span.get("text", "")).strip()
                ]
                size = max(sizes)
                lines.append({"text": text, "size": size, "top": float(line["bbox"][1])})
    candidates = [line for line in lines if is_plausible_pdf_title_line(line["text"])]
    if not candidates:
        return ""
    anchor = max(candidates, key=lambda line: (line["size"], -line["top"]))
    ordered = sorted(lines, key=lambda line: line["top"])
    start = end = ordered.index(anchor)

    def continues_title(edge: dict, neighbour: dict) -> bool:
        return (
            neighbour["size"] >= anchor["size"] * TITLE_LINE_SIZE_RATIO
            and abs(neighbour["top"] - edge["top"]) <= anchor["size"] * TITLE_LINE_SPACING
            and is_mostly_letters(neighbour["text"])
        )

    while start > 0 and continues_title(ordered[start], ordered[start - 1]):
        start -= 1
    while end + 1 < len(ordered) and continues_title(ordered[end], ordered[end + 1]):
        end += 1
    return join_title_lines([line["text"] for line in ordered[start : end + 1]])


def first_page_title_candidate(first_page_text: str) -> str:
    for raw_line in (first_page_text or "").splitlines():
        if is_plausible_pdf_title_line(raw_line):
            return clean_pdf_line(raw_line)
    return ""


def extract_local_pdf_hints(pdf_path: Path) -> dict[str, Any]:
    raw_title = normalize_whitespace(pdf_path.stem.replace("_", " "))
    cleaned_title = clean_local_pdf_stem(pdf_path.stem)
    hints: dict[str, Any] = {
        "title": cleaned_title or raw_title,
        "local_pdf_title_source": "local_pdf_stem_used",
    }
    if is_probable_local_pdf_artifact_title(raw_title):
        hints["local_pdf_artifact_title"] = True
    if fitz is None:
        return hints

    metadata_title = ""
    metadata_subject = ""
    first_page_text = ""
    layout_title = ""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return hints
    try:
        metadata = doc.metadata or {}
        metadata_title = normalize_whitespace(str(metadata.get("title", "")))
        metadata_subject = normalize_whitespace(str(metadata.get("subject", "")))
        if len(doc):
            first_page_text = doc[0].get_text("text")
            layout_title = first_page_title_from_layout(doc[0])
    except Exception:
        return hints
    finally:
        doc.close()

    if metadata_title:
        hints["title"] = metadata_title
        hints["local_pdf_title_source"] = "pdf_metadata_title_used"
        # Tools that write the metadata can drop part of the printed title, such as a
        # venue's "Position:" lead-in, so identity resolution also sees the printed one.
        if layout_title and normalize_identity_title(layout_title) != normalize_identity_title(
            metadata_title
        ):
            hints["local_pdf_first_page_title"] = layout_title
    else:
        page_title = layout_title or first_page_title_candidate(first_page_text)
        if page_title:
            hints["title"] = page_title
            hints["local_pdf_title_source"] = "first_page_title_used"

    searchable = "\n".join(part for part in [metadata_subject, metadata_title, first_page_text] if part)
    doi = extract_doi(searchable)
    if doi:
        hints["doi"] = doi
    arxiv_id = extract_arxiv_id(searchable)
    if arxiv_id:
        hints["arxiv_id"] = arxiv_id

    return hints


def choose_local_pdf_corrected_title(base: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    current_title = normalize_whitespace(str(base.get("title", "")))
    if not current_title:
        return ""
    titled_candidates = [candidate for candidate in candidates if normalize_whitespace(str(candidate.get("title", "")))]
    if local_pdf_title_needs_identity_correction(base):
        identity_matches = [
            candidate for candidate in titled_candidates if external_identity_matches(base, candidate)
        ]
        if identity_matches:
            best_identity = sorted(
                identity_matches,
                key=lambda item: (
                    candidate_priority_score(item),
                    publication_quality_score(item),
                    len(normalize_whitespace(str(item.get("title", "")))),
                ),
                reverse=True,
            )[0]
            return normalize_whitespace(str(best_identity.get("title", "")))

    if not is_probable_local_pdf_artifact_title(current_title):
        return ""
    best = choose_best_title_match(current_title, titled_candidates)
    if not best:
        return ""
    candidate_title = normalize_whitespace(str(best.get("title", "")))
    if not candidate_title:
        return ""
    if title_similarity(current_title, candidate_title) < 0.55:
        return ""
    if not (best.get("doi") or best.get("arxiv_id") or publication_quality_score(best) >= 2):
        return ""
    return candidate_title


LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS = (
    r"^(?:research|original|review)\s+article$",
    r"^provided proper attribution\b",
    r"^published as\b",
    r"^submitted to\b",
    r"^accepted (?:as|to|for)\b",
    r"^conference paper\b",
    r"^proceedings of\b",
    r"^arxiv\s*:",
    r"^doi\s*:",
)


def local_pdf_title_needs_identity_correction(base: dict[str, Any]) -> bool:
    title = normalize_whitespace(str(base.get("title", "")))
    if not title:
        return False
    if base.get("local_pdf_artifact_title") or is_probable_local_pdf_artifact_title(title):
        return True
    source = normalize_whitespace(str(base.get("local_pdf_title_source", "")))
    if source not in {"first_page_title_used", "local_pdf_stem_used", "pdf_metadata_title_used"}:
        return False
    lowered = title.lower()
    return any(re.search(pattern, lowered) for pattern in LOW_CONFIDENCE_LOCAL_TITLE_PATTERNS)


def external_identity_matches(base: dict[str, Any], candidate: dict[str, Any]) -> bool:
    base_doi = extract_doi(str(base.get("doi", ""))) or ""
    candidate_doi = extract_doi(str(candidate.get("doi", ""))) or ""
    if base_doi and candidate_doi and base_doi.lower() == candidate_doi.lower():
        return True
    base_arxiv = normalize_whitespace(str(base.get("arxiv_id", "")))
    candidate_arxiv = normalize_whitespace(str(candidate.get("arxiv_id", "")))
    return bool(base_arxiv and candidate_arxiv and base_arxiv == candidate_arxiv)
