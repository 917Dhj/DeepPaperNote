#!/usr/bin/env python3
"""Assemble a model-facing synthesis bundle from deterministic DeepPaperNote artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from common import maybe_load_json_record, normalize_whitespace


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "build synthesis bundle")
    p.add_argument("--metadata", required=True, help="Metadata JSON path or string.")
    p.add_argument("--evidence", required=True, help="Evidence JSON path or string.")
    p.add_argument("--figures", default="", help="Figure plan JSON path or string.")
    p.add_argument("--assets", default="", help="PDF assets JSON path or string.")
    p.add_argument("--output", default="", help="Output JSON path.")
    return p


def load_record(value: str) -> dict:
    return maybe_load_json_record(value) or {}


def top_items(evidence_pack: dict, key: str, *, limit: int = 6) -> list[dict]:
    results: list[dict] = []
    for item in (evidence_pack.get(key, []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        evidence = normalize_whitespace(str(item.get("evidence", "")))
        if not evidence:
            continue
        results.append(
            {
                "evidence": evidence,
                "source_section": normalize_whitespace(str(item.get("source_section", ""))),
                "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
            }
        )
    return results


def section_previews(evidence_pack: dict, *, limit: int = 10) -> list[dict]:
    previews: list[dict] = []
    for item in (evidence_pack.get("sections", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        previews.append(
            {
                "name": normalize_whitespace(str(item.get("name", ""))),
                "preview": normalize_whitespace(str(item.get("preview", ""))),
                "length": item.get("length", 0),
            }
        )
    return previews


def sanitize_page_assets(assets_wrapper: dict, *, limit: int = 24) -> list[dict]:
    sanitized: list[dict] = []
    for item in (assets_wrapper.get("page_assets", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "page_number": item.get("page_number", 0),
                "searchable_text_chars": item.get("searchable_text_chars", 0),
                "text_extraction_method": item.get("text_extraction_method", ""),
                "ocr_used": item.get("ocr_used", False),
                "image_count": item.get("image_count", 0),
                "text_preview": item.get("text_preview", ""),
            }
        )
    return sanitized


def bundle(metadata: dict, evidence_wrapper: dict, figures_wrapper: dict, assets_wrapper: dict) -> dict:
    evidence_pack = evidence_wrapper.get("evidence_pack", {}) if isinstance(evidence_wrapper.get("evidence_pack"), dict) else {}
    figure_plan = figures_wrapper.get("figure_plan", {}) if isinstance(figures_wrapper.get("figure_plan"), dict) else {}

    return {
        "status": "ok",
        "script": "build_synthesis_bundle.py",
        "paper_id": metadata.get("paper_id") or evidence_wrapper.get("paper_id", ""),
        "title": metadata.get("title") or evidence_wrapper.get("title", ""),
        "metadata": {
            "title": metadata.get("title", ""),
            "translated_title": metadata.get("translated_title", ""),
            "authors": metadata.get("authors", []),
            "affiliations": metadata.get("affiliations", []),
            "year": metadata.get("year", ""),
            "venue": metadata.get("venue", ""),
            "doi": metadata.get("doi", ""),
            "source_url": metadata.get("source_url", ""),
            "abstract": metadata.get("abstract", ""),
            "arxiv_id": metadata.get("arxiv_id", ""),
            "zotero_key": metadata.get("zotero_key", ""),
            "metadata_sources": metadata.get("metadata_sources", []),
        },
        "evidence_quality": evidence_pack.get("evidence_quality", "unknown"),
        "evidence": {
            "problem": top_items(evidence_pack, "problem_evidence"),
            "task": top_items(evidence_pack, "task_evidence"),
            "data": top_items(evidence_pack, "data_evidence"),
            "method": top_items(evidence_pack, "method_evidence"),
            "results": top_items(evidence_pack, "results_evidence"),
            "limitations": top_items(evidence_pack, "limitations_evidence"),
        },
        "section_previews": section_previews(evidence_pack),
        "figure_plan": figure_plan,
        "pdf_assets": {
            "asset_root": assets_wrapper.get("asset_root", ""),
            "images_dir": assets_wrapper.get("images_dir", ""),
            "page_assets": sanitize_page_assets(assets_wrapper),
            "image_assets": assets_wrapper.get("image_assets", []),
            "ocr_available": assets_wrapper.get("ocr_available", False),
        },
        "summary": evidence_wrapper.get("summary", {}),
        "writing_contract": {
            "language": "zh-CN",
            "must_distinguish": [
                "研究问题 vs 任务定义",
                "真实贡献 vs 标题包装",
                "核心结果 vs 好看的结果",
                "作者声称什么 vs 论文没有证明什么",
            ],
            "must_include_sections": [
                "核心信息",
                "一句话总结",
                "研究问题",
                "数据与任务定义",
                "方法主线",
                "关键结果",
                "深度分析",
                "局限",
                "我的笔记",
                "引用",
            ],
            "must_not_do": [
                "不要摘要改写",
                "不要把英文证据原句揉进中文正文",
                "不要把脚本 heuristics 当成论文结论",
            ],
            "planning_rules": [
                "先基于证据做内部 note plan，再写最终笔记",
                "决定哪些部分需要更多篇幅，哪些部分需要 `###` 子标题",
                "复杂论文不能只写扁平的 `##` 结构",
                "优先提炼关键数字、关键比较和论文特有洞察",
            ],
            "figure_rules": [
                "先规划主要图表的占位标签，再决定哪些可以替换成真实图片",
                "如果没有高置信度图像匹配，不要删除占位标签",
                "图注必须保留论文原始编号，例如 Fig. 1、Table 2",
                "如果插入的是局部子图或不完整裁剪，必须明确说明",
                "图可以不全，但文字覆盖必须完整",
            ],
        },
    }


def main() -> None:
    from common import emit

    args = parser().parse_args()
    metadata = load_record(args.metadata)
    evidence = load_record(args.evidence)
    figures = load_record(args.figures) if args.figures else {}
    assets = load_record(args.assets) if args.assets else {}
    emit(bundle(metadata, evidence, figures, assets), args.output)


if __name__ == "__main__":
    main()
