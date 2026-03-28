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


def sanitize_equation_candidates(evidence_pack: dict, *, limit: int = 8) -> list[dict]:
    sanitized: list[dict] = []
    for item in (evidence_pack.get("equation_candidates", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        equation = normalize_whitespace(str(item.get("equation", "")))
        if not equation:
            continue
        sanitized.append(
            {
                "equation": equation,
                "source_section": normalize_whitespace(str(item.get("source_section", ""))),
                "kind_hint": normalize_whitespace(str(item.get("kind_hint", ""))),
            }
        )
    return sanitized


def sanitize_candidate_chunks(evidence_pack: dict, *, limit_sections: int = 8, limit_chunks_per_section: int = 8) -> dict[str, list[dict]]:
    sanitized: dict[str, list[dict]] = {}
    candidate_chunks = evidence_pack.get("candidate_chunks", {}) or {}
    if not isinstance(candidate_chunks, dict):
        return sanitized
    for section_name, chunks in list(candidate_chunks.items())[:limit_sections]:
        if not isinstance(chunks, list):
            continue
        kept: list[dict] = []
        for item in chunks[:limit_chunks_per_section]:
            if not isinstance(item, dict):
                continue
            text = normalize_whitespace(str(item.get("text", "")))
            if not text:
                continue
            kept.append(
                {
                    "text": text,
                    "source_section": normalize_whitespace(str(item.get("source_section", ""))),
                    "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
                    "kind_hint": normalize_whitespace(str(item.get("kind_hint", ""))),
                }
            )
        if kept:
            sanitized[normalize_whitespace(str(section_name))] = kept
    return sanitized


def sanitize_section_texts(evidence_pack: dict, *, limit_sections: int = 8, max_chars: int = 4000) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    section_texts = evidence_pack.get("section_texts", {}) or {}
    if not isinstance(section_texts, dict):
        return sanitized
    for section_name, text in list(section_texts.items())[:limit_sections]:
        cleaned = normalize_whitespace(str(text))
        if not cleaned:
            continue
        sanitized[normalize_whitespace(str(section_name))] = cleaned[:max_chars]
    return sanitized


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
        "equation_candidates": sanitize_equation_candidates(evidence_pack),
        "candidate_chunks": sanitize_candidate_chunks(evidence_pack),
        "section_texts": sanitize_section_texts(evidence_pack),
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
                "原始摘要",
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
                "不要把方法论文写成科普式总结",
            ],
            "writer_persona": [
                "把自己当作顶尖人工智能研究员和算法工程师",
                "默认读者是熟悉 Python、PyTorch、训练流程和实验设计的课题组成员",
                "目标是写一份复现级精读笔记，而不是写给大众的科普摘要",
            ],
            "planning_rules": [
                "先基于证据做显式 note_plan，再写最终笔记",
                "note_plan 应该是一个简短、结构化、可检查的工件，例如 `<note_plan>...</note_plan>` 或独立 planning file",
                "不要只依赖隐式的隐藏规划步骤，也不要输出冗长的自由思维链",
                "决定哪些部分需要更多篇幅，哪些部分需要 `###` 子标题",
                "复杂论文不能只写扁平的 `##` 结构",
                "优先提炼关键数字、关键比较和论文特有洞察",
                "优先自己从 candidate_chunks 和 section_texts 判断重点，而不是盲信脚本挑出来的 top items",
                "方法型论文默认优先展开训练目标、推理链路、关键实现细节、复杂度和消融逻辑",
                "如果 metadata.abstract 可用，原始摘要部分默认同时包含英文原文和中文翻译",
            ],
            "note_plan_contract": {
                "required_fields": [
                    "paper_type",
                    "dominant_domain",
                    "must_cover",
                    "key_numbers",
                    "real_comparisons",
                    "section_plan",
                ],
                "format_preference": "compact_structured_plan",
                "forbidden_style": "verbose_freeform_chain_of_thought",
            },
            "formula_rules": [
                "如果公式、概率分解、优化目标或复杂度表达式是理解方法的核心，应该在笔记里保留少量关键 LaTeX 公式",
                "优先保留 1 到 3 个真正关键的公式，不要为了显得技术化而堆砌公式",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建关键公式语境",
                "行内公式使用 `$...$`，公式块使用 `$$ ... $$`",
                "不要把公式写成反引号代码或 fenced code block",
            ],
            "self_review_rules": [
                "在生成最终 Markdown 前，先自查这篇笔记是否包含关键数字、关键比较、必要时的公式或复杂度表达式",
                "如果方法论文里没有训练目标、推理流程、关键维度、复杂度或核心机制解释，说明写得太浅，需要重写相关小节",
                "如果正文不能让熟悉 Python 和深度学习框架的开发者看懂方法主线，说明仍停留在总结层面，需要继续下钻",
                "如果出现句中异常换行、逗号后换行或明显继承 PDF 折行的 prose，必须整理后再输出",
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
