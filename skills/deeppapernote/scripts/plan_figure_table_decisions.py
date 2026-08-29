#!/usr/bin/env python3
"""Create a full figure/table decision table from source captions and figure planning."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import (
    caption_label_key,
    caption_preference_score,
    emit,
    file_sha256,
    maybe_load_json_record,
    normalize_whitespace,
    runtime_config,
)
from contracts import WRITING_CONTRACT_RULES
from extract_pdf_assets import _render_crop, save_image_bytes
from localization import normalize_output_language, require_artifact_output_language
from source_corpus import SourceCorpusLoadError, load_source_corpus

DECISION_VALUES = set(WRITING_CONTRACT_RULES["figure_decision_values"])
INSERTABLE_KINDS = set(WRITING_CONTRACT_RULES["usable_insert_candidate"]["kinds"])
REVIEW_RENDER_DPI = int(
    WRITING_CONTRACT_RULES["visual_review_contract"]["selected_render_dpi"]
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan figure/table decisions")
    p.add_argument("--source-manifest", default="", help="Source manifest JSON path or string.")
    p.add_argument("--figures", default="", help="Figure plan JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument(
        "--review-decisions",
        default="",
        help="Existing decision JSON whose requested bounded repairs should be applied.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    p.add_argument(
        "--language",
        default="",
        help="Run Override for output language: en or zh-CN.",
    )
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


def input_is_file(value: str) -> bool:
    if not value or value.strip().startswith("{"):
        return False
    try:
        return Path(value).expanduser().is_file()
    except OSError:
        return False


def normalized_caption_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    scores: dict[str, int] = {}
    order: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        label = normalize_whitespace(str(item.get("id") or item.get("label") or ""))
        caption = normalize_whitespace(str(item.get("caption", "")))
        if not label and not caption:
            continue
        page = item.get("page") or item.get("page_number") or 0
        group_key = caption_label_key(label)
        if not group_key:
            continue
        candidate = {
            "kind": item.get("kind", ""),
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


def caption_items(source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    captions = (
        source_manifest.get("captions", {})
        if isinstance(source_manifest.get("captions"), dict)
        else {}
    )
    raw_items: list[dict[str, Any]] = []
    for kind, key in (("figure", "figures"), ("table", "tables")):
        for item in captions.get(key, []) or []:
            if isinstance(item, dict):
                raw_items.append({**dict(item), "kind": kind})
    return normalized_caption_items(raw_items)


def source_caption_items(
    source_manifest: dict[str, Any],
    source_manifest_input: str = "",
) -> list[dict[str, Any]]:
    if input_is_file(source_manifest_input):
        try:
            corpus = load_source_corpus(source_manifest_input)
        except SourceCorpusLoadError as exc:
            raise SystemExit(str(exc)) from exc
        return normalized_caption_items(corpus.caption_items())
    return caption_items(source_manifest)


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
    # Split on both separators so a Windows-style backslash path does not get
    # returned whole (rsplit("/") alone leaves "C:\\...\\fig.png" intact).
    return re.split(r"[\\/]", path)[-1] if path else ""


def should_review(caption: dict[str, Any], plan_item: dict[str, Any], status: str) -> bool:
    if status != "usable_candidate":
        return False
    if caption.get("kind") not in INSERTABLE_KINDS:
        return False
    path = source_image_path(plan_item)
    return bool(path and Path(path).expanduser().is_file())


def matched_figure_asset(assets_wrapper: dict[str, Any], label: str) -> dict[str, Any]:
    target = normalize_label(label)
    for asset in assets_wrapper.get("figure_assets", []) or []:
        if isinstance(asset, dict) and normalize_label(str(asset.get("label", ""))) == target:
            return asset
    return {}


def normalized_bbox(page_rect, bbox: list[float]) -> list[float]:
    width = max(float(page_rect.width), 1.0)
    height = max(float(page_rect.height), 1.0)
    return [
        round((bbox[0] - page_rect.x0) / width, 6),
        round((bbox[1] - page_rect.y0) / height, 6),
        round((bbox[2] - page_rect.x0) / width, 6),
        round((bbox[3] - page_rect.y0) / height, 6),
    ]


def prepare_review_candidate(
    caption: dict[str, Any],
    plan_item: dict[str, Any],
    assets_wrapper: dict[str, Any],
) -> dict[str, Any]:
    image_path = source_image_path(plan_item)
    filename = source_image_filename(plan_item)
    asset = matched_figure_asset(assets_wrapper, str(caption.get("label", "")))
    pdf_path = Path(str(assets_wrapper.get("pdf_path", ""))).expanduser()
    bbox = asset.get("bbox_pt", []) if isinstance(asset.get("bbox_pt"), list) else []
    page_number = int(asset.get("page_number", 0) or 0)
    evidence = {
        "candidate_path": image_path,
        "page_preview_path": str(asset.get("page_preview_path", "")),
        "source_pdf_path": str(pdf_path) if str(pdf_path) != "." else "",
        "source_page": page_number,
        "caption": caption.get("caption", ""),
        "bbox_pt": bbox,
        "normalized_bbox": [],
        "render_dpi": 0,
    }
    if pdf_path.is_file() and page_number > 0 and len(bbox) == 4:
        doc = None
        try:
            from common import fitz

            if fitz is not None:
                doc = fitz.open(pdf_path.resolve())
                page = doc[page_number - 1]
                source = Path(image_path).expanduser()
                output_path = source.with_name(f"{source.stem}_review.png")
                save_image_bytes(
                    output_path,
                    _render_crop(page, tuple(float(value) for value in bbox), REVIEW_RENDER_DPI),
                )
                image_path = str(output_path)
                filename = output_path.name
                evidence["candidate_path"] = image_path
                evidence["normalized_bbox"] = normalized_bbox(page.rect, bbox)
                evidence["render_dpi"] = REVIEW_RENDER_DPI
        except (OSError, RuntimeError, ValueError, IndexError):
            pass
        finally:
            if doc is not None:
                doc.close()
    return {
        "path": image_path,
        "filename": filename,
        "sha256": file_sha256(image_path),
        "review_evidence": evidence,
    }


def validate_normalized_bbox(value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 4:
        raise SystemExit("revised_bbox must be [x0, y0, x1, y1].")
    if not all(
        isinstance(item, (int, float)) and not isinstance(item, bool)
        for item in value
    ):
        raise SystemExit("revised_bbox coordinates must be numeric.")
    bbox = [float(item) for item in value]
    x0, y0, x1, y1 = bbox
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise SystemExit(
            "revised_bbox coordinates must be ordered and within [0, 1]."
        )
    return bbox


def apply_requested_repairs(wrapper: dict[str, Any]) -> dict[str, Any]:
    decisions = wrapper.get("decisions", [])
    if not isinstance(decisions, list):
        raise SystemExit("--review-decisions requires a decisions list.")
    contract = WRITING_CONTRACT_RULES["visual_review_contract"]
    repairable = set(contract["repairable_failure_reasons"])
    repair_limit = int(contract["repair_limit"])

    for item in decisions:
        if not isinstance(item, dict):
            continue
        review = item.get("visual_review", {})
        if not isinstance(review, dict) or review.get("status") != "repair_requested":
            continue
        source_path = Path(str(item.get("source_image_path", ""))).expanduser()
        current_sha256 = file_sha256(str(source_path))
        if not current_sha256 or review.get("reviewed_asset_sha256") != current_sha256:
            raise SystemExit("Bounded crop repair requires a current reviewed asset SHA-256.")
        attempts = int(review.get("repair_attempts", 0) or 0)
        if attempts >= repair_limit:
            review.update(
                {
                    "status": "fail",
                    "failure_reason": "repair_limit_exhausted",
                    "reviewed_asset_sha256": current_sha256,
                }
            )
            item["decision"] = "visual_defect"
            item["skip_reason"] = "repair_limit_exhausted"
            continue
        failure_reason = normalize_whitespace(str(review.get("failure_reason", "")))
        if failure_reason not in repairable:
            raise SystemExit(
                f"Failure reason is not repairable by recropping: {failure_reason}"
            )
        revised_bbox = validate_normalized_bbox(review.get("revised_bbox"))
        evidence = item.get("review_evidence", {})
        if not isinstance(evidence, dict):
            raise SystemExit("Bounded crop repair requires review_evidence.")
        pdf_path = Path(str(evidence.get("source_pdf_path", ""))).expanduser()
        page_number = int(evidence.get("source_page", 0) or 0)
        if not pdf_path.is_file() or page_number <= 0:
            raise SystemExit("Bounded crop repair requires a source PDF and page.")

        from common import fitz

        if fitz is None:
            raise SystemExit("Bounded crop repair requires PyMuPDF (`fitz`).")
        doc = fitz.open(pdf_path.resolve())
        try:
            page = doc[page_number - 1]
            page_rect = page.rect
            x0, y0, x1, y1 = revised_bbox
            bbox_pt = [
                page_rect.x0 + x0 * page_rect.width,
                page_rect.y0 + y0 * page_rect.height,
                page_rect.x0 + x1 * page_rect.width,
                page_rect.y0 + y1 * page_rect.height,
            ]
            repair_path = source_path.with_name(
                f"{source_path.stem}_repair{attempts + 1}.png"
            )
            save_image_bytes(
                repair_path,
                _render_crop(page, tuple(bbox_pt), REVIEW_RENDER_DPI),
            )
        finally:
            doc.close()

        repaired_sha256 = file_sha256(str(repair_path))
        item["decision"] = "review_pending"
        item["source_image_path"] = str(repair_path)
        item["source_image_filename"] = repair_path.name
        item["source_image_sha256"] = repaired_sha256
        if item.get("relative_markdown_embed"):
            item["relative_markdown_embed"] = (
                f"![{item.get('source_id') or repair_path.name}]"
                f"(images/{repair_path.name})"
            )
        evidence.update(
            {
                "candidate_path": str(repair_path),
                "bbox_pt": [round(value, 6) for value in bbox_pt],
                "normalized_bbox": revised_bbox,
                "render_dpi": REVIEW_RENDER_DPI,
            }
        )
        item["review_evidence"] = evidence
        item["visual_review"] = {
            "status": "pending",
            "reviewed_asset_sha256": "",
            "preserved_scientific_elements": [],
            "omitted_scientific_elements": [],
            "notes": "",
            "failure_reason": "",
            "repair_attempts": attempts + 1,
            "revised_bbox": revised_bbox,
        }
    wrapper["decisions"] = decisions
    return wrapper


def decide(
    caption: dict[str, Any],
    plan_item: dict[str, Any] | None,
    assets_wrapper: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    assets_wrapper = assets_wrapper or {}
    prepared = (
        prepare_review_candidate(caption, plan_item, assets_wrapper)
        if status == "usable_candidate"
        else {}
    )
    filename = str(prepared.get("filename") or source_image_filename(plan_item))
    image_path = str(prepared.get("path") or source_image_path(plan_item))
    if filename:
        base["source_image_filename"] = filename
        base["relative_markdown_embed"] = f"![{label or filename}](images/{filename})"
    if image_path:
        base["source_image_path"] = image_path
    if status in {"reject", "reject_visual_quality"}:
        base["decision"] = "visual_defect"
        base["skip_reason"] = "visual_quality_gate_rejected_candidate"
    elif should_review(caption, plan_item, status):
        base["decision"] = "review_pending"
        base["materialization_status"] = "pending"
        base["skip_reason"] = ""
        base["source_image_sha256"] = str(prepared.get("sha256") or file_sha256(image_path))
        base["review_evidence"] = prepared.get("review_evidence", {})
        base["visual_review"] = {
            "status": "pending",
            "reviewed_asset_sha256": "",
            "preserved_scientific_elements": [],
            "omitted_scientific_elements": [],
            "notes": "",
            "failure_reason": "",
            "repair_attempts": 0,
            "revised_bbox": [],
        }
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
    source_manifest_input: str = "",
    assets_wrapper: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    planned = planned_items(figures_wrapper)
    decisions = [
        decide(
            caption,
            planned.get(normalize_label(str(caption.get("label", "")))),
            assets_wrapper,
        )
        for caption in source_caption_items(source_manifest, source_manifest_input)
    ]
    for decision in decisions:
        if decision["decision"] not in DECISION_VALUES:
            decision["decision"] = "skip"
            decision["skip_reason"] = "invalid_decision_normalized_to_skip"
    return decisions


def main() -> None:
    args = parser().parse_args()
    language = normalize_output_language(
        runtime_config(cli_overrides={"output_language": args.language})["output_language"]
    )
    if args.review_decisions:
        payload = load_record(args.review_decisions)
        require_artifact_output_language(payload, "Figure/Table Decisions", language)
        payload = apply_requested_repairs(payload)
        payload["status"] = "ok"
        payload["script"] = "plan_figure_table_decisions.py"
        emit(payload, args.output)
        return
    if not args.source_manifest:
        raise SystemExit(
            "plan_figure_table_decisions.py requires --source-manifest "
            "or --review-decisions."
        )
    source_manifest = load_record(args.source_manifest)
    figures = load_record(args.figures) if args.figures else {}
    require_artifact_output_language(figures, "Figure Plan", language)
    assets = load_record(args.assets) if args.assets else {}
    decisions = build_decisions(
        source_manifest,
        figures,
        args.source_manifest,
        assets,
    )
    payload = {
        "status": "ok",
        "script": "plan_figure_table_decisions.py",
        "output_language": language,
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
