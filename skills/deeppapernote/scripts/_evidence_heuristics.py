"""Keyword heuristics that pick candidate evidence sentences from paper text."""

from __future__ import annotations

import re

from _pdf_text import split_sentences
from common import normalize_title, normalize_whitespace


def infer_paper_type(title: str, abstract: str) -> tuple[str, str]:
    lower = f"{title} {abstract}".lower()
    survey_terms = [
        "survey",
        "tutorial",
        "overview",
        "systematic review",
        "literature review",
        "scoping review",
        "meta-analysis",
        "meta analysis",
    ]
    if any(re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lower) for token in survey_terms):
        return "survey_or_review", "The paper is an explicit survey, review, tutorial, overview, or meta-analysis."
    if any(token in lower for token in ["depression", "anxiety", "mental health", "clinical", "patient", "psychiatric", "psychological", "hospital"]):
        return "clinical_or_psychology_empirical", "The paper is closer to an empirical clinical or psychology study."
    if any(token in lower for token in ["humanities", "social science", "theoretical framing", "ethnographic", "interpretive", "conceptual", "argument structure"]):
        return "humanities_or_social_science", "The paper emphasizes theoretical framing, interpretation, or social-science argument structure."
    if any(token in lower for token in ["benchmark", "leaderboard", "evaluation suite", "dataset", "corpus"]):
        return "benchmark_or_dataset", "The paper emphasizes benchmark, dataset, or evaluation design."
    return "AI_method", "The paper is best treated as a method-focused technical paper."


def extract_dataset_candidates(text: str) -> list[str]:
    found: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        if not any(token in sentence.lower() for token in ["dataset", "benchmark", "corpus", "participants", "patients"]):
            continue
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9+\-]{2,}(?:[ -][A-Z][A-Za-z0-9+\-]{2,})?\b", sentence)
        for candidate in candidates:
            norm = candidate.lower()
            if norm in seen:
                continue
            seen.add(norm)
            found.append(candidate)
            if len(found) >= 8:
                return found
    return found


def extract_metric_claims(text: str) -> list[str]:
    claims: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if not re.search(r"\d", sentence):
            continue
        if not any(token in lower for token in ["accuracy", "f1", "auc", "auprc", "mae", "rmse", "score", "%", "outperform", "improv", "bac"]):
            continue
        normalized = normalize_whitespace(sentence)
        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= 8:
            break
    return claims


def extract_negative_claims(text: str, *, limit: int = 6) -> list[str]:
    claims: list[str] = []
    seen = set()
    explicit_negative_tokens = [
        "worse",
        "degrade",
        "degraded",
        "drop",
        "dropped",
        "decrease",
        "decreased",
        "unstable",
        "instability",
        "fail",
        "failed",
        "fails",
        "collapse",
        "collapsed",
        "underperform",
        "underperformed",
        "sensitive",
        "sensitivity",
        "trade-off",
        "tradeoff",
        "hurt performance",
        "hurts performance",
    ]
    ablation_tokens = [
        "without",
        "w/o",
        "remove",
        "removed",
        "removing",
        "omit",
        "omits",
        "omitted",
        "omitting",
        "ablation",
    ]
    performance_tokens = [
        "accuracy",
        "f1",
        "auc",
        "auprc",
        "mae",
        "rmse",
        "score",
        "performance",
        "%",
        "result",
        "results",
        "training",
        "converge",
        "convergence",
        "stable",
        "stability",
        "baseline",
    ]
    positive_only_tokens = [
        "outperform",
        "improv",
        "better than",
        "achieve",
        "state-of-the-art",
        "sota",
    ]

    for sentence in split_sentences(text):
        normalized = normalize_whitespace(sentence)
        if not normalized:
            continue
        lower = normalized.lower()
        has_explicit_negative = any(token in lower for token in explicit_negative_tokens)
        has_ablation_marker = any(token in lower for token in ablation_tokens)
        has_performance_context = any(token in lower for token in performance_tokens) or bool(re.search(r"\d", normalized))
        has_positive_only = any(token in lower for token in positive_only_tokens)

        if not has_explicit_negative:
            if not (has_ablation_marker and has_performance_context):
                continue
            if has_positive_only and not any(token in lower for token in ["trade-off", "tradeoff", "sensitive", "stability"]):
                continue

        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= limit:
            break
    return claims


def extract_mechanism_flow_sentences(text: str, *, limit: int = 8) -> list[str]:
    claims: list[str] = []
    seen = set()
    action_tokens = [
        "encode",
        "encoded",
        "encoding",
        "extract",
        "extracted",
        "project",
        "projected",
        "pool",
        "pooled",
        "fuse",
        "fused",
        "fusion",
        "concat",
        "concatenate",
        "query",
        "queried",
        "align",
        "aligned",
        "compress",
        "compressed",
        "send",
        "sent",
        "feed",
        "fed",
        "generate",
        "generated",
        "predict",
        "predicted",
        "decode",
        "decoded",
        "update",
        "updated",
        "freeze",
        "frozen",
        "fine-tune",
        "finetune",
    ]
    flow_tokens = [
        "input",
        "inputs",
        "output",
        "outputs",
        "token",
        "tokens",
        "feature",
        "features",
        "representation",
        "representations",
        "encoder",
        "decoder",
        "attention",
        "module",
        "modules",
        "llm",
        "language model",
        "query token",
        "cross-attention",
        "projection",
        "state",
        "states",
    ]

    for sentence in split_sentences(text):
        normalized = normalize_whitespace(sentence)
        if not normalized:
            continue
        lower = normalized.lower()
        if not any(token in lower for token in action_tokens):
            continue
        if not any(token in lower for token in flow_tokens):
            continue
        key = normalize_title(normalized)
        if key in seen:
            continue
        seen.add(key)
        claims.append(normalized)
        if len(claims) >= limit:
            break
    return claims


def pick_sentences_by_keywords(text: str, keywords: list[str], *, limit: int = 5) -> list[str]:
    picked: list[str] = []
    seen = set()
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if not any(keyword in lower for keyword in keywords):
            continue
        normalized = normalize_title(sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        picked.append(normalize_whitespace(sentence))
        if len(picked) >= limit:
            break
    return picked
