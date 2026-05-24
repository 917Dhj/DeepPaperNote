#!/usr/bin/env python3
"""Create a full figure/table decision table from source captions and figure planning."""

from __future__ import annotations

import argparse
import re
from typing import Any

from common import (
    caption_label_key,
    caption_preference_score,
    emit,
    maybe_load_json_record,
    normalize_whitespace,
)

DECISION_VALUES = {"insert", "placeholder", "low_priority", "visual_defect", "skip"}
INSERTABLE_KINDS = {"figure", "table"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan figure/table decisions")
    p.add_argument("--source-manifest", required=True, help="Source manifest JSON path or string.")
    p.add_argument("--figures", default="", help="Figure plan JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    return p


def load_record(value: str) -> dict[str, Any]:
    record = maybe_load_json_record(value)
    if record is None:
        raise SystemExit(f"Expected JSON object for {value!r}.")
    return record


def normalize_label(label: str) -> str:
    text = normalize_whitespace(label).lower()
    text = text.replace("figure", "fig")
    text = re.sub(r"\bfig\.\s*", "fig ", text)
    text = re.sub(r"\btable\.\s*", "table ", text)
    return normalize_whitespace(text)


def caption_items(source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    captions = (
        source_manifest.get("captions", {})
        if isinstance(source_manifest.get("captions"), dict)
        else {}
    )
    grouped: dict[str, dict[str, Any]] = {}
    scores: dict[str, int] = {}
    order: list[str] = []
    for kind, key in (("figure", "figures"), ("table", "tables")):
        for item in captions.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            label = normalize_whitespace(str(item.get("id", "")))
            caption = normalize_whitespace(str(item.get("caption", "")))
            if not label and not caption:
                continue
            page = item.get("page") or item.get("page_number") or 0
            group_key = caption_label_key(label)
            if not group_key:
                continue
            candidate = {
                "kind": kind,
                "label": label,
                "caption": caption,
                "page": page,
                "pages": item.get("pages") or ([page] if page else []),
                "section_id": item.get("section_id", ""),
            }
            score = caption_preference_score(label, caption)
            if group_key not in grouped:
                grouped[group_key] = candidate
                scores[group_key] = score
                order.append(group_key)
                continue
            if score > scores[group_key]:
                grouped[group_key] = candidate
                scores[group_key] = score
    return [grouped[key] for key in order]


def planned_items(figures_wrapper: dict[str, Any]) -> dict[str, dict[str, Any]]:
    figure_plan = (
        figures_wrapper.get("figure_plan", {})
        if isinstance(figures_wrapper.get("figure_plan"), dict)
        else {}
    )
    planned: dict[str, dict[str, Any]] = {}
    for item in figure_plan.get("figures", []) or []:
        if not isinstance(item, dict):
            continue
        label = normalize_whitespace(str(item.get("id", "")))
        if label:
            planned[normalize_label(label)] = item
    return planned


def quality_status(plan_item: dict[str, Any]) -> str:
    candidate = plan_item.get("figure_asset_candidate")
    if not isinstance(candidate, dict):
        return ""
    status = normalize_whitespace(str(candidate.get("candidate_status", "")))
    if status:
        return status
    signals = candidate.get("quality_signals", {})
    if isinstance(signals, dict):
        return normalize_whitespace(str(signals.get("visual_quality_status", "")))
    return ""


def figure_asset_candidate(plan_item: dict[str, Any]) -> dict[str, Any]:
    candidate = plan_item.get("figure_asset_candidate")
    return candidate if isinstance(candidate, dict) else {}


def source_image_path(plan_item: dict[str, Any]) -> str:
    return normalize_whitespace(str(figure_asset_candidate(plan_item).get("path", "")))


def source_image_filename(plan_item: dict[str, Any]) -> str:
    candidate = figure_asset_candidate(plan_item)
    filename = normalize_whitespace(str(candidate.get("filename", "")))
    if filename:
        return filename
    path = source_image_path(plan_item)
    return path.rsplit("/", 1)[-1] if path else ""


def should_insert(caption: dict[str, Any], plan_item: dict[str, Any], status: str) -> bool:
    if status != "usable_candidate":
        return False
    if caption.get("kind") not in INSERTABLE_KINDS:
        return False
    return bool(source_image_path(plan_item))


def decide(caption: dict[str, Any], plan_item: dict[str, Any] | None) -> dict[str, Any]:
    label = normalize_whitespace(str(caption.get("label", "")))
    fallback_caption = normalize_whitespace(str(caption.get("caption", "")))[:40]
    base = {
        "item_id": f"{caption.get('kind', 'item')}:{label or fallback_caption}",
        "source_id": label,
        "kind": caption.get("kind", ""),
        "label": label,
        "caption": caption.get("caption", ""),
        "pages": caption.get("pages", []),
        "section_id": caption.get("section_id", ""),
        "decision": "low_priority",
        "reason": "caption_detected_but_not_selected_by_figure_plan",
        "skip_reason": "",
        "visual_quality_status": "",
        "priority": 99,
        "target_section": "",
    }
    if not plan_item:
        return base

    status = quality_status(plan_item)
    base["priority"] = int(plan_item.get("priority", 99) or 99)
    base["target_section"] = plan_item.get("section", "")
    base["plan_kind"] = plan_item.get("kind", "")
    base["visual_quality_status"] = status
    base["reason"] = plan_item.get("reason", "") or "selected_by_figure_plan"
    filename = source_image_filename(plan_item)
    image_path = source_image_path(plan_item)
    if filename:
        base["source_image_filename"] = filename
        base["relative_markdown_embed"] = f"![{label or filename}](images/{filename})"
    if image_path:
        base["source_image_path"] = image_path
    if status in {"reject", "reject_visual_quality"}:
        base["decision"] = "visual_defect"
        base["skip_reason"] = "visual_quality_gate_rejected_candidate"
    elif should_insert(caption, plan_item, status):
        base["decision"] = "insert"
        base["materialization_status"] = "pending"
        base["skip_reason"] = ""
    else:
        base["decision"] = "placeholder"
        if status == "usable_candidate":
            base["skip_reason"] = "asset_candidate_missing"
        elif status:
            base["skip_reason"] = "visual_quality_requires_review"
        else:
            base["skip_reason"] = "asset_candidate_missing"
    return base


def build_decisions(
    source_manifest: dict[str, Any],
    figures_wrapper: dict[str, Any],
) -> list[dict[str, Any]]:
    planned = planned_items(figures_wrapper)
    decisions = [
        decide(caption, planned.get(normalize_label(str(caption.get("label", "")))))
        for caption in caption_items(source_manifest)
    ]
    for decision in decisions:
        if decision["decision"] not in DECISION_VALUES:
            decision["decision"] = "skip"
            decision["skip_reason"] = "invalid_decision_normalized_to_skip"
    return decisions


def main() -> None:
    args = parser().parse_args()
    source_manifest = load_record(args.source_manifest)
    figures = load_record(args.figures) if args.figures else {}
    _assets = load_record(args.assets) if args.assets else {}
    decisions = build_decisions(source_manifest, figures)
    payload = {
        "status": "ok",
        "script": "plan_figure_table_decisions.py",
        "paper_id": args.paper_id or source_manifest.get("paper_id", ""),
        "decisions": decisions,
        "summary": {
            "total_items": len(decisions),
            "by_decision": {
                value: sum(1 for item in decisions if item.get("decision") == value)
                for value in sorted(DECISION_VALUES)
            },
        },
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
