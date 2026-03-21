#!/usr/bin/env python3
"""Extract page-level PDF assets for later model-side semantic figure matching."""

from __future__ import annotations

import argparse
import io
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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "extract pdf assets")
    p.add_argument("--input", required=True, help="Fetch JSON path, metadata JSON path, JSON string, or raw paper reference.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--assets-dir", default="", help="Optional explicit assets directory.")
    p.add_argument("--max-pages", type=int, default=24, help="Maximum pages to scan.")
    p.add_argument("--min-searchable-chars", type=int, default=100, help="Minimum characters for a page to count as searchable text.")
    p.add_argument("--ocr-dpi", type=int, default=300, help="DPI used when OCR fallback is needed.")
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

    doc = fitz.open(pdf_path.resolve())
    page_records: list[dict] = []
    image_assets: list[dict] = []
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
            page_records.append(
                {
                    "page_number": page_number,
                    "searchable_text_chars": searchable_chars,
                    "text_extraction_method": extraction_method,
                    "ocr_used": extraction_method == "ocr",
                    "image_count": len(page_images),
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
        "ocr_available": bool(pytesseract and Image),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
