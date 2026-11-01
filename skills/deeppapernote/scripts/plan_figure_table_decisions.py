#!/usr/bin/env python3
"""Create a full figure/table decision table from source captions and figure planning."""

from __future__ import annotations

import argparse
import json
import re
import sys
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
from extract_pdf_assets import _render_crop, _unique_figure_asset_filename, save_image_bytes
from lint_grounding import visual_review_evidence_is_valid
from localization import normalize_output_language, require_artifact_output_language
from source_corpus import SourceCorpusLoadError, load_source_corpus
from write_obsidian_note import atomic_write_note

DECISION_VALUES = set(WRITING_CONTRACT_RULES["figure_decision_values"])
INSERTABLE_KINDS = set(WRITING_CONTRACT_RULES["usable_insert_candidate"]["kinds"])
VISUAL_REVIEW = WRITING_CONTRACT_RULES["visual_review_contract"]
REVIEW_RENDER_DPI = int(VISUAL_REVIEW["selected_render_dpi"])
REPAIRABLE_FAILURES = set(VISUAL_REVIEW["repairable_failure_reasons"])
TERMINAL_FAILURES = set(VISUAL_REVIEW["terminal_failure_reasons"])
REPAIR_LIMIT = int(VISUAL_REVIEW["repair_limit"])


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "plan figure/table decisions")
    p.add_argument("--source-manifest", default="", help="Source manifest JSON path or string.")
    p.add_argument("--figures", default="", help="Figure plan JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument(
        "--asset-subdir",
        default="images",
        help="Paper-relative images directory from save preflight.",
    )
    p.add_argument("--output", default="", help="Output JSON path.")
    p.add_argument("--paper-id", default="", help="Canonical paper id.")
    p.add_argument(
        "--language",
        default="",
        help="Run Override for output language: en or zh-CN.",
    )
    return p


def review_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="plan_figure_table_decisions.py review",
        description="Record the model's Visual Review verdict for one item.",
    )
    p.add_argument("--decisions", required=True, help="Decisions JSON file, updated in place.")
    p.add_argument("--item", required=True, help='Label such as "Figure 1".')
    p.add_argument("--verdict", required=True, choices=("pass", "fail", "repair"))
    p.add_argument(
        "--preserved",
        action="append",
        default=[],
        help="Scientific element seen in the crop; repeat for each. Required by pass.",
    )
    p.add_argument(
        "--omitted",
        action="append",
        default=[],
        help="Scientific element the crop lost; repeat for each. Not allowed on pass.",
    )
    p.add_argument("--notes", default="", help="Short review note.")
    p.add_argument("--failure", default="", help="Contract failure reason for fail or repair.")
    p.add_argument(
        "--bbox",
        default="",
        help="Page-normalized x0,y0,x1,y1 read off the grid preview. Required by repair.",
    )
    return p


def promote_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="plan_figure_table_decisions.py promote",
        description="Send a Figure/Table the planner left out into Visual Review.",
    )
    p.add_argument("--decisions", required=True, help="Decisions JSON file, updated in place.")
    p.add_argument("--assets", required=True, help="PDF assets JSON path.")
    p.add_argument("--item", required=True, help='Label such as "Figure 9".')
    p.add_argument(
        "--bbox",
        default="",
        help="Page-normalized x0,y0,x1,y1 read off the grid preview, when no usable crop exists.",
    )
    p.add_argument("--page", type=int, default=0, help="Page of --bbox; defaults to the caption's.")
    return p


def load_record(value: str) -> dict[str, Any]:
    record = maybe_load_json_record(value)
    if record is None:
        raise SystemExit(f"Expected JSON object for {value!r}.")
    return record


def normalize_label(label: str) -> str:
    return caption_label_key(label)


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


def parse_bbox(value: str) -> list[float]:
    try:
        return validate_normalized_bbox([float(part) for part in value.split(",")])
    except ValueError as exc:
        raise SystemExit("--bbox must be four numbers: x0,y0,x1,y1.") from exc


def render_page_region(
    pdf_path: Path,
    page_number: int,
    normalized: list[float],
    output_path: Path,
) -> list[float]:
    """Render a page-normalized region from the PDF and return it in page points."""
    from common import fitz

    if fitz is None:
        raise SystemExit("Rendering a review crop requires PyMuPDF (`fitz`).")
    if not pdf_path.is_file():
        raise SystemExit(f"Rendering a review crop requires the source PDF: {pdf_path}")
    doc = fitz.open(pdf_path.resolve())
    try:
        if not 1 <= page_number <= doc.page_count:
            raise SystemExit(f"Source PDF has no page {page_number}.")
        page = doc[page_number - 1]
        page_rect = page.rect
        x0, y0, x1, y1 = normalized
        bbox_pt = [
            page_rect.x0 + x0 * page_rect.width,
            page_rect.y0 + y0 * page_rect.height,
            page_rect.x0 + x1 * page_rect.width,
            page_rect.y0 + y1 * page_rect.height,
        ]
        save_image_bytes(output_path, _render_crop(page, tuple(bbox_pt), REVIEW_RENDER_DPI))
    finally:
        doc.close()
    return [round(value, 6) for value in bbox_pt]


def pending_visual_review(
    repair_attempts: int = 0,
    revised_bbox: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "reviewed_asset_sha256": "",
        "preserved_scientific_elements": [],
        "omitted_scientific_elements": [],
        "notes": "",
        "failure_reason": "",
        "repair_attempts": repair_attempts,
        "revised_bbox": revised_bbox or [],
    }


def apply_repair(item: dict[str, Any], asset_subdir: str) -> None:
    """Recrop a repair_requested item once, or close it once the repair limit is spent."""
    review = item["visual_review"]
    attempts = int(review.get("repair_attempts", 0) or 0)
    if attempts >= REPAIR_LIMIT:
        review.update({"status": "fail", "failure_reason": "repair_limit_exhausted"})
        item["decision"] = "visual_defect"
        item["skip_reason"] = "repair_limit_exhausted"
        return
    source_path = Path(str(item.get("source_image_path", ""))).expanduser()
    revised_bbox = review["revised_bbox"]
    evidence = item["review_evidence"]
    repair_path = source_path.with_name(f"{source_path.stem}_repair{attempts + 1}.png")
    bbox_pt = render_page_region(
        Path(str(evidence.get("source_pdf_path", ""))).expanduser(),
        int(evidence.get("source_page", 0) or 0),
        revised_bbox,
        repair_path,
    )
    item["decision"] = "review_pending"
    item["source_image_path"] = str(repair_path)
    item["source_image_filename"] = repair_path.name
    item["source_image_sha256"] = file_sha256(str(repair_path))
    if item.get("relative_markdown_embed"):
        item["relative_markdown_embed"] = (
            f"![{item.get('source_id') or repair_path.name}]"
            f"({asset_subdir}/{repair_path.name})"
        )
    evidence.update(
        {
            "candidate_path": str(repair_path),
            "bbox_pt": bbox_pt,
            "normalized_bbox": revised_bbox,
            "render_dpi": REVIEW_RENDER_DPI,
        }
    )
    item["visual_review"] = pending_visual_review(attempts + 1, revised_bbox)


def decide(
    caption: dict[str, Any],
    plan_item: dict[str, Any] | None,
    assets_wrapper: dict[str, Any] | None = None,
    asset_subdir: str = "images",
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
        base["relative_markdown_embed"] = f"![{label or filename}]({asset_subdir}/{filename})"
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
        base["visual_review"] = pending_visual_review()
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
    asset_subdir: str = "images",
) -> list[dict[str, Any]]:
    planned = planned_items(figures_wrapper)
    decisions = [
        decide(
            caption,
            planned.get(normalize_label(str(caption.get("label", "")))),
            assets_wrapper,
            checked_asset_subdir(asset_subdir),
        )
        for caption in source_caption_items(source_manifest, source_manifest_input)
    ]
    for decision in decisions:
        if decision["decision"] not in DECISION_VALUES:
            decision["decision"] = "skip"
            decision["skip_reason"] = "invalid_decision_normalized_to_skip"
    return decisions


def checked_asset_subdir(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"images(?:/[0-9a-f]{64})?", value):
        raise SystemExit("Asset directory must be images or images/<source-sha256> from preflight.")
    return value


def decision_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_items": len(decisions),
        "by_decision": {
            value: sum(1 for item in decisions if item.get("decision") == value)
            for value in sorted(DECISION_VALUES)
        },
    }


def load_decisions(path: str) -> dict[str, Any]:
    if not input_is_file(path):
        raise SystemExit(f"--decisions must be the decisions JSON file: {path}")
    wrapper = load_record(path)
    if not isinstance(wrapper.get("decisions"), list):
        raise SystemExit("--decisions requires a decisions list.")
    return wrapper


def item_label(item: dict[str, Any]) -> str:
    return normalize_whitespace(str(item.get("source_id") or item.get("label") or ""))


def find_item(wrapper: dict[str, Any], label: str) -> dict[str, Any]:
    target = normalize_label(label)
    for item in wrapper["decisions"]:
        if isinstance(item, dict) and normalize_label(item_label(item)) == target:
            return item
    raise SystemExit(f"No decision item matches {label!r}.")


def finish_item_command(path: str, wrapper: dict[str, Any], item: dict[str, Any]) -> None:
    """Save the whole file and report what the model needs to look at next."""
    decisions = wrapper["decisions"]
    wrapper["summary"] = decision_summary(decisions)
    text = json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n"
    atomic_write_note(Path(path).expanduser(), text)
    evidence = item.get("review_evidence", {})
    emit(
        {
            "status": "ok",
            "script": "plan_figure_table_decisions.py",
            "item": item_label(item),
            "decision": item.get("decision", ""),
            "failure_reason": item.get("visual_review", {}).get("failure_reason", ""),
            "candidate_path": evidence.get("candidate_path", ""),
            "page_preview_path": evidence.get("page_preview_path", ""),
            "normalized_bbox": evidence.get("normalized_bbox", []),
            "review_pending_items": wrapper["summary"]["by_decision"]["review_pending"],
        }
    )


def verdict_failure(args: argparse.Namespace, attempts: int) -> str:
    """Check that the flags fit the verdict and return its failure reason."""
    if args.verdict == "pass":
        if args.failure or args.omitted or args.bbox:
            raise SystemExit("--verdict pass takes no --failure, --omitted, or --bbox.")
        if not args.preserved:
            raise SystemExit("--verdict pass requires at least one --preserved element.")
        return ""
    if args.verdict == "repair":
        if args.failure not in REPAIRABLE_FAILURES:
            raise SystemExit(f"Failure reason is not repairable by recropping: {args.failure}")
        if not args.bbox:
            raise SystemExit("--verdict repair requires --bbox.")
        return args.failure
    if args.bbox:
        raise SystemExit("--verdict fail takes no --bbox.")
    if args.failure in REPAIRABLE_FAILURES and attempts < REPAIR_LIMIT:
        raise SystemExit(f"{args.failure} is repairable; use --verdict repair with --bbox.")
    if args.failure not in TERMINAL_FAILURES | REPAIRABLE_FAILURES:
        raise SystemExit(f"Unknown failure reason: {args.failure}")
    return args.failure


def run_review(argv: list[str]) -> None:
    args = review_parser().parse_args(argv)
    wrapper = load_decisions(args.decisions)
    asset_subdir = checked_asset_subdir(wrapper.get("asset_subdir", "images"))
    item = find_item(wrapper, args.item)
    label = item_label(item)
    review = item.get("visual_review")
    if not isinstance(review, dict):
        raise SystemExit(f"{label} is not in Visual Review; send it there with promote first.")
    if not visual_review_evidence_is_valid(item):
        raise SystemExit(f"{label} has incomplete review evidence; rerun the planner.")
    failure = verdict_failure(args, int(review.get("repair_attempts", 0) or 0))
    bbox = parse_bbox(args.bbox) if args.bbox else review.get("revised_bbox", [])
    digest = file_sha256(str(item.get("source_image_path", "")))
    if not digest or digest != item.get("source_image_sha256"):
        raise SystemExit(f"{label}: the candidate crop changed since it was planned.")
    review.update(
        {
            "status": {"pass": "pass", "fail": "fail", "repair": "repair_requested"}[args.verdict],
            "reviewed_asset_sha256": digest,
            "preserved_scientific_elements": args.preserved,
            "omitted_scientific_elements": args.omitted,
            "notes": args.notes,
            "failure_reason": failure,
            "revised_bbox": bbox,
        }
    )
    if args.verdict == "repair":
        apply_repair(item, asset_subdir)
    else:
        item["decision"] = "insert" if args.verdict == "pass" else "visual_defect"
        item["skip_reason"] = failure
    finish_item_command(args.decisions, wrapper, item)


def page_preview_path(assets: dict[str, Any], page_number: int) -> str:
    for page in assets.get("page_assets", []) or []:
        if isinstance(page, dict) and page.get("page_number") == page_number:
            return str(page.get("page_preview_path", ""))
    return ""


def crop_is_rejected(asset: dict[str, Any]) -> bool:
    signals = asset.get("quality_signals")
    return isinstance(signals, dict) and signals.get("visual_quality_status") == "reject"


def measured_candidate(
    item: dict[str, Any],
    assets: dict[str, Any],
    page_number: int,
    bbox: list[float],
) -> dict[str, Any]:
    """Build a review candidate from a region the model measured on the grid preview."""
    label = item_label(item)
    filename = _unique_figure_asset_filename(page_number, label, set())
    output_path = Path(str(assets.get("images_dir", ""))).expanduser() / filename.replace(
        ".png", "_review.png"
    )
    pdf_path = Path(str(assets.get("pdf_path", ""))).expanduser()
    bbox_pt = render_page_region(pdf_path, page_number, bbox, output_path)
    return {
        "path": str(output_path),
        "filename": output_path.name,
        "sha256": file_sha256(str(output_path)),
        "review_evidence": {
            "candidate_path": str(output_path),
            "page_preview_path": page_preview_path(assets, page_number),
            "source_pdf_path": str(pdf_path),
            "source_page": page_number,
            "caption": item.get("caption", ""),
            "bbox_pt": bbox_pt,
            "normalized_bbox": bbox,
            "render_dpi": REVIEW_RENDER_DPI,
        },
    }


def run_promote(argv: list[str]) -> None:
    args = promote_parser().parse_args(argv)
    if args.page and not args.bbox:
        raise SystemExit("--page only applies with --bbox.")
    wrapper = load_decisions(args.decisions)
    asset_subdir = checked_asset_subdir(wrapper.get("asset_subdir", "images"))
    assets = load_record(args.assets)
    item = find_item(wrapper, args.item)
    label = item_label(item)
    if isinstance(item.get("visual_review"), dict):
        raise SystemExit(f"{label} is already in Visual Review; record its verdict with review.")
    if item.get("kind") not in INSERTABLE_KINDS:
        raise SystemExit(f"{label} is not a Figure or Table.")
    pages = item.get("pages") or [0]
    page_number = args.page or int(pages[0] or 0)
    asset = matched_figure_asset(assets, label)
    if args.bbox:
        if page_number <= 0:
            raise SystemExit(f"{label} has no caption page; pass --page.")
        prepared = measured_candidate(item, assets, page_number, parse_bbox(args.bbox))
    elif asset and not crop_is_rejected(asset):
        prepared = prepare_review_candidate(item, {"figure_asset_candidate": asset}, assets)
    else:
        raise SystemExit(
            f"{label} has no usable crop. Read a page-normalized x0,y0,x1,y1 off the grid in "
            f"{page_preview_path(assets, page_number) or 'its page preview'} and rerun with "
            "--bbox; add --page if the body is not on that page."
        )
    item.update(
        {
            "decision": "review_pending",
            "promoted": True,
            "skip_reason": "",
            "visual_quality_status": "usable_candidate",
            "materialization_status": "pending",
            "source_image_path": prepared["path"],
            "source_image_filename": prepared["filename"],
            "source_image_sha256": prepared["sha256"],
            "relative_markdown_embed": f"![{label}]({asset_subdir}/{prepared['filename']})",
            "review_evidence": prepared["review_evidence"],
            "visual_review": pending_visual_review(),
        }
    )
    if not visual_review_evidence_is_valid(item):
        raise SystemExit(f"{label} could not be rendered with complete review evidence.")
    finish_item_command(args.decisions, wrapper, item)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "review":
        run_review(argv[1:])
        return
    if argv and argv[0] == "promote":
        run_promote(argv[1:])
        return
    args = parser().parse_args(argv)
    language = normalize_output_language(
        runtime_config(cli_overrides={"output_language": args.language})["output_language"]
    )
    if not args.source_manifest:
        raise SystemExit("plan_figure_table_decisions.py requires --source-manifest.")
    source_manifest = load_record(args.source_manifest)
    figures = load_record(args.figures) if args.figures else {}
    require_artifact_output_language(figures, "Figure Plan", language)
    assets = load_record(args.assets) if args.assets else {}
    decisions = build_decisions(
        source_manifest,
        figures,
        args.source_manifest,
        assets,
        checked_asset_subdir(args.asset_subdir),
    )
    payload = {
        "status": "ok",
        "script": "plan_figure_table_decisions.py",
        "output_language": language,
        "paper_id": args.paper_id or source_manifest.get("paper_id", ""),
        "asset_subdir": args.asset_subdir,
        "decisions": decisions,
        "summary": decision_summary(decisions),
    }
    emit(payload, args.output)


if __name__ == "__main__":
    main()
