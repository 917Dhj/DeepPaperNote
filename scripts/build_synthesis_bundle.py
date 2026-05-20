#!/usr/bin/env python3
"""Assemble a model-facing synthesis bundle from deterministic DeepPaperNote artifacts."""

from __future__ import annotations

import argparse

from common import maybe_load_json_record, normalize_whitespace, runtime_config
from contracts import NOTE_REQUIRED_SECTIONS, PAPER_TYPE_VALUES
from citation_links import resolve_reference_links


SECTION_TEXT_LIMIT_SECTIONS = 8
SECTION_TEXT_DEFAULT_MAX_CHARS = 4000
SECTION_TEXT_METHOD_MAX_CHARS = 12000
SECTION_TEXT_EXPERIMENT_MAX_CHARS = 12000
SECTION_TEXT_DATA_MAX_CHARS = 8000
SECTION_TEXT_INTRO_CONCLUSION_MAX_CHARS = 6000

SECTION_TEXT_METHOD_KEYWORDS = (
    "method",
    "methods",
    "model",
    "framework",
    "approach",
    "方法",
    "模型",
    "框架",
)
SECTION_TEXT_EXPERIMENT_KEYWORDS = (
    "experiment",
    "result",
    "results",
    "evaluation",
    "实验",
    "结果",
    "评测",
)
SECTION_TEXT_DATA_KEYWORDS = (
    "data",
    "dataset",
    "task",
    "benchmark",
    "数据",
    "任务",
)
SECTION_TEXT_INTRO_CONCLUSION_KEYWORDS = (
    "introduction",
    "conclusion",
    "discussion",
    "引言",
    "结论",
    "讨论",
)


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


def paper_type_writing_contract(paper_type: str) -> dict:
    mechanism_flow_contract = {
        "title": "机制流程",
        "apply_when_paper_type_in": ["AI_method"],
        "required_step_count": "3_to_4",
        "required_step_fields": ["input", "operation", "output_destination"],
        "figure_policy": "If a high-confidence pipeline or architecture figure matches the core execution chain, place it in this subsection first.",
        "fallback_policy": "If no high-confidence figure exists, keep the subsection as text-only and do not lower the figure-matching threshold.",
    }
    contracts = {
        "AI_method": {
            "paper_type": "AI_method",
            "writer_persona": "面向能复现方法机制的技术读者",
            "emphasis": [
                "问题设置",
                "方法机制",
                "训练/推理流程",
                "关键公式",
                "比较基线",
                "消融与失败边界",
            ],
            "planning_rules": [
                "AI_method 论文默认在 `方法主线` 下写 `### 机制流程`，用 3 到 4 步编号列表说明输入、操作和输出去向",
                "围绕机制、公式、训练目标、实验设计和 ablation_evidence 排布深度，而不是停留在摘要级贡献列表",
            ],
            "self_review_rules": [
                "如果 bundle 中存在 ablation_evidence，最终笔记必须至少写出一项次优、失败或不稳定设定；如果不存在，也要明确说明论文未充分报告这类负面经验",
                "AI_method 论文应检查 `### 机制流程` 是否是 3 到 4 步编号列表，而不是泛化散文",
                "如果正文不能让熟悉 Python 和深度学习框架的开发者看懂方法主线，说明仍停留在总结层面，需要继续下钻",
            ],
            "formula_rules": [
                "如果公式、概率分解、优化目标或复杂度表达式是理解方法的核心，保留 1 到 3 个关键 LaTeX 公式",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建关键公式语境",
                "每个保留公式后补一句工程解释，说明它对应什么操作、训练目标或状态更新",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
            "mechanism_flow_contract": mechanism_flow_contract,
        },
        "benchmark_or_dataset": {
            "paper_type": "benchmark_or_dataset",
            "writer_persona": "面向要判断 benchmark/dataset 可用性和偏差边界的研究者",
            "emphasis": [
                "任务拆分",
                "数据来源与构建流程",
                "标注协议",
                "评测指标",
                "覆盖范围与偏差",
                "benchmark 真正测到什么",
            ],
            "planning_rules": [
                "围绕数据/任务定义、构建流程、评测维度、基线和适用边界组织 note_plan",
                "在 `方法主线` 中写清 benchmark/dataset 的设计逻辑，不要强行改写成模型架构流程",
            ],
            "self_review_rules": [
                "检查是否说明数据来源、样本/题目规模、标注或筛选流程、评测指标和潜在偏差",
                "如果论文没有证明 benchmark 能代表真实能力边界，要在局限中明确写出",
            ],
            "formula_rules": [
                "如果评测指标、标注一致性、采样规则或划分规则是理解 benchmark/dataset 的核心，保留 1 到 3 个关键公式或定义",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建指标或数据构建语境",
                "每个保留公式后补一句解释，说明它对应什么指标、采样过程或评价边界",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
        },
        "clinical_or_psychology_empirical": {
            "paper_type": "clinical_or_psychology_empirical",
            "writer_persona": "面向关注临床/心理学样本、变量关系和外推边界的研究读者",
            "emphasis": [
                "样本来源",
                "纳排标准",
                "变量或量表",
                "分析管线",
                "效应量与不确定性",
                "临床或心理学意义",
            ],
            "planning_rules": [
                "围绕样本、变量/量表、任务定义、统计分析和外推边界组织 note_plan",
                "在 `方法主线` 中写清研究设计和分析路径，不要强行改写成模型架构流程",
            ],
            "self_review_rules": [
                "检查是否说明样本来源、样本量、变量/量表、主要统计关系和临床/心理学解释边界",
                "不要把相关性、预测性能或组间差异写成未经证明的因果结论",
            ],
            "formula_rules": [
                "如果统计模型、量表计分、效应量、置信区间或显著性检验是理解论文的核心，保留 1 到 3 个关键公式或定义",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建变量、估计量和统计语境",
                "每个保留公式后补一句解释，说明它对应什么变量关系、估计量或临床/心理学含义",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
        },
        "humanities_or_social_science": {
            "paper_type": "humanities_or_social_science",
            "writer_persona": "面向关注理论框架、材料解释和论证结构的研究读者",
            "emphasis": [
                "研究对象",
                "材料来源",
                "理论框架",
                "论证路径",
                "概念贡献",
                "解释边界",
            ],
            "planning_rules": [
                "围绕研究对象、材料、理论框架、论证路径和概念贡献组织 note_plan",
                "在 `方法主线` 中写清材料如何支撑论证，不要强行改写成模型架构流程",
            ],
            "self_review_rules": [
                "检查是否说明理论框架、材料来源、论证结构、概念贡献和解释性局限",
                "不要把作者的规范性判断、文本解释或案例分析写成实验事实",
            ],
            "formula_rules": [
                "此类论文通常不需要强行保留公式；只有作者使用形式化定义、编码规则或分类框架且它们是理解论证的核心时才保留",
                "优先从 candidate_chunks 和 section_texts 中重建概念、分类轴或编码规则的语境",
                "每个保留公式或形式化定义后补一句解释，说明它如何支撑理论框架或论证路径",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
        },
        "survey_or_review": {
            "paper_type": "survey_or_review",
            "writer_persona": "面向需要梳理综述脉络、分类体系和证据边界的研究读者",
            "emphasis": [
                "综述范围",
                "纳入排除标准",
                "主题分类",
                "方法谱系",
                "共识与分歧",
                "开放问题",
            ],
            "planning_rules": [
                "围绕综述范围、分类轴、代表性方向、证据强弱和开放问题组织 note_plan",
                "在 `方法主线` 中写清分类体系或综述方法，不要强行改写成单篇方法架构流程",
            ],
            "self_review_rules": [
                "检查是否说明综述范围、文献选择或纳入标准、分类体系、共识/分歧和开放问题",
                "不要把综述中的代表性结论写成作者自己完成的单项实验结果",
            ],
            "formula_rules": [
                "如果分类轴、纳入排除准则、证据汇总规则或 meta-analysis 统计量是理解综述的核心，保留 1 到 3 个关键公式或定义",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建综述方法或证据聚合语境",
                "每个保留公式或定义后补一句解释，说明它如何影响文献归类、证据权重或结论边界",
                "最终 Markdown 使用 Obsidian/MathJax 可渲染的 `$...$` 或 `$$...$$`，不要写成代码块或双反斜杠转义文本",
            ],
        },
    }
    normalized = normalize_whitespace(str(paper_type or "")) or "AI_method"
    selected = dict(contracts.get(normalized, contracts["AI_method"]))
    selected["reader_lens"] = selected["writer_persona"]
    selected["section_focus"] = list(selected["emphasis"])
    selected["required_checks"] = list(selected["self_review_rules"])
    selected["avoid_rules"] = [
        "不要移除或重命名 12 个 required sections",
        "不要为了套用论文类型而编造证据、数字、公式、实验或理论框架",
    ]
    if selected["paper_type"] != "AI_method":
        selected["avoid_rules"].append("不要强行写 `### 机制流程` 或把论文改写成模型架构流程")
    return selected


def paper_type_writing_contracts() -> dict[str, dict]:
    return {paper_type: paper_type_writing_contract(paper_type) for paper_type in PAPER_TYPE_VALUES}


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


def section_text_max_chars(section_name: str, override: int | None = None) -> int:
    if override is not None:
        return override
    normalized = normalize_whitespace(str(section_name)).lower()
    if any(keyword in normalized for keyword in SECTION_TEXT_METHOD_KEYWORDS):
        return SECTION_TEXT_METHOD_MAX_CHARS
    if any(keyword in normalized for keyword in SECTION_TEXT_EXPERIMENT_KEYWORDS):
        return SECTION_TEXT_EXPERIMENT_MAX_CHARS
    if any(keyword in normalized for keyword in SECTION_TEXT_DATA_KEYWORDS):
        return SECTION_TEXT_DATA_MAX_CHARS
    if any(keyword in normalized for keyword in SECTION_TEXT_INTRO_CONCLUSION_KEYWORDS):
        return SECTION_TEXT_INTRO_CONCLUSION_MAX_CHARS
    return SECTION_TEXT_DEFAULT_MAX_CHARS


def sanitize_section_texts(
    evidence_pack: dict,
    *,
    limit_sections: int = SECTION_TEXT_LIMIT_SECTIONS,
    max_chars: int | None = None,
) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    section_texts = evidence_pack.get("section_texts", {}) or {}
    if not isinstance(section_texts, dict):
        return sanitized
    for section_name, text in list(section_texts.items())[:limit_sections]:
        section_key = normalize_whitespace(str(section_name))
        cleaned = normalize_whitespace(str(text))
        if not section_key or not cleaned:
            continue
        sanitized[section_key] = cleaned[: section_text_max_chars(section_key, max_chars)]
    return sanitized


def bundle_text_budget(
    evidence_pack: dict,
    *,
    limit_sections: int = SECTION_TEXT_LIMIT_SECTIONS,
    max_chars: int | None = None,
) -> dict:
    section_texts = evidence_pack.get("section_texts", {}) or {}
    budget = {
        "section_text_default_max_chars": max_chars or SECTION_TEXT_DEFAULT_MAX_CHARS,
        "section_text_limit_sections": limit_sections,
        "section_text_limits": {},
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
        section_limit = section_text_max_chars(section_key, max_chars)
        included_chars = min(original_chars, section_limit)
        budget["section_text_limits"][section_key] = section_limit
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


def sanitize_appendix_evidence(evidence_pack: dict, *, limit_per_category: int = 8) -> dict:
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
    summary = evidence_wrapper.get("summary", {}) if isinstance(evidence_wrapper.get("summary"), dict) else {}
    paper_type_contracts = paper_type_writing_contracts()
    suggested_paper_type = normalize_whitespace(str(summary.get("paper_type", "")))

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
        "summary": summary,
        "writing_contract": {
            "language": "zh-CN",
            "contract_role": "minimal_generation_contract",
            "canonical_source": "SKILL.md carries the required workflow; references are optional topic deep dives.",
            "paper_type_adaptation_rule": "Keep the 12 required sections unchanged. First choose note_plan.paper_type from allowed_paper_types, then adapt emphasis, formulas, subsection choices, and self-review checks through paper_type_contracts[note_plan.paper_type].",
            "paper_type_selection": {
                "source_of_truth": "note_plan.paper_type",
                "suggested_paper_type": suggested_paper_type,
                "suggested_paper_type_role": "hint_only",
                "allowed_paper_types": list(PAPER_TYPE_VALUES),
            },
            "paper_type_contracts": paper_type_contracts,
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
                "根据 note_plan.paper_type 采用 paper_type_contracts[note_plan.paper_type] 中的 reader_lens 和 writer_persona",
            ],
            "planning_rules": [
                "先基于 bundle evidence/coverage/candidate_chunks/section_texts 做显式 note_plan，再写最终笔记",
                "先从 writing_contract.paper_type_selection.allowed_paper_types 中选择 note_plan.paper_type；summary.paper_type/suggested_paper_type 只能作为 hint_only 线索，不能替代模型判断",
                "确定 note_plan.paper_type 后，应用 paper_type_contracts[note_plan.paper_type] 的 reader_lens、section_focus、planning_rules、formula_rules 和 self_review_rules",
                "note_plan 是简短 JSON planning file，例如 `<note>.plan.json` 或 `*_note_plan.json`；lint 时传给 `scripts/lint_note.py --plan-file ...`",
                "`核心信息` 是固定 metadata 区；`创新点` 是独立 `##` 章节，位于 `原文摘要翻译` 之后、`一句话总结` 之前",
                "metadata.abstract 可用时，`原文摘要翻译` 必须是原 abstract 的中文翻译，不要写成英文原文+中文翻译或全文 summary",
                "复杂论文需要 paper-specific `###` 子标题；具体重心按 paper_type_contracts[note_plan.paper_type] 调整",
                "优先选择关键数字、真实比较、论文特有洞察和必要公式，不要机械复述所有抽取项",
            ],
            "note_plan_contract": {
                "required_fields": [
                    "paper_type",
                    "paper_type_rationale",
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
            "self_review_rules": [
                "生成最终 Markdown 前，检查是否包含关键数字、真实比较、必要公式和 paper-specific insight",
                "检查 note_plan.paper_type 是否来自 allowed_paper_types，并确认正文已应用 paper_type_contracts[note_plan.paper_type]；若 note_plan.paper_type 为 AI_method，也要执行其中关于 ablation_evidence 和 `### 机制流程` 的检查",
                "必须先查看 bundle.coverage：section coverage 为 poor 或 partial 时，不要把 abstract fallback 当作全文证据来写深度判断",
                "如果 bundle.coverage.pdf_coverage 显示 PDF 被 max_pages 截断，不要声称完成了全文级精读",
                "如果 bundle.coverage.bundle_text_budget 显示 section_texts 被截断，不要把截断片段当作完整 section 证据",
                "appendix evidence 只能补强复现细节、额外实验、局限或图表语义，不能替代主文方法主线",
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
                "For each usable candidate, resolve the final note as inserted, visual-defect placeholder, lower-priority placeholder because a more central related figure is already inserted, or materialization-blocked placeholder.",
                "Do not keep a usable candidate as a placeholder only because the note should stay light, key values were transcribed, the figure can be checked later, or it is convenient as a back-reference.",
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
