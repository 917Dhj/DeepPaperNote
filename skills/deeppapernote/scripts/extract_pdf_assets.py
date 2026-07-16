#!/usr/bin/env python3
"""Extract page-level PDF assets for later model-side semantic figure matching.

Two extraction strategies run in parallel:
1. xref-level: extract raw embedded image objects (legacy behaviour).
2. figure-level: locate Figure/Table captions on each page, compute a bounding
   box that covers the visual content above the caption, and render that region
   from the page pixmap at high DPI.  This produces complete, human-readable
   figures even when the PDF stores them as many small xref fragments or as
   pure vector art.

Downstream consumers (plan_figures.py, materialize_figure_asset.py) should
prefer figure-level assets when available.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

from common import default_assets_dir, emit, enrich_metadata, fitz, maybe_load_json_record, normalize_whitespace, resolve_reference

try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    Image = None

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover
    pytesseract = None

FIGURE_RENDER_DPI = 200
MIN_FIGURE_HEIGHT_PT = 60
MIN_FIGURE_WIDTH_PT = 100

CAPTION_RE = re.compile(
    r"^((?:"
    r"supplementary\s+(?:fig(?:ure)?|table)\.?\s*\d+[a-z]?"
    r"|extended\s+data\s+(?:fig(?:ure)?|table)\.?\s*\d+[a-z]?"
    r"|scheme\.?\s*\d+[a-z]?"
    r"|algorithm\.?\s*\d+[a-z]?"
    r"|(?:fig(?:ure)?|table)\.?\s*[AS]?\d+[a-z]?"
    r"))(?!\.\d)(?=$|[\s:：.。,\、|—–-])",
    re.IGNORECASE,
)

# Used to decide whether a continuation line still belongs to the caption text
# or has already entered the data body of a table.  A row of pure tabular data
# usually contains many short numeric tokens separated by spaces, e.g.
# "0.283  0.321  0.236  0.282".  When such a row appears immediately after the
# caption start, we must NOT merge it into the caption bbox; otherwise the
# downstream "table body lives below caption" cropping logic will mistake the
# numeric row for caption text and shrink the table bbox accordingly.
_NUMERIC_TOKEN_RE = re.compile(r"^[+-]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
_TEXT_TABLE_SEPARATOR_RE = re.compile(r"(?:\t+|\s{2,}|[|;])")
_TEXT_TABLE_PROSE_STARTERS = {
    "a",
    "an",
    "it",
    "our",
    "that",
    "the",
    "these",
    "this",
    "those",
    "we",
}
_TEXT_TABLE_PROSE_CONNECTORS = {
    "although",
    "because",
    "therefore",
    "whereas",
    "which",
}


def _looks_like_data_row(text: str) -> bool:
    """Heuristic: a data row from a tabular layout, not part of a caption."""
    tokens = text.split()
    if len(tokens) < 3:
        return False
    numeric_tokens = sum(1 for tok in tokens if _NUMERIC_TOKEN_RE.match(tok))
    return numeric_tokens >= max(2, len(tokens) // 2)


def _looks_like_text_table_row(text: str) -> bool:
    """Heuristic: a short textual row from a comparison/categorization table."""
    raw = text.strip()
    cleaned = normalize_whitespace(raw)
    tokens = cleaned.split()
    if len(tokens) < 3 or len(cleaned) > 180:
        return False

    cells = [cell.strip() for cell in _TEXT_TABLE_SEPARATOR_RE.split(raw) if cell.strip()]
    if len(cells) >= 3 and all(len(cell.split()) <= 8 for cell in cells):
        return True

    normalized_tokens = [tok.strip(".,:()[]{}").lower() for tok in tokens]
    if cleaned.endswith((".", "?", "!")):
        return False
    if normalized_tokens[0] in _TEXT_TABLE_PROSE_STARTERS:
        return False
    if any(tok in _TEXT_TABLE_PROSE_CONNECTORS for tok in normalized_tokens):
        return False

    average_token_length = sum(len(tok.strip(".,:()[]{}")) for tok in tokens) / len(tokens)
    long_tokens = sum(1 for tok in tokens if len(tok.strip(".,:()[]{}")) > 18)
    return len(tokens) <= 8 and average_token_length <= 9.0 and long_tokens <= 1


def _rect_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return _rect_area((x0, y0, x1, y1))


def _rects_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    return _intersection_area(a, b) > 0


def _classify_visual_quality(
    *,
    kind: str,
    page_coverage_ratio: float,
    visual_rect_count: int,
    visual_body_ratio: float,
    paragraph_text_chars: int,
    table_body_rows: int,
    caption_text_chars: int,
    other_caption_labels: list[str] | None = None,
) -> dict:
    """Classify whether a caption-matched crop is visually usable.

    This is intentionally conservative. A label/caption match proves identity,
    but not that the rendered crop contains the figure or table body.
    """
    normalized_kind = kind.strip().lower()
    other_caption_labels = list(other_caption_labels or [])
    reasons: list[str] = []

    if normalized_kind == "table":
        text_per_table_row = paragraph_text_chars / max(1, table_body_rows)
        if table_body_rows <= 0:
            reasons.append("table_body_missing")
        if table_body_rows <= 1 and visual_body_ratio < 0.03 and caption_text_chars >= 40:
            reasons.append("caption_only_suspected")
        # Dense tables naturally contain many text spans. Treat prose-like text
        # as contamination when table structure is weak or the text density is
        # far higher than the detected table body can explain.
        if paragraph_text_chars >= 450 and (
            table_body_rows <= 2
            or (paragraph_text_chars >= 900 and visual_body_ratio <= 0.03 and text_per_table_row > 90)
            or text_per_table_row > 140
        ):
            reasons.append("table_text_contamination_suspected")
        if other_caption_labels:
            reasons.append("multiple_caption_regions_suspected")
        status = "reject" if reasons else "usable"
    else:
        if other_caption_labels:
            reasons.append("multiple_caption_regions_suspected")
        visual_dominant = visual_rect_count >= 3 and visual_body_ratio >= 0.18
        if paragraph_text_chars >= 450 and not visual_dominant:
            reasons.append("large_text_block_suspected")
        if page_coverage_ratio >= 0.70 and paragraph_text_chars >= 250:
            reasons.append("oversized_page_crop")
        if visual_rect_count <= 1 and visual_body_ratio < 0.03:
            reasons.append("low_visual_body_ratio")
        if any(
            code in reasons
            for code in (
                "multiple_caption_regions_suspected",
                "large_text_block_suspected",
                "oversized_page_crop",
                "low_visual_body_ratio",
            )
        ):
            status = "reject"
        elif visual_rect_count == 0 or visual_body_ratio < 0.08:
            if "low_visual_body_ratio" not in reasons:
                reasons.append("low_visual_body_ratio")
            status = "review"
        else:
            status = "usable"

    return {
        "visual_quality_status": status,
        "quality_reason_codes": reasons,
        "page_coverage_ratio": round(page_coverage_ratio, 6),
        "visual_rect_count": int(visual_rect_count),
        "visual_body_ratio": round(visual_body_ratio, 6),
        "paragraph_text_chars": int(paragraph_text_chars),
        "table_body_rows": int(table_body_rows),
        "caption_text_chars": int(caption_text_chars),
        "other_caption_count": len(other_caption_labels),
        "other_caption_labels": other_caption_labels,
    }


def _classify_caption_kind(label: str) -> str:
    """Return 'table' if the caption label starts with 'Table', else 'figure'."""
    return (
        "table"
        if re.match(r"^(?:(?:supplementary|extended\s+data)\s+)?table\b", label.strip(), re.IGNORECASE)
        else "figure"
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract pdf assets")
    p.add_argument("--input", required=True, help="Fetch JSON path, metadata JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--assets-dir", default="", help="Optional explicit assets directory.")
    p.add_argument("--max-pages", type=int, default=40, help="Maximum pages to scan.")
    p.add_argument("--min-searchable-chars", type=int, default=100, help="Minimum characters for a page to count as searchable text.")
    p.add_argument("--ocr-dpi", type=int, default=300, help="DPI used when OCR fallback is needed.")
    p.add_argument("--figure-dpi", type=int, default=FIGURE_RENDER_DPI, help="DPI for figure-level page rendering.")
    return p


def ensure_record(input_value: str) -> dict:
    record = maybe_load_json_record(input_value)
    if record is not None:
        return dict(record)
    return enrich_metadata(resolve_reference(input_value))


def save_image_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def ocr_page(page, dpi: int) -> str:
    if fitz is None or pytesseract is None or Image is None:
        return ""
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return normalize_whitespace(pytesseract.image_to_string(image))


def extract_page_images(doc, page, page_number: int, images_dir: Path) -> list[dict]:
    """Legacy xref-level extraction."""
    assets: list[dict] = []
    seen_xrefs = set()
    for image_index, image_info in enumerate(page.get_images(full=True), start=1):
        if not image_info:
            continue
        xref = int(image_info[0])
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        extracted = doc.extract_image(xref)
        image_bytes = extracted.get("image")
        if not image_bytes:
            continue
        ext = normalize_whitespace(str(extracted.get("ext", "png"))).lower() or "png"
        filename = f"page_{page_number:03d}_img_{image_index:02d}.{ext}"
        output_path = images_dir / filename
        save_image_bytes(output_path, image_bytes)
        assets.append(
            {
                "page_number": page_number,
                "image_index": image_index,
                "xref": xref,
                "filename": filename,
                "path": str(output_path),
                "ext": ext,
                "width": extracted.get("width", 0),
                "height": extracted.get("height", 0),
                "colorspace": extracted.get("colorspace", 0),
                "size_bytes": len(image_bytes),
                "extraction_level": "xref",
            }
        )
    return assets


# ---------------------------------------------------------------------------
# Figure-level extraction: caption-anchored page-render cropping
# ---------------------------------------------------------------------------

def _find_caption_blocks(page) -> list[dict]:
    """Return caption anchors sorted top-to-bottom by their y0 coordinate.

    Each anchor contains the full multi-line caption bbox so that the
    downstream crop includes the entire caption text, not just the first line.

    Each anchor::

        {
            "label": "Figure 3",
            "kind": "figure" | "table",
            "bbox": (x0, y0, x1, y1),
            "line_text": ...,
        }
    """
    anchors: list[dict] = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        lines = block.get("lines", [])
        for line_idx, line in enumerate(lines):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(s.get("text", "") for s in spans).strip()
            match = CAPTION_RE.match(line_text)
            if not match or _caption_match_is_inline_reference(line_text, match):
                continue
            label = normalize_whitespace(match.group(1))
            kind = _classify_caption_kind(label)

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
                if CAPTION_RE.match(cont_text):
                    break
                if _looks_like_data_row(cont_text):
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

            full_caption = " ".join(caption_lines_text)
            anchors.append({
                "label": label,
                "kind": kind,
                "bbox": (x0, y0, x1, y1),
                "label_bbox": tuple(first_bbox),
                "line_text": full_caption,
            })
    anchors.sort(key=lambda a: a["bbox"][1])
    return anchors


def _caption_match_is_inline_reference(line_text: str, match: re.Match[str]) -> bool:
    """Reject prose references such as "Table 8 summarizes ..."."""
    tail = line_text[match.end():]
    if not tail or not tail[0].isspace():
        return False
    rest = tail.strip()
    if not rest:
        return False
    first_word = re.match(r"[A-Za-z]+", rest)
    return bool(first_word and first_word.group(0)[0].islower())


def _collect_xref_rects(page) -> list[tuple[float, float, float, float]]:
    """Gather the page-level bounding boxes of all embedded images."""
    rects: list[tuple[float, float, float, float]] = []
    for img_info in page.get_images(full=True):
        xref = int(img_info[0])
        try:
            img_rects = page.get_image_rects(xref)
        except Exception:
            continue
        for r in img_rects:
            if r.is_empty or r.is_infinite:
                continue
            rects.append((r.x0, r.y0, r.x1, r.y1))
    return rects


def _collect_drawing_rects(page) -> list[tuple[float, float, float, float]]:
    """Gather bounding boxes of vector drawings on the page."""
    rects: list[tuple[float, float, float, float]] = []
    try:
        for drawing in page.get_drawings():
            r = drawing.get("rect")
            if r is None:
                continue
            rect = fitz.Rect(r)
            if rect.is_empty or rect.is_infinite:
                continue
            if rect.width < 10 or rect.height < 10:
                continue
            rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
    except Exception:
        pass
    return rects


def _visual_signal_for_bbox(page, bbox: tuple[float, float, float, float]) -> tuple[int, float]:
    """Return visual rect count and visual-area ratio inside a crop."""
    crop_area = _rect_area(bbox)
    if crop_area <= 0:
        return 0, 0.0
    rects = _collect_xref_rects(page) + _collect_drawing_rects(page)
    count = 0
    visual_area = 0.0
    for rect in rects:
        area = _intersection_area(rect, bbox)
        if area <= 0:
            continue
        count += 1
        visual_area += area
    return count, min(1.0, visual_area / crop_area)


def _find_body_text_blocks(page) -> list[tuple[float, float, float, float, str]]:
    """Return bounding boxes of body-text blocks (non-caption) sorted top-to-bottom."""
    results: list[tuple[float, float, float, float, str]] = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        full_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                full_text += span.get("text", "")
        full_text = full_text.strip()
        if len(full_text) < 40:
            continue
        if CAPTION_RE.match(full_text):
            continue
        bb = block["bbox"]
        results.append((bb[0], bb[1], bb[2], bb[3], full_text))
    results.sort(key=lambda b: b[1])
    return results


def _find_paragraph_blocks(page, *, min_chars: int = 200) -> list[tuple[float, float, float, float, str]]:
    """Return only large prose blocks that look like running paragraphs.

    PyMuPDF often groups an entire tabular column ("DS-Ulysses 629.9 418.3 ...")
    into a single text block, so the legacy ``_find_body_text_blocks`` filter
    catches table cells too aggressively.  For deciding whether we have walked
    out of a table region we want a stricter notion: only blocks whose total
    text mass and line count look like real prose count as paragraph blocks.
    """
    results: list[tuple[float, float, float, float, str]] = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        lines = block.get("lines", [])
        full_text = ""
        for line in lines:
            for span in line.get("spans", []):
                full_text += span.get("text", "")
        full_text = full_text.strip()
        if len(full_text) < min_chars:
            continue
        if CAPTION_RE.match(full_text):
            continue
        # Real prose paragraphs have many lines and few numeric-heavy lines.
        if len(lines) < 3:
            continue
        numeric_line_share = 0
        for line in lines:
            line_text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if _looks_like_data_row(line_text):
                numeric_line_share += 1
        if numeric_line_share > len(lines) * 0.4:
            continue
        bb = block["bbox"]
        results.append((bb[0], bb[1], bb[2], bb[3], full_text))
    results.sort(key=lambda b: b[1])
    return results


def _count_paragraph_text_chars_in_bbox(
    page,
    bbox: tuple[float, float, float, float],
    caption_bbox: tuple[float, float, float, float],
) -> int:
    """Count prose-like text intersecting a crop, excluding the caption area."""
    chars = 0
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        bb = tuple(block["bbox"])
        if not _rects_intersect(bb, bbox):
            continue
        if _intersection_area(bb, caption_bbox) / max(_rect_area(bb), 1.0) > 0.6:
            continue

        lines = block.get("lines", [])
        line_texts = [
            "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            for line in lines
        ]
        line_texts = [text for text in line_texts if text]
        full_text = normalize_whitespace(" ".join(line_texts))
        if len(full_text) < 80:
            continue
        if CAPTION_RE.match(full_text):
            continue
        numeric_rows = sum(1 for text in line_texts if _looks_like_data_row(text))
        if line_texts and numeric_rows > len(line_texts) * 0.4:
            continue
        chars += len(full_text)
    return chars


def _other_caption_labels_for_crop(
    caption_anchors: list[dict],
    current_anchor: dict,
    bbox: tuple[float, float, float, float],
) -> list[str]:
    """Return other caption labels substantially covered by this crop."""
    labels: list[str] = []
    current_label = normalize_whitespace(str(current_anchor.get("label", "")))
    current_bbox = tuple(current_anchor.get("bbox", ()))

    for anchor in caption_anchors:
        label = normalize_whitespace(str(anchor.get("label", "")))
        anchor_bbox = tuple(anchor.get("bbox", ()))
        label_bbox = tuple(anchor.get("label_bbox", anchor_bbox))
        if not label or len(anchor_bbox) != 4:
            continue
        if label == current_label and anchor_bbox == current_bbox:
            continue

        overlap = _intersection_area(anchor_bbox, bbox)
        label_overlap = _intersection_area(label_bbox, bbox) if len(label_bbox) == 4 else 0.0
        if overlap <= 0 and label_overlap <= 0:
            continue
        caption_overlap_ratio = overlap / max(_rect_area(anchor_bbox), 1.0)
        label_overlap_ratio = label_overlap / max(_rect_area(label_bbox), 1.0) if len(label_bbox) == 4 else 0.0
        if caption_overlap_ratio < 0.5 and label_overlap_ratio < 0.15:
            continue
        labels.append(label)

    return sorted(set(labels))


def _quality_signals_for_crop(
    page,
    kind: str,
    bbox: tuple[float, float, float, float],
    caption_anchor: dict,
    page_rect,
    *,
    table_body_rows: int,
    caption_anchors: list[dict] | None = None,
) -> dict:
    page_area = _rect_area((page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1))
    page_coverage_ratio = _rect_area(bbox) / page_area if page_area > 0 else 0.0
    visual_rect_count, visual_body_ratio = _visual_signal_for_bbox(page, bbox)
    caption_bbox = tuple(caption_anchor["bbox"])
    paragraph_text_chars = _count_paragraph_text_chars_in_bbox(page, bbox, caption_bbox)
    caption_text_chars = len(normalize_whitespace(str(caption_anchor.get("line_text", ""))))
    other_caption_labels = _other_caption_labels_for_crop(caption_anchors or [], caption_anchor, bbox)
    return _classify_visual_quality(
        kind=kind,
        page_coverage_ratio=page_coverage_ratio,
        visual_rect_count=visual_rect_count,
        visual_body_ratio=visual_body_ratio,
        paragraph_text_chars=paragraph_text_chars,
        table_body_rows=table_body_rows,
        caption_text_chars=caption_text_chars,
        other_caption_labels=other_caption_labels,
    )


def _clip_to_page(
    bbox: tuple[float, float, float, float],
    page_rect,
    *,
    padding: float = 4.0,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    x0 = max(page_rect.x0, x0 - padding)
    y0 = max(page_rect.y0, y0 - padding)
    x1 = min(page_rect.x1, x1 + padding)
    y1 = min(page_rect.y1, y1 + padding)
    return (x0, y0, x1, y1)


def _estimate_figure_bbox_above_caption(
    page,
    caption_anchor: dict,
    prev_anchor: dict | None,
    page_rect,
) -> tuple[float, float, float, float] | None:
    """Estimate the bounding box of the figure that lives ABOVE its caption.

    Strategy:
    1. Collect all xref image rects and vector drawing rects on the page.
    2. Keep only those rects whose vertical centre is between the previous
       boundary (top of page or previous caption) and the current caption.
    3. Union them and expand slightly for padding.
    4. If no rects are found (pure-text or OCR page), use the region between
       the nearest body-text block above and the caption.
    """
    caption_y_top = caption_anchor["bbox"][1]
    caption_y_bottom = caption_anchor["bbox"][3]

    upper_bound = 0.0
    if prev_anchor is not None:
        upper_bound = prev_anchor["bbox"][3] + 2.0

    img_rects = _collect_xref_rects(page)
    draw_rects = _collect_drawing_rects(page)
    all_rects = img_rects + draw_rects

    relevant: list[tuple[float, float, float, float]] = []
    for r in all_rects:
        ry_mid = (r[1] + r[3]) / 2.0
        if upper_bound <= ry_mid <= caption_y_top + 5:
            clipped_y1 = min(r[3], caption_y_top - 2.0)
            if clipped_y1 > r[1]:
                relevant.append((r[0], r[1], r[2], clipped_y1))

    if relevant:
        caption_x0, _, caption_x1, _ = caption_anchor["bbox"]
        x0 = min([r[0] for r in relevant] + [caption_x0])
        y0 = min(r[1] for r in relevant)
        x1 = max([r[2] for r in relevant] + [caption_x1])
        y1 = max(r[3] for r in relevant)
    else:
        body_blocks = _find_body_text_blocks(page)
        nearest_above_y = upper_bound
        for bb in body_blocks:
            if bb[3] < caption_y_top - 5 and bb[3] > nearest_above_y:
                nearest_above_y = bb[3]
        y0 = nearest_above_y + 2.0
        x0 = page_rect.x0
        x1 = page_rect.x1
        y1 = caption_y_top - 2.0

    y1 = max(y1, caption_y_bottom + 2.0)

    bbox = _clip_to_page((x0, y0, x1, y1), page_rect)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width < MIN_FIGURE_WIDTH_PT or height < MIN_FIGURE_HEIGHT_PT:
        return None
    return bbox


def _collect_text_lines(page) -> list[dict]:
    """Return per-line records sorted top-to-bottom.

    Each record::

        {"bbox": (x0, y0, x1, y1), "text": str}
    """
    lines_out: list[dict] = []
    blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            lines_out.append({"bbox": tuple(line["bbox"]), "text": text})
    lines_out.sort(key=lambda r: r["bbox"][1])
    return lines_out


def _cluster_lines_into_rows(
    lines: list[dict], *, y_tolerance: float = 2.0
) -> list[dict]:
    """Cluster sibling text lines that share roughly the same vertical band.

    PDFs created by LaTeX often emit one PyMuPDF "line" per cell, so a single
    visual row of a table is split into many independent line records.  We
    merge lines whose ``y0`` falls within ``y_tolerance`` points of the row
    seed so that downstream heuristics can reason about a true logical row.

    Each output record::

        {
            "bbox": (x0, y0, x1, y1),  # union of all member bboxes
            "tokens": [str, ...],       # text content of each member, left-to-right
            "text": str,                # tokens joined by single spaces
            "members": [dict, ...],     # original line records inside the row
        }
    """
    rows: list[dict] = []
    sorted_lines = sorted(lines, key=lambda r: (r["bbox"][1], r["bbox"][0]))
    for line in sorted_lines:
        bx0, by0, bx1, by1 = line["bbox"]
        placed = False
        for row in rows:
            rx0, ry0, rx1, ry1 = row["bbox"]
            row_mid = (ry0 + ry1) / 2.0
            line_mid = (by0 + by1) / 2.0
            if abs(line_mid - row_mid) <= y_tolerance:
                row["bbox"] = (
                    min(rx0, bx0),
                    min(ry0, by0),
                    max(rx1, bx1),
                    max(ry1, by1),
                )
                row["members"].append(line)
                placed = True
                break
        if not placed:
            rows.append({
                "bbox": (bx0, by0, bx1, by1),
                "members": [line],
            })

    for row in rows:
        row["members"].sort(key=lambda m: m["bbox"][0])
        row["tokens"] = [m["text"] for m in row["members"]]
        row["text"] = " ".join(row["tokens"])
    rows.sort(key=lambda r: r["bbox"][1])
    return rows


def _row_is_table_like(row: dict) -> bool:
    """A logical row that looks like part of a data table.

    The row qualifies if it has many short tokens (typical for tabular cells).
    Either:
    - many independent cells (≥ 3 separate line members), or
    - a single text whose tokens look like numeric or textual table body cells.
    """
    members = row.get("members", [])
    text = row.get("text", "")
    if len(members) >= 3:
        # Many separated cells: the typical case for LaTeX-rendered tables
        # where every cell becomes its own PyMuPDF line.
        return True
    return _looks_like_data_row(text) or _looks_like_text_table_row(text)


def _restrict_row_to_caption_column(row: dict, caption_bbox: tuple[float, float, float, float], page_rect) -> dict | None:
    """Keep only row cells in the same page column as a narrow caption.

    In two-column papers, unrelated left/right column tables often share the
    same y bands. Row clustering can merge them unless we trim by caption side.
    """
    members = list(row.get("members", []) or [])
    if not members:
        return row

    page_x0 = float(getattr(page_rect, "x0", 0.0))
    page_x1 = float(getattr(page_rect, "x1", 0.0))
    page_width = max(1.0, page_x1 - page_x0)
    page_mid = (page_x0 + page_x1) / 2.0
    cx0, _, cx1, _ = caption_bbox
    caption_width = cx1 - cx0
    if caption_width >= page_width * 0.45:
        return row

    caption_mid = (cx0 + cx1) / 2.0
    caption_is_left = caption_mid < page_mid
    expanded_caption_x0 = cx0 - 24.0
    expanded_caption_x1 = cx1 + 24.0

    def overlaps_caption_band(x0: float, x1: float) -> bool:
        overlap = max(0.0, min(x1, expanded_caption_x1) - max(x0, expanded_caption_x0))
        width = max(1.0, x1 - x0)
        return overlap >= min(16.0, width * 0.25)

    rx0, _, rx1, _ = row["bbox"]
    row_mid = (rx0 + rx1) / 2.0
    row_same_side = (row_mid < page_mid) == caption_is_left
    row_overlaps_caption_band = overlaps_caption_band(rx0, rx1)
    if not (rx0 < page_mid - 10.0 and rx1 > page_mid + 10.0):
        return row if row_same_side or row_overlaps_caption_band else None

    filtered = []
    for member in members:
        mx0, _, mx1, _ = member["bbox"]
        member_mid = (mx0 + mx1) / 2.0
        same_side = (member_mid < page_mid) == caption_is_left
        if same_side or overlaps_caption_band(mx0, mx1):
            filtered.append(member)

    if not filtered:
        return None
    if len(filtered) == len(members):
        return row

    x0 = min(member["bbox"][0] for member in filtered)
    y0 = min(member["bbox"][1] for member in filtered)
    x1 = max(member["bbox"][2] for member in filtered)
    y1 = max(member["bbox"][3] for member in filtered)
    tokens = [member["text"] for member in sorted(filtered, key=lambda m: m["bbox"][0])]
    return {
        "bbox": (x0, y0, x1, y1),
        "members": sorted(filtered, key=lambda m: m["bbox"][0]),
        "tokens": tokens,
        "text": " ".join(tokens),
    }


def _line_is_inside_any_block(
    line_bbox: tuple[float, float, float, float],
    blocks: list[tuple[float, float, float, float, str]],
) -> bool:
    for bb in blocks:
        if (
            line_bbox[0] >= bb[0] - 0.5
            and line_bbox[1] >= bb[1] - 0.5
            and line_bbox[2] <= bb[2] + 0.5
            and line_bbox[3] <= bb[3] + 0.5
        ):
            return True
    return False


def _grow_table_region(
    page,
    caption_anchor: dict,
    rows: list[dict],
    paragraph_blocks: list[tuple[float, float, float, float, str]],
    *,
    direction: str,
    upper_bound: float,
    lower_bound: float,
) -> tuple[list[tuple[float, float, float, float]], int]:
    """Walk away from the caption in ``direction`` ('up' or 'down') and collect
    logical rows that look like part of a tabular layout.

    Returns the list of accepted row bboxes (caption excluded) and the number
    of rows confirmed as table body rows.  The caller decides which direction
    wins.
    """
    caption_y0 = caption_anchor["bbox"][1]
    caption_y1 = caption_anchor["bbox"][3]

    accepted: list[tuple[float, float, float, float]] = []
    data_row_count = 0
    consecutive_non_data = 0
    seen_data = False
    last_accepted_edge = caption_y1 if direction == "down" else caption_y0

    if direction == "down":
        candidates = [r for r in rows if r["bbox"][1] > caption_y1 + 0.5]
        candidates.sort(key=lambda r: r["bbox"][1])
        boundary_check = lambda ly0, ly1: ly1 >= lower_bound
    else:
        candidates = [r for r in rows if r["bbox"][3] < caption_y0 - 0.5]
        candidates.sort(key=lambda r: r["bbox"][3], reverse=True)
        boundary_check = lambda ly0, ly1: ly0 <= upper_bound

    for row in candidates:
        restricted_row = _restrict_row_to_caption_column(row, caption_anchor["bbox"], page.rect)
        if restricted_row is None:
            continue
        row = restricted_row
        rx0, ry0, rx1, ry1 = row["bbox"]
        if boundary_check(ry0, ry1):
            break
        text = row["text"]
        is_table_row = _row_is_table_like(row)
        in_paragraph_block = _line_is_inside_any_block(row["bbox"], paragraph_blocks)
        row_gap = ry0 - last_accepted_edge if direction == "down" else last_accepted_edge - ry1
        row_height = max(ry1 - ry0, 1.0)
        if seen_data and row_gap > max(12.0, row_height * 1.8) and not is_table_row:
            break
        if (
            seen_data
            and len(row.get("members", []) or []) <= 1
            and in_paragraph_block
            and not _looks_like_data_row(text)
        ):
            break
        # If this row sits entirely inside a real prose paragraph and does not
        # look table-shaped, we have walked out of the table.
        if not is_table_row and (in_paragraph_block or len(text) > 200):
            break
        if is_table_row:
            consecutive_non_data = 0
            data_row_count += 1
            seen_data = True
        else:
            consecutive_non_data += 1
            # Header / footnote rows are allowed but we should not collect an
            # unbounded run of them when no real data has been seen yet.
            if consecutive_non_data > 4 and not seen_data:
                break
            if consecutive_non_data > 8:
                break
        accepted.append(row["bbox"])
        last_accepted_edge = ry1 if direction == "down" else ry0

    return accepted, data_row_count


def _finalize_table_bbox(
    page,
    caption_anchor: dict,
    extra_rects: list[tuple[float, float, float, float]],
    page_rect,
) -> tuple[float, float, float, float] | None:
    if not extra_rects:
        return None
    caption_x0, caption_y0, caption_x1, caption_y1 = caption_anchor["bbox"]
    accepted: list[tuple[float, float, float, float]] = list(extra_rects) + [
        (caption_x0, caption_y0, caption_x1, caption_y1)
    ]

    y0 = min(b[1] for b in accepted)
    y1 = max(b[3] for b in accepted)
    initial_x0 = min(b[0] for b in accepted)
    initial_x1 = max(b[2] for b in accepted)
    for r in _collect_drawing_rects(page):
        ry_mid = (r[1] + r[3]) / 2.0
        if y0 - 4.0 <= ry_mid <= y1 + 4.0 and r[2] >= initial_x0 - 12.0 and r[0] <= initial_x1 + 12.0:
            accepted.append(r)
    for r in _collect_xref_rects(page):
        ry_mid = (r[1] + r[3]) / 2.0
        if y0 - 4.0 <= ry_mid <= y1 + 4.0 and r[2] >= initial_x0 - 12.0 and r[0] <= initial_x1 + 12.0:
            accepted.append(r)

    x0 = min(b[0] for b in accepted)
    y0 = min(b[1] for b in accepted)
    x1 = max(b[2] for b in accepted)
    y1 = max(b[3] for b in accepted)

    bbox = _clip_to_page((x0, y0, x1, y1), page_rect, padding=6.0)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width < MIN_FIGURE_WIDTH_PT or height < MIN_FIGURE_HEIGHT_PT:
        return None
    return bbox


def _estimate_table_bbox(
    page,
    caption_anchor: dict,
    prev_anchor: dict | None,
    next_anchor: dict | None,
    page_rect,
) -> tuple[float, float, float, float] | None:
    result = _estimate_table_bbox_with_rows(page, caption_anchor, prev_anchor, next_anchor, page_rect)
    return result[0] if result is not None else None


def _estimate_table_bbox_with_rows(
    page,
    caption_anchor: dict,
    prev_anchor: dict | None,
    next_anchor: dict | None,
    page_rect,
) -> tuple[tuple[float, float, float, float], int] | None:
    r"""Estimate the bounding box of a table.

    Tables in academic papers come in two layouts:

    - caption-on-top: ``\caption`` precedes ``\begin{tabular}``;
    - caption-on-bottom: tabular body precedes ``\caption``.

    LaTeX makes both common, and within a single paper both forms can mix
    (e.g. wide tables placed with ``[t]`` vs. ``[b]``).  We therefore probe
    both directions and pick the side with strictly more confirmed table body
    rows.  Ties go to the downward side, matching the most common ACM / IEEE
    template defaults.

    Tables are usually pure text + thin separator lines, so the page rendering
    of just the union of text-line bboxes is sufficient.  We additionally
    union any drawing rects (``\hline``, frames) and image rects that fall in
    the same y-range, in case the paper places company-logo plots inside a
    table cell.
    """
    caption_y0 = caption_anchor["bbox"][1]
    caption_y1 = caption_anchor["bbox"][3]

    upper_bound = page_rect.y0
    if prev_anchor is not None:
        upper_bound = max(page_rect.y0, prev_anchor["bbox"][3] + 2.0)

    lower_bound = page_rect.y1
    if next_anchor is not None:
        lower_bound = max(caption_y1 + 1.0, next_anchor["bbox"][1] - 2.0)

    text_lines = _collect_text_lines(page)
    rows = _cluster_lines_into_rows(text_lines)
    paragraph_blocks = _find_paragraph_blocks(page)

    down_lines, down_data = _grow_table_region(
        page,
        caption_anchor,
        rows,
        paragraph_blocks,
        direction="down",
        upper_bound=upper_bound,
        lower_bound=lower_bound,
    )
    up_lines, up_data = _grow_table_region(
        page,
        caption_anchor,
        rows,
        paragraph_blocks,
        direction="up",
        upper_bound=upper_bound,
        lower_bound=lower_bound,
    )

    if down_data == 0 and up_data == 0:
        return None

    chosen: list[tuple[float, float, float, float]]
    chosen_data_rows: int
    if up_data > down_data:
        chosen = up_lines
        chosen_data_rows = up_data
    else:
        chosen = down_lines
        chosen_data_rows = down_data

    bbox = _finalize_table_bbox(page, caption_anchor, chosen, page_rect)
    if bbox is None:
        return None
    return bbox, chosen_data_rows


def _render_crop(page, bbox: tuple[float, float, float, float], dpi: int) -> bytes:
    """Render a page region to PNG bytes at the given DPI."""
    clip = fitz.Rect(*bbox)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    return pix.tobytes("png")


def _unique_figure_asset_filename(page_number: int, label: str, used_filenames: set[str]) -> str:
    safe_label = re.sub(r"[^a-zA-Z0-9]+", "_", label.lower()).strip("_") or "unlabeled"
    base = f"page_{page_number:03d}_fig_{safe_label}.png"
    if base not in used_filenames:
        used_filenames.add(base)
        return base

    stem = base.removesuffix(".png")
    suffix = 2
    while True:
        candidate = f"{stem}_{suffix}.png"
        if candidate not in used_filenames:
            used_filenames.add(candidate)
            return candidate
        suffix += 1


def extract_figure_regions(
    page, page_number: int, images_dir: Path, *, dpi: int = FIGURE_RENDER_DPI
) -> list[dict]:
    """Detect figure/table captions and crop the corresponding visual region."""
    if fitz is None:
        return []

    anchors = _find_caption_blocks(page)
    if not anchors:
        return []

    page_rect = page.rect
    assets: list[dict] = []
    used_filenames: set[str] = set()

    for idx, anchor in enumerate(anchors):
        prev_anchor = anchors[idx - 1] if idx > 0 else None
        next_anchor = anchors[idx + 1] if idx + 1 < len(anchors) else None
        kind = anchor.get("kind", "figure")

        bbox: tuple[float, float, float, float] | None
        table_body_rows = 0
        if kind == "table":
            table_result = _estimate_table_bbox_with_rows(page, anchor, prev_anchor, next_anchor, page_rect)
            if table_result is not None:
                bbox, table_body_rows = table_result
            else:
                bbox = None
            if bbox is None:
                # Fall back to the figure-shape estimator in case the table is
                # actually rendered as an embedded image.
                bbox = _estimate_figure_bbox_above_caption(page, anchor, prev_anchor, page_rect)
        else:
            bbox = _estimate_figure_bbox_above_caption(page, anchor, prev_anchor, page_rect)
            if bbox is None:
                bbox = _estimate_table_bbox(page, anchor, prev_anchor, next_anchor, page_rect)

        if bbox is None:
            continue

        label = anchor["label"]
        filename = _unique_figure_asset_filename(page_number, label, used_filenames)
        output_path = images_dir / filename

        try:
            png_bytes = _render_crop(page, bbox, dpi)
        except Exception:
            continue

        save_image_bytes(output_path, png_bytes)

        width_px = int((bbox[2] - bbox[0]) * dpi / 72.0)
        height_px = int((bbox[3] - bbox[1]) * dpi / 72.0)
        quality_signals = _quality_signals_for_crop(
            page,
            kind,
            bbox,
            anchor,
            page_rect,
            table_body_rows=table_body_rows,
            caption_anchors=anchors,
        )

        assets.append(
            {
                "page_number": page_number,
                "label": label,
                "kind": kind,
                "caption_text": normalize_whitespace(anchor["line_text"]),
                "filename": filename,
                "path": str(output_path),
                "ext": "png",
                "width": width_px,
                "height": height_px,
                "bbox_pt": list(bbox),
                "size_bytes": len(png_bytes),
                "extraction_level": "figure",
                "quality_signals": quality_signals,
            }
        )

    return assets


def main() -> None:
    args = parser().parse_args()
    record = ensure_record(args.input)
    pdf_path = Path(str(record.get("pdf_path", "")).strip()).expanduser()
    if not pdf_path.exists():
        from_fetch = maybe_load_json_record(args.input) or {}
        pdf_candidate = str(from_fetch.get("pdf_path", "")).strip()
        if pdf_candidate:
            pdf_path = Path(pdf_candidate).expanduser()
    if not pdf_path.exists():
        raise SystemExit("extract_pdf_assets.py requires a resolvable local PDF path.")
    if fitz is None:
        raise SystemExit("extract_pdf_assets.py requires PyMuPDF (`fitz`).")

    asset_root = Path(args.assets_dir).expanduser().resolve() if args.assets_dir else default_assets_dir(record)
    images_dir = asset_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    figure_dpi = args.figure_dpi

    doc = fitz.open(pdf_path.resolve())
    page_records: list[dict] = []
    image_assets: list[dict] = []
    figure_assets: list[dict] = []
    asset_coverage: dict = {}
    try:
        total_pages = len(doc)
        page_limit = min(total_pages, args.max_pages)
        asset_coverage = {
            "total_pages": total_pages,
            "asset_max_pages": args.max_pages,
            "asset_pages_scanned": page_limit,
            "truncated_due_to_asset_page_limit": total_pages > args.max_pages,
        }
        for idx in range(page_limit):
            page = doc[idx]
            page_number = idx + 1
            text = normalize_whitespace(page.get_text("text"))
            searchable_chars = len(text)
            extraction_method = "text" if searchable_chars >= args.min_searchable_chars else "none"
            ocr_text = ""
            if extraction_method == "none":
                ocr_text = ocr_page(page, args.ocr_dpi)
                if ocr_text:
                    extraction_method = "ocr"
            page_images = extract_page_images(doc, page, page_number, images_dir)
            image_assets.extend(page_images)

            page_figures = extract_figure_regions(page, page_number, images_dir, dpi=figure_dpi)
            figure_assets.extend(page_figures)

            page_records.append(
                {
                    "page_number": page_number,
                    "searchable_text_chars": searchable_chars,
                    "text_extraction_method": extraction_method,
                    "ocr_used": extraction_method == "ocr",
                    "image_count": len(page_images),
                    "figure_count": len(page_figures),
                    "page_text": text or ocr_text,
                    "text_preview": (text or ocr_text)[:240],
                }
            )
    finally:
        doc.close()

    payload = {
        "status": "ok",
        "script": "extract_pdf_assets.py",
        "paper_id": record.get("paper_id", ""),
        "pdf_path": str(pdf_path.resolve()),
        "asset_root": str(asset_root),
        "images_dir": str(images_dir),
        "page_assets": page_records,
        "image_assets": image_assets,
        "figure_assets": figure_assets,
        "asset_coverage": asset_coverage,
        "ocr_available": bool(pytesseract and Image),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
