"""Choose where a note is saved in the Obsidian vault, including domain routing."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Any

from _evidence_heuristics import infer_paper_type
from common import normalize_whitespace, slugify_filename


def configured_obsidian_vault(config: dict[str, Any]) -> Path | None:
    if str(config.get("save_mode", "")).strip() == "workspace":
        return None
    vault = str(config.get("obsidian_vault", "")).strip()
    if not vault:
        return None
    vault_path = Path(vault).expanduser().resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        raise RuntimeError(f"Configured Obsidian vault does not exist: {vault_path}")
    return vault_path


def require_obsidian_vault(config: dict[str, Any]) -> Path:
    vault_path = configured_obsidian_vault(config)
    if vault_path is None:
        raise RuntimeError("Missing Obsidian Vault in User Configuration or the current Run Override.")
    return vault_path


def resolve_note_output_mode(config: dict[str, Any]) -> tuple[str, Path]:
    save_mode = str(config.get("save_mode", "")).strip()
    if save_mode == "obsidian":
        return ("obsidian", require_obsidian_vault(config))
    if not save_mode:
        vault_path = configured_obsidian_vault(config)
        if vault_path is not None:
            return ("obsidian", vault_path)
    workspace_root = Path.cwd().resolve()
    output_dir = str(config.get("workspace_output_dir", "DeepPaperNote_output")).strip() or "DeepPaperNote_output"
    output_path = workspace_root / Path(
        *safe_relative_path_parts(output_dir, "workspace_output_dir")
    )
    return ("workspace", require_path_within(workspace_root, output_path, "workspace_output_dir"))


def safe_relative_path_parts(value: str | Path, field: str) -> tuple[str, ...]:
    raw = str(value).strip()
    if not raw:
        return ()
    windows_path = PureWindowsPath(raw)
    if (
        Path(raw).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise RuntimeError(
            f"Unsafe {field}: expected a relative path inside the Save Target: {raw}"
        )
    parts = tuple(part for part in re.split(r"[\\/]+", raw) if part and part != ".")
    if ".." in parts:
        raise RuntimeError(
            f"Unsafe {field}: expected a relative path inside the Save Target: {raw}"
        )
    return parts


def require_path_within(root: str | Path, path: str | Path, field: str) -> Path:
    root_path = Path(root).expanduser().resolve()
    candidate = Path(path).expanduser().resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise RuntimeError(f"Unsafe {field}: path escapes the Save Target: {path}") from exc
    return Path(path)


def resolve_note_asset_dir(note_path: str | Path, asset_subdir: str) -> Path:
    asset_subdir_parts = safe_relative_path_parts(asset_subdir, "asset_subdir")
    if not asset_subdir_parts:
        raise RuntimeError(
            "Unsafe asset_subdir: expected a relative directory inside the Save Target"
        )
    note_dir = Path(note_path).parent
    return require_path_within(
        note_dir,
        note_dir / Path(*asset_subdir_parts),
        "asset_subdir",
    )


DOMAIN_RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "domain_rules.yaml"
DOMAIN_LIST_KEYS = (
    "aliases",
    "keywords",
    "methods",
    "application_keywords",
    "method_keywords",
    "specialized_folders",
)
DOMAIN_SECTIONS = ("domains", "fallback_domains")
DOMAIN_SECTION_ALIASES = {"application_domains": "domains"}
DEFAULT_DOMAIN_RULES: dict[str, list[dict[str, Any]]] = {
    "domains": [
        {
            "label": "医疗健康",
            "aliases": ["healthcare", "medical", "clinical medicine"],
            "specialized_folders": ["心理健康"],
            "keywords": [
                "clinical",
                "patient",
                "patients",
                "depression",
                "anxiety",
                "mental health",
                "psychiatric",
                "psychology",
                "therapy",
                "counseling",
                "symptom",
                "diagnosis",
                "screening",
                "hospital",
                "healthcare",
                "medical",
            ],
            "methods": [],
        },
        {
            "label": "法律",
            "aliases": ["legal", "law"],
            "keywords": [
                "legal",
                "law",
                "court",
                "judge",
                "contract",
                "statute",
                "regulation",
                "litigation",
                "case law",
            ],
            "methods": [],
        },
        {
            "label": "教育",
            "aliases": ["education", "educational"],
            "keywords": [
                "education",
                "student",
                "teacher",
                "classroom",
                "curriculum",
                "tutoring",
                "learning analytics",
                "pedagogy",
            ],
            "methods": [],
        },
        {
            "label": "金融",
            "aliases": ["finance", "financial"],
            "keywords": [
                "finance",
                "financial",
                "stock",
                "market",
                "trading",
                "portfolio",
                "risk",
                "credit",
                "banking",
                "investment",
            ],
            "methods": [],
        },
        {
            "label": "机器人",
            "aliases": ["robotics", "robotic"],
            "keywords": [
                "robot",
                "robotics",
                "robotic",
                "manipulation",
                "navigation",
                "control policy",
                "locomotion",
                "autonomous driving",
                "embodied",
            ],
            "methods": ["diffusion policy"],
        },
        {
            "label": "软件工程",
            "aliases": ["software engineering"],
            "keywords": [
                "software engineering",
                "code generation",
                "program repair",
                "bug",
                "repository",
                "developer",
                "code review",
                "test generation",
                "compiler",
            ],
            "methods": [],
        },
        {
            "label": "生物医学",
            "aliases": ["biomedical", "bioinformatics"],
            "keywords": [
                "biomedical",
                "genomics",
                "protein",
                "drug discovery",
                "molecular",
                "cell",
                "gene",
                "bioinformatics",
            ],
            "methods": [],
        },
        {
            "label": "心理健康",
            "route_to": "医疗健康",
            "aliases": ["mental health", "psychology", "psychiatry"],
            "keywords": [
                "depression",
                "anxiety",
                "mental health",
                "psychiatric",
                "psychology",
                "therapy",
                "counseling",
                "symptom",
            ],
            "methods": [],
        },
        {
            "label": "推荐系统",
            "aliases": ["recommender systems", "recommendation"],
            "keywords": [
                "recommendation",
                "recommender",
                "ctr prediction",
                "ranking system",
                "personalization",
            ],
            "methods": [],
        },
    ],
    "fallback_domains": [
        {
            "label": "大模型",
            "aliases": ["llm", "large language model", "language model", "foundation model"],
            "keywords": [
                "large language model",
                "llm",
                "foundation model",
                "gpt",
                "transformer",
                "instruction tuning",
                "pretrain",
                "pre-training",
                "language model",
                "agent",
                "multi-agent",
                "multi agent",
                "reasoning",
                "multimodal",
                "retrieval-augmented generation",
                "rag",
                "in-context learning",
                "long-context",
                "long context",
                "mixture-of-experts",
                "mixture of experts",
                "moe",
                "alignment",
                "rlhf",
            ],
            "methods": [],
        },
        {
            "label": "机器学习",
            "aliases": ["machine learning", "ml"],
            "keywords": [
                "machine learning",
                "deep learning",
                "neural network",
                "representation learning",
                "reinforcement learning",
                "computer vision",
                "graph neural network",
                "speech recognition",
            ],
            "methods": [],
        },
    ],
}


def _copy_default_domain_rules() -> dict[str, list[dict[str, Any]]]:
    return {
        section: [
            {key: list(value) if isinstance(value, list) else value for key, value in rule.items()}
            for rule in DEFAULT_DOMAIN_RULES[section]
        ]
        for section in DOMAIN_SECTIONS
    }


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _parse_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_inline_yaml_list(value: str) -> list[str]:
    items: list[str] = []
    current = []
    in_single = False
    in_double = False
    for char in value:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "," and not in_single and not in_double:
            item = _parse_yaml_scalar("".join(current))
            if item:
                items.append(item)
            current = []
            continue
        current.append(char)
    item = _parse_yaml_scalar("".join(current))
    if item:
        items.append(item)
    return items


def _parse_yaml_value(value: str) -> str | list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return _split_inline_yaml_list(value[1:-1])
    return _parse_yaml_scalar(value)


def _parse_domain_rules_yaml(text: str) -> dict[str, list[dict[str, Any]]]:
    rules: dict[str, list[dict[str, Any]]] = {section: [] for section in DOMAIN_SECTIONS}
    section = ""
    current: dict[str, Any] | None = None
    current_list_key = ""

    for raw_line in text.splitlines():
        line = _strip_yaml_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            current = None
            current_list_key = ""
            key, _, value = stripped.partition(":")
            key = DOMAIN_SECTION_ALIASES.get(key.strip(), key.strip())
            if key in DOMAIN_SECTIONS:
                section = key
                if value.strip() == "[]":
                    rules[section] = []
            else:
                section = ""
            continue

        if section not in rules:
            continue

        if indent <= 2 and stripped.startswith("- "):
            current = {}
            rules[section].append(current)
            current_list_key = ""
            item = stripped[2:].strip()
            if item:
                key, separator, value = item.partition(":")
                if not separator:
                    raise ValueError("Domain list entries must be mappings.")
                current[key.strip()] = _parse_yaml_value(value)
            continue

        if current is None:
            raise ValueError("Domain properties must belong to a list entry.")

        if stripped.startswith("- "):
            if not current_list_key:
                raise ValueError("List item without a list key.")
            item = _parse_yaml_scalar(stripped[2:].strip())
            if item:
                current.setdefault(current_list_key, []).append(item)
            continue

        key, separator, value = stripped.partition(":")
        if not separator:
            raise ValueError("Expected key/value domain property.")
        key = key.strip()
        value = value.strip()
        if key in DOMAIN_LIST_KEYS:
            parsed = _parse_yaml_value(value) if value else []
            current[key] = parsed if isinstance(parsed, list) else [parsed]
            current_list_key = key if not value else ""
        else:
            current[key] = _parse_yaml_scalar(value)
            current_list_key = ""

    return rules


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_domain_rule(raw: dict[str, Any]) -> dict[str, Any] | None:
    label = str(raw.get("label", "")).strip()
    if not label:
        return None
    rule: dict[str, Any] = {"label": label}
    route_to = str(raw.get("route_to", "")).strip()
    if route_to:
        rule["route_to"] = route_to
    rule["aliases"] = _as_string_list(raw.get("aliases"))
    rule["specialized_folders"] = _as_string_list(raw.get("specialized_folders"))
    rule["keywords"] = _as_string_list(raw.get("keywords")) + _as_string_list(
        raw.get("application_keywords")
    )
    rule["methods"] = _as_string_list(raw.get("methods")) + _as_string_list(
        raw.get("method_keywords")
    )
    return rule


def _normalize_domain_rules(
    raw: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]] | None:
    normalized: dict[str, list[dict[str, Any]]] = {section: [] for section in DOMAIN_SECTIONS}
    for section in DOMAIN_SECTIONS:
        items = raw.get(section)
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                return None
            rule = _normalize_domain_rule(item)
            if rule is None:
                return None
            normalized[section].append(rule)
    if not normalized["domains"] and not normalized["fallback_domains"]:
        return None
    return normalized


def load_domain_rules() -> dict[str, list[dict[str, Any]]]:
    try:
        if not DOMAIN_RULES_PATH.exists():
            return _copy_default_domain_rules()
        parsed = _parse_domain_rules_yaml(DOMAIN_RULES_PATH.read_text(encoding="utf-8-sig"))
        normalized = _normalize_domain_rules(parsed)
        if normalized is None:
            return _copy_default_domain_rules()
        return normalized
    except Exception:
        return _copy_default_domain_rules()


def _normalized_domain_label(value: str) -> str:
    return normalize_whitespace(value).lower()


def _term_in_text(term: str, text: str) -> bool:
    normalized = _normalized_domain_label(term)
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._+/#-]*", normalized):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text) is not None
    return normalized in text


def _count_term_hits(terms: list[str], text: str) -> int:
    return sum(1 for term in terms if _term_in_text(term, text))


def _domain_route_label(rule: dict[str, Any]) -> str:
    return str(rule.get("route_to") or rule.get("label") or "").strip()


def _domain_match_terms(rule: dict[str, Any]) -> list[str]:
    terms = [str(rule.get("label", "")).strip(), _domain_route_label(rule)]
    terms.extend(_as_string_list(rule.get("aliases")))
    terms.extend(_as_string_list(rule.get("specialized_folders")))
    return [term for term in terms if term]


def _domain_name_matches_rule(domain_name: str, rule: dict[str, Any]) -> bool:
    name = _normalized_domain_label(domain_name)
    return any(_normalized_domain_label(term) == name for term in _domain_match_terms(rule))


def _rules_for_label(
    rules: dict[str, list[dict[str, Any]]],
    label: str,
) -> list[tuple[str, dict[str, Any]]]:
    normalized_label = _normalized_domain_label(label)
    matches: list[tuple[str, dict[str, Any]]] = []
    for section in DOMAIN_SECTIONS:
        for rule in rules[section]:
            route_label = _normalized_domain_label(_domain_route_label(rule))
            terms = [_normalized_domain_label(term) for term in _domain_match_terms(rule)]
            if normalized_label == route_label or normalized_label in terms:
                matches.append((section, rule))
    return matches


def _score_domain_for_inference(rule: dict[str, Any], text: str, *, fallback: bool) -> int:
    label_hits = _count_term_hits([str(rule.get("label", "")), _domain_route_label(rule)], text)
    alias_hits = _count_term_hits(_as_string_list(rule.get("aliases")), text)
    specialized_hits = _count_term_hits(_as_string_list(rule.get("specialized_folders")), text)
    keyword_hits = _count_term_hits(_as_string_list(rule.get("keywords")), text)
    method_hits = _count_term_hits(_as_string_list(rule.get("methods")), text)
    if fallback:
        return (label_hits * 80) + (alias_hits * 60) + (keyword_hits * 12) + (method_hits * 4)
    return (
        (label_hits * 100)
        + (alias_hits * 80)
        + (specialized_hits * 80)
        + (keyword_hits * 20)
        + (method_hits * 3)
    )


def infer_domain_label(title: str, abstract: str = "") -> str:
    lower = normalize_whitespace(f"{title} {abstract}").lower()
    rules = load_domain_rules()
    scored: list[tuple[int, str]] = []
    for rule in rules["domains"]:
        score = _score_domain_for_inference(rule, lower, fallback=False)
        if score > 0:
            scored.append((score, _domain_route_label(rule)))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]

    for rule in rules["fallback_domains"]:
        score = _score_domain_for_inference(rule, lower, fallback=True)
        if score > 0:
            scored.append((score, _domain_route_label(rule)))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][1]

    paper_type, _ = infer_paper_type(title, abstract)
    if paper_type == "clinical_or_psychology_empirical":
        return "医疗健康"
    if paper_type == "AI_method":
        return "机器学习"
    return "未分类"


def is_probable_paper_folder(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(
        (path / marker).exists()
        for marker in (
            f"{path.name}.md",
            f"{path.name}.zh-CN.md",
            f"{path.name}.en.md",
            ".deeppapernote.json",
        )
    )


def existing_domain_dirs(config: dict[str, Any]) -> list[str]:
    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    base_dir = root_path / Path(papers_dir) if output_mode == "obsidian" else root_path
    if not base_dir.exists() or not base_dir.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if is_probable_paper_folder(child):
            continue
        names.append(child.name)
    return names


def domain_name_score(domain_name: str, label: str, title: str, abstract: str) -> int:
    name = domain_name.strip().lower()
    score = 0
    if name == label.lower():
        score += 100
    lower = normalize_whitespace(f"{title} {abstract}").lower()
    rules = load_domain_rules()
    label_rules = _rules_for_label(rules, label)
    label_is_application = any(section == "domains" for section, _ in label_rules)
    known_fallback_name = any(
        _domain_name_matches_rule(domain_name, rule) for rule in rules["fallback_domains"]
    )

    for section, rule in label_rules:
        if not _domain_name_matches_rule(domain_name, rule):
            continue
        score += 90 if section == "domains" else 70
        score += _count_term_hits(_as_string_list(rule.get("aliases")), lower) * 20
        score += _count_term_hits(_as_string_list(rule.get("specialized_folders")), lower) * 20
        score += _count_term_hits(_as_string_list(rule.get("keywords")), lower) * 10
        score += _count_term_hits(_as_string_list(rule.get("methods")), lower) * 2

    if not (label_is_application and known_fallback_name) and _term_in_text(domain_name, lower):
        score += 15
    return score


def resolve_domain_subdir(
    config: dict[str, Any],
    *,
    title: str,
    abstract: str = "",
    subdir: str = "",
) -> str:
    if subdir.strip():
        return subdir.strip()
    label = infer_domain_label(title, abstract)
    existing = existing_domain_dirs(config)
    if existing:
        best_name = ""
        best_score = -1
        for domain_name in existing:
            score = domain_name_score(domain_name, label, title, abstract)
            if score > best_score:
                best_name = domain_name
                best_score = score
        if best_name and best_score > 0:
            return best_name
    return label


def resolve_obsidian_note_path(
    config: dict[str, Any],
    *,
    title: str,
    subdir: str = "",
    filename: str = "",
) -> Path:
    def path_from_parts(parts: tuple[str, ...]) -> Path:
        return Path(*parts) if parts else Path()

    def starts_with_parts(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
        return bool(prefix) and parts[: len(prefix)] == prefix

    output_mode, root_path = resolve_note_output_mode(config)
    papers_dir = str(config.get("papers_dir", "Research/Papers")).strip() or "Research/Papers"
    papers_dir_parts = safe_relative_path_parts(papers_dir, "papers_dir")
    relative_dir = path_from_parts(papers_dir_parts) if output_mode == "obsidian" else Path()
    if subdir:
        subdir_parts = safe_relative_path_parts(subdir, "subdir")
        subdir_path = path_from_parts(subdir_parts)
        if output_mode == "obsidian" and starts_with_parts(subdir_parts, papers_dir_parts):
            relative_dir = subdir_path
        else:
            relative_dir = relative_dir / subdir_path
    note_slug = slugify_filename(title)
    target_name = filename.strip() or f"{note_slug}.md"
    target_name_parts = safe_relative_path_parts(target_name, "filename")
    target_name_path = path_from_parts(target_name_parts)
    folder_name = target_name_path.stem or note_slug
    folder_aliases = {folder_name, note_slug, slugify_filename(folder_name)}
    normalized_folder_aliases = {alias.lower() for alias in folder_aliases if alias}
    if relative_dir.name.lower() in normalized_folder_aliases:
        target_path = root_path / relative_dir / target_name_path
    else:
        target_path = root_path / relative_dir / folder_name / target_name_path
    save_target = (
        root_path / path_from_parts(papers_dir_parts)
        if output_mode == "obsidian"
        else root_path
    )
    require_path_within(root_path, save_target, "papers_dir")
    return require_path_within(save_target, target_path, "note path")
