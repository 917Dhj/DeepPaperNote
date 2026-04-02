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
            "mechanism": top_items(evidence_pack, "mechanism_evidence"),
            "results": top_items(evidence_pack, "results_evidence"),
            "ablation": top_items(evidence_pack, "ablation_evidence"),
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
                "原文摘要翻译",
                "创新点",
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
            "core_info_contract": {
                "role": "fixed_metadata_block",
                "format": "template_style_metadata_bullets",
                "fixed_field_behavior": [
                    "Use the predefined template fields only.",
                    "Keep each line in `- 字段名: 值` form.",
                    "Do not add ad hoc metadata fields just because they seem helpful.",
                    "If a field is unavailable, leave it blank or mark it as unavailable instead of replacing it with commentary.",
                ],
                "forbidden_content": [
                    "analysis",
                    "judgment",
                    "takeaways",
                    "mini_summaries",
                    "my_view_sentences",
                ],
                "redirect_analysis_to": ["一句话总结", "深度分析", "我的笔记"],
            },
            "must_not_do": [
                "不要摘要改写",
                "不要把英文证据原句揉进中文正文",
                "不要把脚本 heuristics 当成论文结论",
                "不要把方法论文写成科普式总结",
                "不要为了通过 lint 而编造事实、失败案例、机制细节或比较结论",
                "不要加入只是为了看起来合规却没有信息量的 filler text",
                "不要为了通过 mixed-language 检查而把句子硬改成不自然的翻译",
                "不要因为怕触发 lint 就删掉有价值的公式、术语或必要英文原文",
                "不要在 `核心信息` 里加入解释性判断、总结性句子或“我对这篇论文的判断”之类的分析内容",
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
                "`核心信息` 是固定字段的 metadata 区，不要擅自增删字段，也不要把解释性 prose 塞进这里",
                "在章节骨架上，`创新点` 应该作为独立 `##` 章节放在 `原文摘要翻译` 之后、`一句话总结` 之前",
                "创新点部分不要只写抽象赞美，要列出 3 到 5 个真正的 paper-specific innovations，并分别解释它们解决了什么问题、带来了什么能力或评估增益",
                "决定哪些部分需要更多篇幅，哪些部分需要 `###` 子标题",
                "复杂论文不能只写扁平的 `##` 结构",
                "优先提炼关键数字、关键比较和论文特有洞察",
                "优先自己从 candidate_chunks 和 section_texts 判断重点，而不是盲信脚本挑出来的 top items",
                "方法型论文默认优先展开训练目标、推理链路、关键实现细节、复杂度和消融逻辑",
                "对于 method/system/framework 类型论文，`方法主线` 下默认包含固定小节 `### 机制流程`，不要把机制解释分散成难以扫描的散文",
                "如果 Algorithm 伪代码框或流程框在抽取后已经损坏，不要尝试逐字还原；应基于 method 的 section_texts、candidate_chunks 与 mechanism evidence，在 `### 机制流程` 中用 3 到 4 步工程流程重建核心机制",
                "机制流程的每一步都应尽量说清楚 Input、关键中间变换和 Output 去向，而不是只复述模块名或术语",
                "如果论文同时存在训练主线与推理主线，`### 机制流程` 优先写最核心的主执行链，不要把它膨胀成完整训练 recipe",
                "如果 metadata.abstract 可用，`原文摘要翻译` 部分应默认写成单一的中文翻译块，而不是英文原文加中文翻译的双子节结构",
                "`原文摘要翻译` 的标题固定为 `## 原文摘要翻译`，不要改成 `摘要`、`原始摘要`，也不要在里面再拆出 `### 英文原文` 或 `### 中文翻译`",
                "`原文摘要翻译` 这个 section 本身必须直接写成中文，不要在这里输出英文摘要句子、英文段落或英文原文摘录",
                "`原文摘要翻译` 的任务很简单：把原文 abstract 翻译成中文，不要把它改写成你自己对全文的总结",
                "`原文摘要翻译` 不要写成基于整篇论文内容重新整理后的 summary，也不要混入创新点、价值判断或后文分析",
                "如果 abstract 较长，也应完整翻译；提炼和压缩应放到 `一句话总结`、`创新点` 或其他分析章节，而不是发生在 `原文摘要翻译` 里",
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
                "format_preference": "compact_structured_plan",
                "forbidden_style": "verbose_freeform_chain_of_thought",
            },
            "formula_rules": [
                "如果公式、概率分解、优化目标或复杂度表达式是理解方法的核心，应该在笔记里保留少量关键 LaTeX 公式",
                "优先保留 1 到 3 个真正关键的公式，不要为了显得技术化而堆砌公式",
                "优先从 equation_candidates、candidate_chunks 和 section_texts 中重建关键公式语境",
                "每个保留的关键公式后都要补一句工程解释，说明它在实现上对应什么操作、训练目标或状态更新；不要只解释变量名",
                "公式解释应尽量服务于 `### 机制流程` 或其相邻方法子节，而不是让公式孤立悬空",
                "最终 Markdown 中的公式必须按 Obsidian/MathJax 可直接渲染的 TeX 写法输出，不要把它们写成 JSON 或字符串风格的双反斜杠转义文本",
                "避免把 `\\tau`、`\\frac`、`\\bar`、`\\begin`、`\\end` 这类命令错误地写成双反斜杠；在最终笔记里应保留单反斜杠 TeX 命令",
                "行内公式使用 `$...$`，公式块使用 `$$ ... $$`",
                "不要把公式写成反引号代码或 fenced code block",
            ],
            "self_review_rules": [
                "在生成最终 Markdown 前，先自查这篇笔记是否包含关键数字、关键比较、必要时的公式或复杂度表达式",
                "如果方法论文里没有训练目标、推理流程、关键维度、复杂度或核心机制解释，说明写得太浅，需要重写相关小节",
                "如果这是 method/system/framework 类型论文，检查 `方法主线` 下是否显式包含 `### 机制流程`，并且该小节是 3 到 4 步的编号列表，而不是一段泛化散文",
                "如果 bundle 中存在 ablation_evidence，最终笔记必须至少写出一项次优、失败或不稳定设定；如果不存在，也要明确说明论文未充分报告这类负面经验",
                "如果正文不能让熟悉 Python 和深度学习框架的开发者看懂方法主线，说明仍停留在总结层面，需要继续下钻",
                "如果出现句中异常换行、逗号后换行或明显继承 PDF 折行的 prose，必须整理后再输出",
                "脚本 lint 通过后，仍必须重新通读整篇笔记做最终可读性质检；lint 只是下限，不是写作目标",
                "最终可读性质检只能修表达：改善句子流畅度、消除生硬翻译、把普通英文短语改成自然中文、并在必要时给稳定专名补中文解释",
                "最终可读性质检不得新增无证据支撑的信息，不得改动核心数字、结论或实验判断，也不得借润色之名把笔记写浅",
                "如果为了满足章节要求而写出了空壳句子、合规模板话或明显写给 lint 看的表述，必须改掉再输出",
                "如果笔记中保留了 LaTeX 公式，最终输出前要快速自查是否存在双反斜杠误转义、损坏的 math delimiter 或明显无法渲染的 TeX 命令",
            ],
            "readability_review_contract": {
                "stage_name": "final_readability_review",
                "position_in_workflow": "after_lint_before_save",
                "role": "final_model_side_language_and_readability_review",
                "core_rule": "Lint is a floor, not the writing objective.",
                "allowed_kept_english": [
                    "stable model names",
                    "stable dataset names",
                    "stable metric names",
                    "method names",
                    "source-faithful technical labels",
                    "math symbols",
                    "code tokens",
                    "original paper figure/table ids",
                ],
                "should_be_natural_chinese": [
                    "ordinary English phrases",
                    "abstract descriptive phrases in analytical prose",
                    "English leftovers that have no clear reason to remain",
                ],
                "checklist": [
                    "有没有普通英文短语其实应写成自然中文",
                    "有没有术语被翻得过硬过怪",
                    "有没有为了满足章节要求而写出的空壳句子",
                    "有没有写给 lint 看而不是写给读者看的语气",
                    "有没有本可自然中文表达却仍残留英文导致阅读发涩的句子",
                ],
                "must_not_do": [
                    "do_not_invent_new_facts",
                    "do_not_change_core_numbers_or_conclusions",
                    "do_not_flatten_the_note_under_the_name_of_polish",
                    "do_not_translate_stable_proper_nouns_mechanically",
                ],
                "rerun_rule": "If the readability review edits the note, rerun lint before write_obsidian_note.",
            },
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
