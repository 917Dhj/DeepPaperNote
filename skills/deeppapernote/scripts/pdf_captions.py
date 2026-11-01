#!/usr/bin/env python3
"""Locate figure and table captions from the PDF text layout."""

from __future__ import annotations

import re
from collections import Counter

from common import (
    caption_label_key,
    clean_pdf_line,
    fitz,
    normalize_caption_label,
    normalize_whitespace,
)

CAPTION_RE = re.compile(
    r"^((?:"
    r"supplementary\s+(?:fig(?:ure)?|table)\.?\s*\d+[a-z]?"
    r"|extended\s+data\s+(?:fig(?:ure)?|table)\.?\s*\d+[a-z]?"
    r"|scheme\.?\s*\d+[a-z]?"
    r"|algorithm\.?\s*\d+[a-z]?"
    r"|(?:fig(?:ure)?|table)\.?\s*[AS]?\d+[a-z]?"
    r"|[图表]\.?\s*[A-Z]?\d+[a-z]?"
    r"))(?!\.\d)(?=$|[\s:：.。,\、|—–-])",
    re.IGNORECASE,
)
CAPTION_SEPARATORS = ":：.。|—–-"
CJK_RE = re.compile(r"[　-〿㐀-鿿＀-￯]")
CAPTION_SENTENCE_ENDS = (".", "?", "!", "。", "？", "！")

# Used to decide whether a continuation line still belongs to the caption text
# or has already entered the data body of a table.  A row of pure tabular data
# usually contains many short numeric tokens separated by spaces, e.g.
# "0.283  0.321  0.236  0.282".  When such a row appears immediately after the
# caption start, we must NOT merge it into the caption bbox; otherwise the
# downstream "table body lives below caption" cropping logic will mistake the
# numeric row for caption text and shrink the table bbox accordingly.
MAX_CAPTION_CONTINUATIONS = 3
# A sentence cut before its label ends on one of these words, as in "shown in\nFig. 2a."
WRAPPED_REFERENCE_LEAD_RE = re.compile(
    r"\b(?:and|as|by|data|from|in|of|or|see|supplementary|the|to|with)\s*[(\[]?$",
    re.IGNORECASE,
)
MIN_CAPTION_COLUMN_CHARS = 20
_NUMERIC_TOKEN_RE = re.compile(r"^[+-]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


def looks_like_data_row(text: str) -> bool:
    """Heuristic: a data row from a tabular layout, not part of a caption."""
    tokens = text.split()
    if len(tokens) < 3:
        return False
    numeric_tokens = sum(1 for tok in tokens if _NUMERIC_TOKEN_RE.match(tok))
    return numeric_tokens >= max(2, len(tokens) // 2)


def classify_caption_kind(label: str) -> str:
    """Return 'table' if the caption label starts with 'Table', else 'figure'."""
    return (
        "table"
        if re.match(
            r"^(?:(?:(?:supplementary|extended\s+data)\s+)?table\b|表)",
            label.strip(),
            re.IGNORECASE,
        )
        else "figure"
    )


def caption_match_is_inline_reference(line_text: str, match: re.Match[str]) -> bool:
    """Reject prose references such as "Table 8 summarizes ..."."""
    tail = line_text[match.end():]
    if not tail or not tail[0].isspace():
        return False
    rest = tail.strip()
    if not rest:
        return False
    first_word = re.match(r"[A-Za-z]+", rest)
    return bool(first_word and first_word.group(0)[0].islower())


def line_is_wrapped_reference(previous_line: str | None) -> bool:
    return bool(previous_line and WRAPPED_REFERENCE_LEAD_RE.search(previous_line.rstrip()))


def caption_strength(line_text: str, match: re.Match[str], *, block_start: bool) -> int:
    """Score how much a label line looks like a caption rather than wrapped prose.

    A separator alone cannot tell "Figure 4. Training curves" from a sentence
    ending at "Fig. 4." that happens to wrap to the line start, so the line's
    position in its text block counts as well.
    """
    rest = line_text[match.end():].strip()
    if not rest:
        separator = 1
    elif rest[0] in CAPTION_SEPARATORS:
        body = rest.lstrip(CAPTION_SEPARATORS + " ")
        separator = 0 if body[:1].islower() else 2
    else:
        separator = 1 if rest[0].isupper() or CJK_RE.match(rest[0]) else 0
    return separator + int(block_start)


def join_caption_lines(lines: list[str]) -> str:
    joined = lines[0]
    for line in lines[1:]:
        if re.search(r"[a-z]-$", joined) and line[0].islower():
            joined = joined[:-1] + line
        elif CJK_RE.match(joined[-1]) and CJK_RE.match(line[0]):
            joined += line
        else:
            joined = f"{joined} {line}"
    return joined


def font_sizes(blocks: list[dict]) -> Counter:
    """Count the characters set at each font size, rounded to absorb small jitter."""
    sizes: Counter = Counter()
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                sizes[round(span["size"], 1)] += len(span.get("text", "").strip())
    return sizes


def dominant_font_size(blocks: list[dict]) -> float:
    sizes = font_sizes(blocks)
    return sizes.most_common(1)[0][0] if sizes else 0.0


def block_lines(block: dict) -> list[str]:
    lines = ("".join(s.get("text", "") for s in line.get("spans", [])) for line in block["lines"])
    return [text for text in (line.strip() for line in lines) if text]


def block_continues_caption(
    block: dict,
    caption_bbox: tuple[float, float, float, float],
    tail_bbox: tuple[float, float, float, float],
    text: str,
    size: float,
    body_size: float,
) -> bool:
    """Tell whether a text block carries on a caption cut by a layout break.

    Text set smaller than the page body in the next column, level with the
    caption, can only be the caption. Elsewhere a block must follow directly
    and read as the rest of an unfinished sentence, which keeps table headers
    and body paragraphs out.
    """
    lines = block_lines(block)
    if (
        not lines
        or abs(dominant_font_size([block]) - size) > 0.3
        or CAPTION_RE.match(lines[0])
        or looks_like_data_row(lines[0])
    ):
        return False
    x0, y0, x1, _ = block["bbox"]
    small = size <= body_size - 0.5
    unfinished = not (text.endswith(CAPTION_SENTENCE_ENDS) or CJK_RE.match(text[-1]))
    lowercase = lines[0][0].islower()
    if (
        x0 >= caption_bbox[2] - 2.0
        and abs(y0 - caption_bbox[1]) <= 3.0
        and x1 - x0 <= (caption_bbox[2] - caption_bbox[0]) * 1.15
        and sum(map(len, lines)) >= MIN_CAPTION_COLUMN_CHARS
    ):
        return small or (unfinished and lowercase)
    follows = tail_bbox[1] < y0 and y0 - tail_bbox[3] <= size * 1.6
    overlaps = x0 < tail_bbox[2] and x1 > tail_bbox[0]
    return follows and overlaps and unfinished and (lowercase or small)


def extend_caption_across_blocks(anchor: dict, block: dict, blocks: list[dict]) -> None:
    """Append the text blocks a caption runs into when its own block ends."""
    size = dominant_font_size([block])
    body_size = dominant_font_size(blocks)
    caption_bbox = anchor["bbox"]
    tail_bbox = caption_bbox
    parts = [anchor["line_text"]]
    for _ in range(MAX_CAPTION_CONTINUATIONS):
        following = next(
            (
                candidate
                for candidate in blocks
                if candidate is not block
                and block_continues_caption(
                    candidate, caption_bbox, tail_bbox, parts[-1], size, body_size
                )
            ),
            None,
        )
        if following is None:
            break
        block = following
        tail_bbox = tuple(following["bbox"])
        parts.append(join_caption_lines(block_lines(following)))
        if tail_bbox[0] < caption_bbox[2]:
            x0, y0, x1, y1 = anchor["bbox"]
            anchor["bbox"] = (
                min(x0, tail_bbox[0]),
                y0,
                max(x1, tail_bbox[2]),
                max(y1, tail_bbox[3]),
            )
    anchor["line_text"] = join_caption_lines(parts)


def find_caption_blocks(page) -> list[dict]:
    """Return caption anchors sorted top-to-bottom by their y0 coordinate.

    Each anchor contains the full multi-line caption bbox so that the
    downstream crop includes the entire caption text, not just the first line.

    Each anchor::

        {
            "label": "Figure 3",
            "kind": "figure" | "table",
            "bbox": (x0, y0, x1, y1),
            "line_text": ...,
            "strength": 3,
        }
    """
    anchors: list[dict] = []
    blocks = [
        block
        for block in page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        if block.get("type") == 0
    ]
    for block in blocks:
        lines = block.get("lines", [])
        line_texts = ["".join(s.get("text", "") for s in line.get("spans", [])) for line in lines]
        for line_idx, line in enumerate(lines):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = line_texts[line_idx].strip()
            match = CAPTION_RE.match(line_text)
            if (
                not match
                or caption_match_is_inline_reference(line_text, match)
                or line_is_wrapped_reference(line_texts[line_idx - 1] if line_idx else None)
            ):
                continue
            label = normalize_whitespace(match.group(1))
            kind = classify_caption_kind(label)

            caption_lines_text = [line_text]
            first_bbox = line["bbox"]
            x0, y0, x1, y1 = first_bbox
            prev_line_bottom = first_bbox[3]
            line_height = max(first_bbox[3] - first_bbox[1], 6.0)

            for cont_line in lines[line_idx + 1:]:
                cont_spans = cont_line.get("spans", [])
                if not cont_spans:
                    break
                cont_text = "".join(s.get("text", "") for s in cont_spans).strip()
                if not cont_text:
                    break
                if CAPTION_RE.match(cont_text) and not line_is_wrapped_reference(
                    caption_lines_text[-1]
                ):
                    break
                if looks_like_data_row(cont_text):
                    break
                cb = cont_line["bbox"]
                # Stop merging if the next line is too far below the previous one
                # (it is then a separate paragraph, not a caption continuation).
                if cb[1] - prev_line_bottom > line_height * 1.6:
                    break
                x0 = min(x0, cb[0])
                y1 = max(y1, cb[3])
                x1 = max(x1, cb[2])
                prev_line_bottom = cb[3]
                caption_lines_text.append(cont_text)

            anchor = {
                "label": label,
                "kind": kind,
                "bbox": (x0, y0, x1, y1),
                "label_bbox": tuple(first_bbox),
                "line_text": join_caption_lines(caption_lines_text),
                "strength": caption_strength(line_text, match, block_start=line_idx == 0),
            }
            if line_idx + len(caption_lines_text) == len(lines):
                extend_caption_across_blocks(anchor, block, blocks)
            anchors.append(anchor)
    anchors.sort(key=lambda a: a["bbox"][1])
    return anchors


def select_caption_blocks(doc) -> dict[int, list[dict]]:
    """Return each 1-based page's anchors, dropping those weaker than their label's best.

    The whole document is compared because a reference can precede its caption
    by a page. Equally strong anchors all remain, which keeps continued tables.
    """
    pages = {index + 1: find_caption_blocks(doc[index]) for index in range(len(doc))}
    strongest: dict[str, int] = {}
    for anchors in pages.values():
        for anchor in anchors:
            key = caption_label_key(anchor["label"])
            strongest[key] = max(strongest.get(key, 0), anchor["strength"])
    return {
        page: [
            anchor
            for anchor in anchors
            if anchor["strength"] == strongest[caption_label_key(anchor["label"])]
        ]
        for page, anchors in pages.items()
    }


def caption_item(anchor: dict) -> dict[str, str]:
    """Return an anchor as a Source Manifest id and caption, without the label."""
    text = clean_pdf_line(anchor["line_text"])
    match = CAPTION_RE.match(text)
    return {
        "id": normalize_caption_label(anchor["label"]),
        "caption": text[match.end():].lstrip(CAPTION_SEPARATORS + ",、 ") if match else "",
    }
