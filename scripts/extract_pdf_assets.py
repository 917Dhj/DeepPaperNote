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
    r"^((?:fig(?:ure)?|table)\.?\s*\d+[a-z]?)\b",
    re.IGNORECASE,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract pdf assets")
    p.add_argument("--input", required=True, help="Fetch JSON path, metadata JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--assets-dir", default="", help="Optional explicit assets directory.")
    p.add_argument("--max-pages", type=int, default=24, help="Maximum pages to scan.")
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

    Each anchor: {"label": "Figure 3", "bbox": (x0, y0, x1, y1), "line_text": ...}
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
            if not match:
                continue
            label = normalize_whitespace(match.group(1))

            caption_lines_text = [line_text]
            first_bbox = line["bbox"]
            x0, y0, x1, y1 = first_bbox

            for cont_line in lines[line_idx + 1:]:
                cont_spans = cont_line.get("spans", [])
                if not cont_spans:
                    break
                cont_text = "".join(s.get("text", "") for s in cont_spans).strip()
                if not cont_text:
                    break
                if CAPTION_RE.match(cont_text):
                    break
                cb = cont_line["bbox"]
                x0 = min(x0, cb[0])
                y1 = max(y1, cb[3])
                x1 = max(x1, cb[2])
                caption_lines_text.append(cont_text)

            full_caption = " ".join(caption_lines_text)
            anchors.append({
                "label": label,
                "bbox": (x0, y0, x1, y1),
                "line_text": full_caption,
            })
    anchors.sort(key=lambda a: a["bbox"][1])
    return anchors


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


def _estimate_figure_bbox(
    page,
    caption_anchor: dict,
    next_anchor: dict | None,
    page_rect,
) -> tuple[float, float, float, float] | None:
    """Estimate the bounding box of the figure above (or below) its caption.

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
    if next_anchor is not None:
        upper_bound = next_anchor["bbox"][3] + 2.0

    img_rects = _collect_xref_rects(page)
    draw_rects = _collect_drawing_rects(page)
    all_rects = img_rects + draw_rects

    relevant: list[tuple[float, float, float, float]] = []
    for r in all_rects:
        ry_mid = (r[1] + r[3]) / 2.0
        if upper_bound <= ry_mid <= caption_y_top + 5:
            relevant.append(r)

    if relevant:
        x0 = min(r[0] for r in relevant)
        y0 = min(r[1] for r in relevant)
        x1 = max(r[2] for r in relevant)
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

    padding = 4.0
    x0 = max(page_rect.x0, x0 - padding)
    y0 = max(page_rect.y0, y0 - padding)
    x1 = min(page_rect.x1, x1 + padding)
    y1 = min(page_rect.y1, y1 + padding)

    width = x1 - x0
    height = y1 - y0
    if width < MIN_FIGURE_WIDTH_PT or height < MIN_FIGURE_HEIGHT_PT:
        return None

    return (x0, y0, x1, y1)


def _render_crop(page, bbox: tuple[float, float, float, float], dpi: int) -> bytes:
    """Render a page region to PNG bytes at the given DPI."""
    clip = fitz.Rect(*bbox)
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    return pix.tobytes("png")


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

    for idx, anchor in enumerate(anchors):
        prev_anchor = anchors[idx - 1] if idx > 0 else None
        bbox = _estimate_figure_bbox(page, anchor, prev_anchor, page_rect)
        if bbox is None:
            continue

        label = anchor["label"]
        safe_label = re.sub(r"[^a-zA-Z0-9]+", "_", label.lower()).strip("_")
        filename = f"page_{page_number:03d}_fig_{safe_label}.png"
        output_path = images_dir / filename

        try:
            png_bytes = _render_crop(page, bbox, dpi)
        except Exception:
            continue

        save_image_bytes(output_path, png_bytes)

        width_px = int((bbox[2] - bbox[0]) * dpi / 72.0)
        height_px = int((bbox[3] - bbox[1]) * dpi / 72.0)

        assets.append(
            {
                "page_number": page_number,
                "label": label,
                "caption_text": normalize_whitespace(anchor["line_text"]),
                "filename": filename,
                "path": str(output_path),
                "ext": "png",
                "width": width_px,
                "height": height_px,
                "bbox_pt": list(bbox),
                "size_bytes": len(png_bytes),
                "extraction_level": "figure",
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
    try:
        page_limit = min(len(doc), args.max_pages)
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
        "ocr_available": bool(pytesseract and Image),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
