#!/usr/bin/env python3
"""Plan figure/table placeholders and attach deterministic asset candidates."""

from __future__ import annotations

import argparse
import re

from common import caption_preference_score, maybe_load_json_record, normalize_whitespace


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
        merged["figure_assets"] = assets.get("figure_assets", [])
    return merged


def classify_caption_kind(item_id: str, caption: str) -> tuple[str, str, str]:
    text = f"{item_id} {caption}".lower()
    if any(
        token in text
        for token in [
            "accuracy",
            "score",
            "performance",
            "comparison",
            "win-rate",
            "results",
            "recall",
            "latency",
            "throughput",
            "request rate",
            "batched request",
            "batch size",
            "memory saving",
            "ablation",
            "ablated",
            "overhead",
            "microbenchmark",
            "block size",
            "single sequence generation",
            "parallel generation",
        ]
    ) or re.search(
        r"\b(?:model|system|architecture|method|approach)\s+"
        r"(?:produces|achieves|outperforms|improves|reduces|increases)\b",
        text,
    ):
        return "main_result", "关键结果", "这张图或表直接承载主结果，适合放在关键结果部分。"
    if any(
        token in text
        for token in [
            "prisma",
            "literature flow",
            "flow diagram",
            "study selection",
            "screening flow",
            "screened records",
            "records screened",
            "identification of studies",
        ]
    ):
        return "data_or_task_overview", "数据与任务定义", "这张图解释文献筛选或纳入流程；如果候选图质量足够，适合放在数据与任务定义部分帮助读者理解综述证据来源。"
    if any(
        token in text
        for token in [
            "pipeline",
            "framework",
            "overview",
            "architecture",
            "system",
            "workflow",
            "stage",
            "procedure",
            "process",
        ]
    ):
        return "method_overview", "机制流程", "这张图概括了整体方法或系统流程；如果匹配置信度足够高，最适合放在 `### 机制流程` 帮助快速建立执行链理解。"
    if any(
        token in text
        for token in [
            "created from",
            "sources",
            "connect",
            "collection",
            "curation",
            "filtering",
            "pull request",
            "issue",
        ]
    ):
        return "data_or_task_overview", "数据与任务定义", "这张图解释任务或数据集如何被构造；如果候选图质量足够，适合放在数据与任务定义部分帮助读者理解数据来源。"
    if any(
        token in text
        for token in [
            "dataset",
            "data",
            "corpus",
            "participants",
            "recordings",
            "setup",
            "distribution",
            "quality",
            "task",
            "instance",
            "attribute",
        ]
    ):
        return "data_or_task", "数据与任务定义", "这张图更像任务设定或数据说明，放在数据与任务定义最合适。"
    if any(
        token in text
        for token in [
            "algorithm",
            "block table",
            "kv cache",
            "key-value cache",
            "copy-on-write",
            "parallel sampling",
            "beam search",
            "shared prompt",
            "shared prefix",
            "memory management",
            "block translation",
        ]
    ):
        return "method_detail", "方法主线", "这张图解释方法内部机制或关键执行状态，适合放在方法主线部分作为机制细节占位。"
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
    grouped_scores: dict[str, int] = {}
    order: list[str] = []
    for item in raw_items:
        item_id = normalize_whitespace(str(item.get("id", "")))
        caption = normalize_whitespace(str(item.get("caption", "")))
        if not item_id:
            continue
        key = _normalize_label_for_match(item_id) or item_id.lower()
        current = grouped.get(key)
        candidate = {"id": item_id, "caption": caption, "source": item.get("source", "")}
        if current is None:
            grouped[key] = candidate
            grouped_scores[key] = caption_preference_score(item_id, caption)
            order.append(key)
            continue
        # Prefer true caption-looking lines over later body references such as
        # "Fig. 14 shows ..."; fall back to richness when both look caption-like.
        score = caption_preference_score(item_id, caption)
        if score > grouped_scores[key]:
            grouped[key] = candidate
            grouped_scores[key] = score

    picked: list[dict] = []
    for key in order:
        item = grouped[key]
        item_id = normalize_whitespace(str(item.get("id", "")))
        caption = normalize_whitespace(str(item.get("caption", "")))
        kind, section, reason = classify_caption_kind(item_id, caption)
        priority = 3
        if kind == "method_overview":
            priority = 1
        elif kind in {"data_or_task_overview", "main_result", "table_result", "method_detail"}:
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
        high_priority = [item for item in picked if int(item.get("priority", 99)) <= 2]
        supporting = [item for item in picked if int(item.get("priority", 99)) > 2]
        if len(high_priority) >= limit:
            return high_priority
        return high_priority + supporting[: limit - len(high_priority)]
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
    extended_match = re.match(r"^extended data (fig(?:ure)?|table)\.?\s*(\d+[a-z]?)$", normalized)
    if extended_match:
        prefix = "extended data table" if extended_match.group(1) == "table" else "extended data fig"
        variants.update(
            {
                f"{prefix} {extended_match.group(2)}",
                f"{prefix}. {extended_match.group(2)}",
            }
        )
    scheme_match = re.match(r"^(scheme|algorithm)\.?\s*(\d+[a-z]?)$", normalized)
    if scheme_match:
        variants.update(
            {
                f"{scheme_match.group(1)} {scheme_match.group(2)}",
                f"{scheme_match.group(1)}. {scheme_match.group(2)}",
            }
        )
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


def _normalize_label_for_match(label: str) -> str:
    """Normalize a figure/table label to a canonical form for matching.

    'Figure 3' / 'Fig. 3' / 'fig 3' / 'Figure. 3' all become 'fig 3'.
    'Table 2' / 'table. 2' / 'Table. 2' all become 'table 2'.
    """
    text = normalize_whitespace(label).lower()
    extended_figure_match = re.match(
        r"^extended\s+data\s+fig(?:ure)?\.?\s*(\d+[a-z]?)$",
        text,
    )
    if extended_figure_match:
        return f"extended data fig {extended_figure_match.group(1)}"
    extended_table_match = re.match(
        r"^extended\s+data\s+table\.?\s*(\d+[a-z]?)$",
        text,
    )
    if extended_table_match:
        return f"extended data table {extended_table_match.group(1)}"
    scheme_match = re.match(r"^(scheme|algorithm)\.?\s*(\d+[a-z]?)$", text)
    if scheme_match:
        return f"{scheme_match.group(1)} {scheme_match.group(2)}"
    supplementary_match = re.match(
        r"^supplementary\s+(fig(?:ure)?|table)\.?\s*(\d+[a-z]?)$",
        text,
    )
    if supplementary_match:
        prefix = "table" if supplementary_match.group(1) == "table" else "fig"
        return f"{prefix} s{supplementary_match.group(2)}"
    label_match = re.match(r"^(fig(?:ure)?|table)\.?\s*([as]?\d+[a-z]?)$", text)
    if label_match:
        prefix = "table" if label_match.group(1) == "table" else "fig"
        return f"{prefix} {label_match.group(2)}"
    return normalize_whitespace(text)


def _match_figure_asset(item_id: str, figure_assets: list[dict]) -> dict | None:
    """Find a figure-level asset whose label matches the plan item id."""
    target = _normalize_label_for_match(item_id)
    if not target:
        return None
    for asset in figure_assets:
        asset_label = _normalize_label_for_match(str(asset.get("label", "")))
        if asset_label == target:
            return asset
    return None


def _candidate_status_for_quality(asset: dict) -> str:
    signals = asset.get("quality_signals")
    status = signals.get("visual_quality_status", "") if isinstance(signals, dict) else ""
    if status == "usable":
        return "usable_candidate"
    if status == "reject":
        return "reject_visual_quality"
    return "needs_visual_quality_check"


def _asset_candidate(asset: dict, *, include_label: bool = False) -> dict:
    candidate = {
        "filename": asset.get("filename", ""),
        "path": asset.get("path", ""),
        "width": asset.get("width", 0),
        "height": asset.get("height", 0),
        "size_bytes": asset.get("size_bytes", 0),
    }
    if include_label:
        candidate["label"] = asset.get("label", "")
        candidate["extraction_level"] = asset.get("extraction_level", "figure")
        if isinstance(asset.get("quality_signals"), dict):
            candidate["quality_signals"] = asset.get("quality_signals")
        candidate["candidate_status"] = _candidate_status_for_quality(asset)
    return candidate


def attach_candidate_images(
    items: list[dict],
    page_assets: list[dict],
    image_assets: list[dict],
    figure_assets: list[dict] | None = None,
) -> list[dict]:
    figure_assets = figure_assets or []

    image_map: dict[int, list[dict]] = {}
    for image in image_assets:
        if not isinstance(image, dict):
            continue
        page_number = int(image.get("page_number", 0) or 0)
        if page_number <= 0:
            continue
        image_map.setdefault(page_number, []).append(image)

    figure_map: dict[int, list[dict]] = {}
    for asset in figure_assets:
        if not isinstance(asset, dict):
            continue
        page_number = int(asset.get("page_number", 0) or 0)
        if page_number <= 0:
            continue
        figure_map.setdefault(page_number, []).append(asset)

    has_visual = set()
    for page in page_assets:
        if not isinstance(page, dict):
            continue
        pn = int(page.get("page_number", 0) or 0)
        img_count = int(page.get("image_count", 0) or 0)
        fig_count = int(page.get("figure_count", 0) or 0)
        if img_count > 0 or fig_count > 0:
            has_visual.add(pn)
    pages_with_images = [
        page for page in page_assets
        if isinstance(page, dict) and int(page.get("page_number", 0) or 0) in has_visual
    ]

    for index, item in enumerate(items):
        item_id = str(item.get("id", ""))

        fig_match = _match_figure_asset(item_id, figure_assets)
        if fig_match:
            item["figure_asset_candidate"] = _asset_candidate(fig_match, include_label=True)

        variants = label_variants(item_id)
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

            if score <= 0:
                continue

            candidates.append(
                {
                    "page_number": page_number,
                    "score": score,
                    "matched_terms": matched_terms[:6],
                    "snippet": snippets[0] if snippets else normalize_whitespace(str(page.get("text_preview", "")))[:220],
                    "images": [
                        _asset_candidate(img)
                        for img in image_map.get(page_number, [])[:3]
                    ],
                    "figure_assets": [
                        _asset_candidate(asset, include_label=True)
                        for asset in figure_map.get(page_number, [])[:3]
                    ],
                }
            )

        candidates.sort(key=lambda candidate: (-candidate["score"], candidate["page_number"]))
        item["candidate_pages"] = candidates[:3]
        if fig_match:
            item["matching_strategy"] = "figure-asset-candidate"
        elif candidates:
            item["matching_strategy"] = "page-proximity-and-caption-cues"
        else:
            item["candidate_status"] = "no_match_found"
            item["matching_strategy"] = "no-match-found"
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
    figure_assets = data.get("figure_assets", []) if isinstance(data.get("figure_assets"), list) else []
    items = build_figure_items(evidence_pack, limit=args.max_items)
    items = attach_candidate_images(items, page_assets, image_assets, figure_assets)
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
