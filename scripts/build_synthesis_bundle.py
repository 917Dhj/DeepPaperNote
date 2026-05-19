#!/usr/bin/env python3
"""Assemble a model-facing synthesis bundle from deterministic DeepPaperNote artifacts."""

from __future__ import annotations

import argparse

from common import maybe_load_json_record, normalize_whitespace, runtime_config
from contracts import NOTE_REQUIRED_SECTIONS
from citation_links import resolve_reference_links


SECTION_TEXT_LIMIT_SECTIONS = 8
SECTION_TEXT_MAX_CHARS = 4000


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


def sanitize_reference_candidates(evidence_pack: dict, *, limit: int = 20) -> list[dict]:
    candidates = evidence_pack.get("reference_candidates", []) or []
    if not isinstance(candidates, list):
        return []
    try:
        matched_candidates = resolve_reference_links(candidates[:limit], runtime_config())
    except Exception:
        matched_candidates = [
            {
                **candidate,
                "wikilink": "",
                "vault_target": "",
                "match_status": "vault_unavailable",
                "match_reason": "none",
            }
            for candidate in candidates[:limit]
            if isinstance(candidate, dict)
        ]

    sanitized: list[dict] = []
    for item in matched_candidates:
        if not isinstance(item, dict):
            continue
        raw_text = normalize_whitespace(str(item.get("raw_text", "")))
        display_text = normalize_whitespace(str(item.get("display_text", "")))
        if not raw_text and not display_text:
            continue
        sanitized.append(
            {
                "raw_text": raw_text,
                "display_text": display_text,
                "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
                "doi": normalize_whitespace(str(item.get("doi", ""))),
                "arxiv_id": normalize_whitespace(str(item.get("arxiv_id", ""))),
                "wikilink": normalize_whitespace(str(item.get("wikilink", ""))),
                "vault_target": normalize_whitespace(str(item.get("vault_target", ""))),
                "match_status": normalize_whitespace(str(item.get("match_status", "no_vault_match"))),
                "match_reason": normalize_whitespace(str(item.get("match_reason", "none"))),
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
            if item.get("actual_source_section"):
                kept[-1]["actual_source_section"] = normalize_whitespace(
                    str(item.get("actual_source_section", ""))
                )
            if item.get("is_abstract_fallback"):
                kept[-1]["is_abstract_fallback"] = True
        if kept:
            sanitized[normalize_whitespace(str(section_name))] = kept
    return sanitized


def sanitize_section_texts(
    evidence_pack: dict,
    *,
    limit_sections: int = SECTION_TEXT_LIMIT_SECTIONS,
    max_chars: int = SECTION_TEXT_MAX_CHARS,
) -> dict[str, str]:
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


def bundle_text_budget(
    evidence_pack: dict,
    *,
    limit_sections: int = SECTION_TEXT_LIMIT_SECTIONS,
    max_chars: int = SECTION_TEXT_MAX_CHARS,
) -> dict:
    section_texts = evidence_pack.get("section_texts", {}) or {}
    budget = {
        "section_text_max_chars": max_chars,
        "section_text_limit_sections": limit_sections,
        "section_text_original_chars": {},
        "section_text_included_chars": {},
        "section_text_truncated_sections": [],
    }
    if not isinstance(section_texts, dict):
        return budget

    for section_name, text in list(section_texts.items())[:limit_sections]:
        section_key = normalize_whitespace(str(section_name))
        cleaned = normalize_whitespace(str(text))
        if not section_key or not cleaned:
            continue
        original_chars = len(cleaned)
        included_chars = min(original_chars, max_chars)
        budget["section_text_original_chars"][section_key] = original_chars
        budget["section_text_included_chars"][section_key] = included_chars
        if original_chars > included_chars:
            budget["section_text_truncated_sections"].append(section_key)
    return budget


def figure_quality_summary(assets_wrapper: dict) -> dict[str, int]:
    summary = {"usable": 0, "review": 0, "reject": 0, "unknown": 0}
    for item in assets_wrapper.get("figure_assets", []) or []:
        if not isinstance(item, dict):
            summary["unknown"] += 1
            continue
        quality_signals = item.get("quality_signals", {})
        if not isinstance(quality_signals, dict):
            summary["unknown"] += 1
            continue
        status = normalize_whitespace(str(quality_signals.get("visual_quality_status", ""))).lower()
        if status == "needs_review":
            status = "review"
        if status not in summary:
            status = "unknown"
        summary[status] += 1
    return summary


def truncation_warnings(pdf_coverage: dict, asset_coverage: dict, text_budget: dict) -> list[str]:
    warnings: list[str] = []
    if pdf_coverage.get("truncated_due_to_page_limit"):
        warnings.append("pdf_page_limit")
    if asset_coverage.get("truncated_due_to_asset_page_limit"):
        warnings.append("asset_page_limit")
    if text_budget.get("section_text_truncated_sections"):
        warnings.append("section_text_truncated")
    return warnings


def coverage_summary(evidence_pack: dict, metadata: dict | None = None, assets_wrapper: dict | None = None) -> dict:
    metadata = metadata or {}
    assets_wrapper = assets_wrapper or {}
    pdf_coverage = evidence_pack.get("pdf_coverage", {}) or {}
    asset_coverage = assets_wrapper.get("asset_coverage", {}) or {}
    text_budget = bundle_text_budget(evidence_pack)
    return {
        "language_hint": evidence_pack.get("language_hint", "unknown"),
        "section_extraction_coverage": evidence_pack.get("section_extraction_coverage", {}) or {},
        "pdf_coverage": pdf_coverage,
        "bundle_text_budget": text_budget,
        "appendix_evidence_counts": appendix_evidence_counts(evidence_pack),
        "extraction_failures": evidence_pack.get("extraction_failures", []) or [],
        "asset_coverage": asset_coverage if isinstance(asset_coverage, dict) else {},
        "figure_quality_summary": figure_quality_summary(assets_wrapper),
        "truncation_warnings": truncation_warnings(
            pdf_coverage if isinstance(pdf_coverage, dict) else {},
            asset_coverage if isinstance(asset_coverage, dict) else {},
            text_budget,
        ),
        "identity_confidence": metadata.get("identity_confidence", ""),
        "identity_confidence_reasons": metadata.get("identity_confidence_reasons", []) or [],
    }


def appendix_evidence_counts(evidence_pack: dict) -> dict[str, int]:
    appendix_evidence = evidence_pack.get("appendix_evidence", {}) or {}
    if not isinstance(appendix_evidence, dict):
        return {}
    return {
        normalize_whitespace(str(category)): len(items)
        for category, items in appendix_evidence.items()
        if isinstance(items, list)
    }


def sanitize_appendix_evidence(evidence_pack: dict, *, limit_per_category: int = 4) -> dict:
    appendix_evidence = evidence_pack.get("appendix_evidence", {}) or {}
    if not isinstance(appendix_evidence, dict):
        return {}
    sanitized: dict[str, list[dict]] = {}
    for category, items in appendix_evidence.items():
        if not isinstance(items, list):
            continue
        kept: list[dict] = []
        for item in items[:limit_per_category]:
            if not isinstance(item, dict):
                continue
            evidence = normalize_whitespace(str(item.get("evidence", "")))
            if not evidence:
                continue
            kept.append(
                {
                    "evidence": evidence,
                    "source_section": normalize_whitespace(str(item.get("source_section", ""))),
                    "page_hint": normalize_whitespace(str(item.get("page_hint", ""))),
                    "kind_hint": normalize_whitespace(str(item.get("kind_hint", ""))),
                }
            )
        sanitized[normalize_whitespace(str(category))] = kept
    return sanitized


def appendix_summary(evidence_pack: dict) -> dict:
    return {
        "index": evidence_pack.get("appendix_index", {}) or {},
        "evidence": sanitize_appendix_evidence(evidence_pack),
    }


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


def sanitize_figure_assets(assets_wrapper: dict, *, limit: int = 48) -> list[dict]:
    sanitized: list[dict] = []
    for item in (assets_wrapper.get("figure_assets", []) or [])[:limit]:
        if not isinstance(item, dict):
            continue
        record = {
            "filename": item.get("filename", ""),
            "path": item.get("path", ""),
            "page_number": item.get("page_number", 0),
            "label": item.get("label", ""),
            "kind": item.get("kind", ""),
            "caption_text": normalize_whitespace(str(item.get("caption_text", ""))),
            "width": item.get("width", 0),
            "height": item.get("height", 0),
            "size_bytes": item.get("size_bytes", 0),
            "extraction_level": item.get("extraction_level", ""),
        }
        if isinstance(item.get("quality_signals"), dict):
            record["quality_signals"] = item.get("quality_signals")
        sanitized.append(record)
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
            "identity_confidence": metadata.get("identity_confidence", ""),
            "identity_confidence_reasons": metadata.get("identity_confidence_reasons", []) or [],
        },
        "evidence_quality": evidence_pack.get("evidence_quality", "unknown"),
        "coverage": coverage_summary(evidence_pack, metadata, assets_wrapper),
        "evidence": {
            "problem": top_items(evidence_pack, "problem_evidence"),
            "task": top_items(evidence_pack, "task_evidence"),
            "data": top_items(evidence_pack, "data_evidence"),
            "method": top_items(evidence_pack, "method_evidence"),
            "mechanism": top_items(evidence_pack, "mechanism_evidence"),
            "results": top_items(evidence_pack, "results_evidence"),
            "ablation": top_items(evidence_pack, "ablation_evidence"),
            "limitations": top_items(evidence_pack, "limitations_evidence"),
        },
        "appendix": appendix_summary(evidence_pack),
        "equation_candidates": sanitize_equation_candidates(evidence_pack),
        "references": {"candidates": sanitize_reference_candidates(evidence_pack)},
        "candidate_chunks": sanitize_candidate_chunks(evidence_pack),
        "section_texts": sanitize_section_texts(evidence_pack),
        "section_previews": section_previews(evidence_pack),
        "figure_plan": figure_plan,
        "pdf_assets": {
            "asset_root": assets_wrapper.get("asset_root", ""),
            "images_dir": assets_wrapper.get("images_dir", ""),
            "page_assets": sanitize_page_assets(assets_wrapper),
            "image_assets": assets_wrapper.get("image_assets", []),
            "figure_assets": sanitize_figure_assets(assets_wrapper),
            "ocr_available": assets_wrapper.get("ocr_available", False),
        },
        "summary": evidence_wrapper.get("summary", {}),
        "writing_contract": {
            "language": "zh-CN",
            "contract_role": "minimal_generation_contract",
            "canonical_source": "SKILL.md carries the required workflow; references are optional topic deep dives.",
            "must_distinguish": [
                "研究问题 vs 任务定义",
                "真实贡献 vs 标题包装",
                "核心结果 vs 好看的结果",
                "作者声称什么 vs 论文没有证明什么",
            ],
            "must_include_sections": list(NOTE_REQUIRED_SECTIONS),
            "core_info_contract": {
                "role": "fixed_metadata_block",
                "format": "template_style_metadata_bullets",
                "fixed_field_behavior": [
                    "Use predefined metadata fields only.",
                    "Keep each line in `- 字段名: 值` form.",
                    "Leave unavailable fields blank or marked unavailable instead of replacing them with commentary.",
                ],
                "forbidden_content": ["analysis", "judgment", "takeaways", "mini_summaries", "my_view_sentences"],
                "redirect_analysis_to": ["一句话总结", "深度分析", "我的笔记"],
            },
            "must_not_do": [
                "不要把英文证据原句揉进中文正文",
                "不要把脚本 heuristics 当成论文结论",
                "不要为了通过 lint 而编造事实、失败案例、机制细节或比较结论",
                "不要加入只是为了看起来合规却没有信息量的 filler text",
                "不要在 `核心信息` 里加入解释性判断或总结性句子",
            ],
            "writer_persona": [
                "复现级中文研究笔记",
                "读者默认熟悉 Python、PyTorch、训练流程和实验设计",
            ],
            "planning_rules": [
                "先基于 bundle evidence/coverage/candidate_chunks/section_texts 做显式 note_plan，再写最终笔记",
                "note_plan 是简短 JSON planning file，例如 `<note>.plan.json` 或 `*_note_plan.json`；lint 时传给 `scripts/lint_note.py --plan-file ...`",
                "`核心信息` 是固定 metadata 区；`创新点` 是独立 `##` 章节，位于 `原文摘要翻译` 之后、`一句话总结` 之前",
                "metadata.abstract 可用时，`原文摘要翻译` 必须是原 abstract 的中文翻译，不要写成英文原文+中文翻译或全文 summary",
                "复杂论文需要 paper-specific `###` 子标题；method/system/framework 论文默认在 `方法主线` 下写 `### 机制流程`",
                "优先选择关键数字、真实比较、论文特有洞察和必要公式，不要机械复述所有抽取项",
            ],
            "mechanism_flow_contract": {
                "title": "机制流程",
                "apply_when_paper_type_in": ["AI_method", "system", "framework"],
                "required_step_count": "3_to_4",
                "required_step_fields": ["input", "operation", "output_destination"],
                "figure_policy": "If a high-confidence pipeline or architecture figure matches the core execution chain, place it in this subsection first.",
                "fallback_policy": "If no high-confidence figure exists, keep the subsection as text-only and do not lower the figure-matching threshold.",
            },
            "note_plan_contract": {
                "required_fields": [
                    "paper_type",
                    "dominant_domain",
                    "must_cover",
                    "key_numbers",
                    "real_comparisons",
                    "section_plan",
                ],
                "artifact_preference": "short_json_planning_file",
                "format_preference": "compact_structured_plan",
                "lint_hint": "pass_to_lint_note_with_plan_file",
                "forbidden_style": "verbose_freeform_chain_of_thought",
            },
            "formula_rules": [
                "如果公式、概率分解、优化目标或复杂度表达式是理解方法的核心，保留 1 到 3 个关键 LaTeX 公式",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建关键公式语境",
                "每个保留公式后补一句工程解释，说明它对应什么操作、训练目标或状态更新",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
            "self_review_rules": [
                "生成最终 Markdown 前，检查是否包含关键数字、真实比较、必要公式和 paper-specific insight",
                "必须先查看 bundle.coverage：section coverage 为 poor 或 partial 时，不要把 abstract fallback 当作全文证据来写深度判断",
                "如果 bundle.coverage.pdf_coverage 显示 PDF 被 max_pages 截断，不要声称完成了全文级精读",
                "如果 bundle.coverage.bundle_text_budget 显示 section_texts 被截断，不要把截断片段当作完整 section 证据",
                "appendix evidence 只能补强复现细节、额外实验、局限或图表语义，不能替代主文方法主线",
                "如果 bundle 中存在 ablation_evidence，最终笔记必须至少写出一项次优、失败或不稳定设定；如果不存在，也要明确说明论文未充分报告这类负面经验",
                "method/system/framework 论文应检查 `### 机制流程` 是否是 3 到 4 步编号列表，而不是泛化散文",
                "如果正文不能让熟悉 Python 和深度学习框架的开发者看懂方法主线，说明仍停留在总结层面，需要继续下钻",
                "清理 PDF 折行、句中异常换行和明显写给 lint 看的空壳句子",
                "脚本 lint 通过后仍必须做 final_readability_review；该阶段只修表达，不新增事实、不改变核心数字和结论",
            ],
            "readability_review_contract": {
                "stage_name": "final_readability_review",
                "position_in_workflow": "after_lint_before_save",
                "core_rule": "Lint is a floor, not the writing objective.",
                "focus": [
                    "smooth awkward Chinese prose",
                    "remove stiff translations",
                    "rewrite ordinary English phrase leftovers into natural Chinese",
                    "keep stable proper nouns when translation would be worse",
                ],
                "must_not_do": [
                    "do_not_invent_new_facts",
                    "do_not_change_core_numbers_or_conclusions",
                    "do_not_flatten_the_note_under_the_name_of_polish",
                ],
                "rerun_rule": "If the readability review edits the note, rerun lint before write_obsidian_note.",
            },
            "figure_rules": [
                "Plan semantic figure/table placeholders before deciding replacements.",
                "label/caption match is not insertion approval; visual usability is a separate hard gate.",
                "Reject caption-only crops, missing table body crops, contaminated table crops, large text/title/abstract crops, and low visual body ratio crops.",
                "If visual quality is missing, ambiguous, or marked review/reject, fail closed: keep the placeholder instead of inserting the image.",
                "Every kept placeholder must appear directly under the most relevant analytical section; never collect them in catch-all sections.",
                "Every kept placeholder must use the standard `> [!figure]` callout with `建议位置`, `放置原因`, and `当前状态`; never use plain markers such as `[图表占位 | Fig. 1]`.",
                "`reject_visual_quality` means the candidate image is unsafe to insert; it does not require keeping a final-note placeholder for every rejected candidate.",
                "When inserting a real image, prefer the `obsidian_embed` returned by materialize_figure_asset.py and preserve the original Fig./Table id.",
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
