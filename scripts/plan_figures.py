#!/usr/bin/env python3
"""Plan figure/table placeholders and attach deterministic asset candidates."""

from __future__ import annotations

import argparse
import re

from common import maybe_load_json_record, normalize_whitespace


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan figures")
    p.add_argument("--input", default="", help="Primary JSON path or string.")
    p.add_argument("--evidence", default="", help="Evidence JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    p.add_argument("--max-items", type=int, default=12, help="Maximum number of figure/table items to keep. 0 means keep all.")
    return p


def merge_inputs(primary: dict | None, evidence: dict | None, assets: dict | None) -> dict:
    merged: dict = {}
    for item in [primary, evidence, assets]:
        if isinstance(item, dict):
            merged.update(item)
    if evidence and evidence.get("evidence_pack"):
        merged["evidence_pack"] = evidence["evidence_pack"]
    if assets and assets.get("page_assets"):
        merged["page_assets"] = assets["page_assets"]
        merged["image_assets"] = assets.get("image_assets", [])
    return merged


def classify_caption_kind(item_id: str, caption: str) -> tuple[str, str, str]:
    text = f"{item_id} {caption}".lower()
    if any(token in text for token in ["pipeline", "framework", "overview", "architecture", "system"]):
        return "method_overview", "方法主线", "这张图概括了整体方法或系统流程，最适合放在方法主线帮助快速建立结构理解。"
    if any(token in text for token in ["dataset", "data", "corpus", "participants", "recordings", "setup", "distribution", "quality"]):
        return "data_or_task", "数据与任务定义", "这张图更像任务设定或数据说明，放在数据与任务定义最合适。"
    if any(token in text for token in ["accuracy", "score", "performance", "comparison", "win-rate", "results", "recall"]):
        return "main_result", "关键结果", "这张图或表直接承载主结果，适合放在关键结果部分。"
    if item_id.lower().startswith("table"):
        return "table_result", "关键结果", "这是关键结果表，适合放在关键结果部分辅助定位核心数值。"
    return "supporting_figure", "深度分析", "这张图更适合作为补充图，放在深度分析部分帮助解释作者论点。"


def build_figure_items(evidence_pack: dict, *, limit: int = 12) -> list[dict]:
    raw_items = []
    for item in evidence_pack.get("figure_captions", []) or []:
        if isinstance(item, dict):
            raw_items.append({"id": item.get("id", ""), "caption": item.get("caption", ""), "source": "figure"})
    for item in evidence_pack.get("table_captions", []) or []:
        if isinstance(item, dict):
            raw_items.append({"id": item.get("id", ""), "caption": item.get("caption", ""), "source": "table"})

    grouped: dict[str, dict] = {}
    order: list[str] = []
    for item in raw_items:
        item_id = normalize_whitespace(str(item.get("id", "")))
        caption = normalize_whitespace(str(item.get("caption", "")))
        if not item_id:
            continue
        key = item_id.lower()
        current = grouped.get(key)
        candidate = {"id": item_id, "caption": caption, "source": item.get("source", "")}
        if current is None:
            grouped[key] = candidate
            order.append(key)
            continue
        current_caption = str(current.get("caption", ""))
        # Prefer the richer caption if multiple extraction passes produced duplicates.
        if len(caption) > len(current_caption):
            grouped[key] = candidate

    picked: list[dict] = []
    for key in order:
        item = grouped[key]
        item_id = normalize_whitespace(str(item.get("id", "")))
        caption = normalize_whitespace(str(item.get("caption", "")))
        kind, section, reason = classify_caption_kind(item_id, caption)
        priority = 3
        if kind == "method_overview":
            priority = 1
        elif kind in {"main_result", "table_result"}:
            priority = 2
        picked.append(
            {
                "id": item_id,
                "caption": caption,
                "kind": kind,
                "section": section,
                "reason": reason,
                "priority": priority,
                "anchor_text": section,
                "insert_mode": "placeholder",
            }
        )
    picked.sort(key=lambda item: (item["priority"], item["id"]))
    if limit and limit > 0:
        return picked[:limit]
    return picked


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "our",
    "study",
    "figure",
    "table",
    "results",
    "result",
    "shows",
    "showing",
    "overview",
}


def label_variants(label: str) -> list[str]:
    normalized = normalize_whitespace(label).lower()
    if not normalized:
        return []
    variants = {normalized}
    short = normalized.replace("figure", "fig").replace("table.", "table").replace("fig.", "fig")
    variants.add(short)
    digits = re.findall(r"\d+[a-z]?", normalized)
    if digits:
        number = digits[0]
        if normalized.startswith("fig"):
            variants.update({f"fig {number}", f"fig. {number}", f"figure {number}"})
        if normalized.startswith("table"):
            variants.update({f"table {number}", f"table. {number}"})
    return sorted(variants)


def caption_keywords(caption: str, *, limit: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", caption.lower())
    picked: list[str] = []
    for word in words:
        if word in STOPWORDS or word in picked:
            continue
        picked.append(word)
        if len(picked) >= limit:
            break
    return picked


def match_snippet(page_text: str, needle: str, *, radius: int = 90) -> str:
    lower = page_text.lower()
    idx = lower.find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(page_text), idx + len(needle) + radius)
    snippet = normalize_whitespace(page_text[start:end])
    return snippet[:220]


def attach_candidate_images(items: list[dict], page_assets: list[dict], image_assets: list[dict]) -> list[dict]:
    image_map: dict[int, list[dict]] = {}
    for image in image_assets:
        if not isinstance(image, dict):
            continue
        page_number = int(image.get("page_number", 0) or 0)
        if page_number <= 0:
            continue
        image_map.setdefault(page_number, []).append(image)

    pages_with_images = [page for page in page_assets if isinstance(page, dict) and int(page.get("image_count", 0) or 0) > 0]

    for index, item in enumerate(items):
        variants = label_variants(str(item.get("id", "")))
        keywords = caption_keywords(str(item.get("caption", "")))
        candidates: list[dict] = []
        for page in pages_with_images:
            page_number = int(page.get("page_number", 0) or 0)
            page_text = normalize_whitespace(str(page.get("page_text", "")))
            lower = page_text.lower()
            score = 0
            matched_terms: list[str] = []
            snippets: list[str] = []

            for variant in variants:
                if variant and variant in lower:
                    score += 5
                    matched_terms.append(variant)
                    snippet = match_snippet(page_text, variant)
                    if snippet:
                        snippets.append(snippet)
                    break

            keyword_hits = 0
            for keyword in keywords:
                if keyword in lower:
                    keyword_hits += 1
                    matched_terms.append(keyword)
                    snippet = match_snippet(page_text, keyword)
                    if snippet:
                        snippets.append(snippet)
            score += min(keyword_hits, 3)

            if score == 0 and index < len(pages_with_images):
                fallback_page = int(pages_with_images[index].get("page_number", 0) or 0)
                if page_number == fallback_page:
                    score = 1
                    matched_terms.append("order_fallback")

            if score <= 0:
                continue

            candidates.append(
                {
                    "page_number": page_number,
                    "score": score,
                    "matched_terms": matched_terms[:6],
                    "snippet": snippets[0] if snippets else normalize_whitespace(str(page.get("text_preview", "")))[:220],
                    "images": [
                        {
                            "filename": img.get("filename", ""),
                            "path": img.get("path", ""),
                            "width": img.get("width", 0),
                            "height": img.get("height", 0),
                            "size_bytes": img.get("size_bytes", 0),
                        }
                        for img in image_map.get(page_number, [])[:3]
                    ],
                }
            )

        candidates.sort(key=lambda candidate: (-candidate["score"], candidate["page_number"]))
        item["candidate_pages"] = candidates[:3]
        item["matching_strategy"] = "page-proximity-and-caption-cues"
    return items


def main() -> None:
    from common import emit

    args = parser().parse_args()
    primary = maybe_load_json_record(args.input) if args.input else None
    evidence = maybe_load_json_record(args.evidence) if args.evidence else None
    assets = maybe_load_json_record(args.assets) if args.assets else None
    data = merge_inputs(primary, evidence, assets)
    if not data:
        raise SystemExit("plan_figures.py requires at least one JSON input.")

    evidence_pack = data.get("evidence_pack", {}) if isinstance(data.get("evidence_pack"), dict) else {}
    page_assets = data.get("page_assets", []) if isinstance(data.get("page_assets"), list) else []
    image_assets = data.get("image_assets", []) if isinstance(data.get("image_assets"), list) else []
    items = build_figure_items(evidence_pack, limit=args.max_items)
    items = attach_candidate_images(items, page_assets, image_assets)
    payload = {
        "status": "ok",
        "script": "plan_figures.py",
        "paper_id": args.paper_id or data.get("paper_id", ""),
        "figure_plan": {
            "paper_id": args.paper_id or data.get("paper_id", ""),
            "figures": items,
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
