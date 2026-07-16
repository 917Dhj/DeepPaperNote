# Paper Glossary Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fast, first-use-configured paper-glossary workflow that proposes length-aware terms, non-destructively enriches a shared Obsidian term library, and adds safe first-occurrence links to the explicit article Markdown.

**Architecture:** Keep paper evidence intake limited to `*_source_manifest.json` and `*_raw_sections.jsonl`. Add a device-local configuration layer, deterministic candidate prefilter followed by one host semantic review, deterministic library inventory, one batched model payload for new/thin entries, and a separate atomic Markdown linker. DeepPaperNote remains untouched.

**Tech Stack:** Python 3.10+, standard library only, Markdown/JSON/JSONL, pytest 8+, existing repository scripts and contracts.

## Global Constraints

- Modify only `skills/paper-glossary/`; do not modify `skills/deeppapernote/` or root plugin manifests.
- Keep `*_source_manifest.json` and `*_raw_sections.jsonl` as the only paper-content collaboration contract.
- Do not add dependencies.
- Do not guess an article Markdown path from a title, PDF, or `full_text_md_path`.
- Require the configured term directory and article Markdown to belong to the same nearest Obsidian vault.
- Preserve all user-authored term-note content; enrichment may only add missing structured fields and a missing occurrence.
- Use TDD: run every named failing test before implementation and rerun it after the minimal change.
- Preserve the current uncommitted selection-gate work and build on it rather than reverting it.
- Do not commit or push during implementation. Each task ends with a diff/test checkpoint; commit only after the user explicitly approves the completed implementation.
- Before editing skill behavior, invoke `superpowers:writing-skills`; before each behavior change, invoke `superpowers:test-driven-development`.

## File Map

| File | Responsibility |
| --- | --- |
| `scripts/glossary_config.py` | Device-local config, nearest-vault validation, same-vault article validation, article hash |
| `scripts/configure_glossary.py` | Configure/show/reset/validate CLI for first-use interaction |
| `scripts/plan_glossary.py` | Effective-prose cleanup, dynamic limits, grounded candidate pool, selected-term triage |
| `scripts/glossary_library.py` | Alias index, existing-note inspection, completeness classification, additive field insertion |
| `scripts/inspect_glossary_library.py` | CLI inventory of selected terms before model generation |
| `scripts/write_glossary_terms.py` | Preflight operation validation and create/enrich/reuse writes |
| `scripts/link_glossary_terms.py` | Protected-region-aware, hash-guarded, atomic article linking |
| `scripts/lint_glossary.py` | Lint one or more changed notes without scanning the full library |
| `scripts/glossary_common.py` | Shared JSON emission and elapsed-time helper |
| `SKILL.md` and `agents/openai.yaml` | Cross-host first-use, preview, selection, write, and link instructions |
| `README.md` and `references/file-contract.md` | User setup and artifact contracts |
| `tests/` | Focused unit, contract, and end-to-end coverage |

## Spec Coverage

| Design section | Implemented by |
| --- | --- |
| Goals, non-goals, inputs, and boundaries | Global constraints; Tasks 1 and 5 |
| First-use configuration | Task 1 |
| Candidate workflow and dynamic limits | Task 2 |
| Selection, adaptive generation, and old-note enrichment | Tasks 3 and 5 |
| Article outlinks and write safety | Task 4 |
| Performance and stage timing | Task 6 |
| Result and failure reporting | Tasks 1, 3, 4, and 6 |
| Implementation surface and verification | Tasks 1-6 |
| Current demo cleanup and real acceptance | Task 7 |

---

### Task 1: Device-local Obsidian configuration

**Files:**
- Create: `skills/paper-glossary/scripts/glossary_config.py`
- Create: `skills/paper-glossary/scripts/configure_glossary.py`
- Create: `skills/paper-glossary/tests/test_glossary_config.py`

**Interfaces:**
- Produces: `find_vault_root(path: Path) -> Path | None`
- Produces: `configure_terms_dir(terms_dir: Path, config_path: Path | None = None) -> dict[str, str]`
- Produces: `load_config(config_path: Path | None = None) -> dict[str, str] | None`
- Produces: `resolve_terms_dir(config: dict[str, str]) -> Path`
- Produces: `validate_article(article: Path, config: dict[str, str]) -> dict[str, str]`
- Produces CLI modes: `--terms-dir`, `--show`, `--reset`, `--validate-article`, plus `--config-path` and `--output`

- [ ] **Step 1: Write failing configuration and vault-boundary tests**

Add tests that exercise an existing term folder, a not-yet-created child folder, nearest nested vault selection, a non-vault path, same-vault article validation, cross-vault rejection, config reuse, reset, and missing configured paths. Core tests must include:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from glossary_config import (
    configure_terms_dir,
    load_config,
    resolve_terms_dir,
    validate_article,
)


def test_configure_terms_dir_persists_nearest_vault_and_relative_subdir(
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    inner = outer / "research"
    (outer / ".obsidian").mkdir(parents=True)
    (inner / ".obsidian").mkdir()
    terms_dir = inner / "book" / "术语"
    config_path = tmp_path / "device" / "config.json"

    payload = configure_terms_dir(terms_dir, config_path)

    assert payload == {
        "vault_root": str(inner.resolve()),
        "terms_subdir": str(Path("book") / "术语"),
    }
    assert terms_dir.is_dir()
    assert load_config(config_path) == payload
    assert resolve_terms_dir(payload) == terms_dir.resolve()


def test_validate_article_rejects_other_vault(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / ".obsidian").mkdir(parents=True)
    (second / ".obsidian").mkdir(parents=True)
    article = second / "Paper.md"
    article.write_text("# Paper\n", encoding="utf-8")
    config = configure_terms_dir(first / "术语", tmp_path / "config.json")

    with pytest.raises(SystemExit, match="same Obsidian vault"):
        validate_article(article, config)


def test_load_config_returns_none_before_first_use(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.json") is None
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_glossary_config.py --basetemp .pytest-tmp-paper-glossary-config
```

Expected: collection fails because `glossary_config` does not exist.

- [ ] **Step 3: Implement config resolution and validation**

Use `Path.resolve(strict=False)` before containment checks and walk from the selected path or its nearest existing parent. The core implementation must follow this shape:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONFIG_DIRNAME = ".paper-glossary"
CONFIG_FILENAME = "config.json"


def default_config_path() -> Path:
    return Path.home() / CONFIG_DIRNAME / CONFIG_FILENAME


def find_vault_root(path: Path) -> Path | None:
    current = path.expanduser().resolve(strict=False)
    while not current.exists() and current != current.parent:
        current = current.parent
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate.resolve()
    return None


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def configure_terms_dir(
    terms_dir: Path, config_path: Path | None = None
) -> dict[str, str]:
    resolved = terms_dir.expanduser().resolve(strict=False)
    vault = find_vault_root(resolved)
    if vault is None or not _is_within(resolved, vault):
        raise SystemExit("Term directory must be inside an Obsidian vault containing .obsidian.")
    resolved.mkdir(parents=True, exist_ok=True)
    payload = {
        "vault_root": str(vault),
        "terms_subdir": str(resolved.relative_to(vault)),
    }
    target = (config_path or default_config_path()).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_config(config_path: Path | None = None) -> dict[str, str] | None:
    target = (config_path or default_config_path()).expanduser()
    if not target.is_file():
        return None
    payload = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid paper-glossary config object: {target}")
    return {"vault_root": str(payload.get("vault_root", "")), "terms_subdir": str(payload.get("terms_subdir", ""))}


def resolve_terms_dir(config: dict[str, str]) -> Path:
    vault = Path(config.get("vault_root", "")).expanduser().resolve(strict=False)
    terms_dir = (vault / config.get("terms_subdir", "")).resolve(strict=False)
    if not (vault / ".obsidian").is_dir() or not terms_dir.is_dir() or not _is_within(terms_dir, vault):
        raise SystemExit("Configured Obsidian term directory is missing or invalid; configure it again.")
    return terms_dir


def validate_article(article: Path, config: dict[str, str]) -> dict[str, str]:
    resolved = article.expanduser().resolve()
    if resolved.suffix.lower() != ".md" or not resolved.is_file():
        raise SystemExit(f"Article Markdown not found: {resolved}")
    article_vault = find_vault_root(resolved)
    configured_vault = Path(config["vault_root"]).expanduser().resolve()
    if article_vault != configured_vault:
        raise SystemExit("Article and term directory must be inside the same Obsidian vault.")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return {"article_path": str(resolved), "article_sha256": digest}
```

Keep JSON formatting readable and use `SystemExit` messages that the host can relay directly.

- [ ] **Step 4: Add the small configuration CLI**

Implement mutually exclusive configure/show/reset/validate modes. `--show` must return `workflow_state: "needs_configuration"` when no config exists instead of failing. `--validate-article` must include the resolved `terms_dir`, `article_path`, and `article_sha256` in its JSON output. `--reset` removes only the config file and never removes a vault or term directory.

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

Run the command from Step 2. Expected: all tests in `test_glossary_config.py` pass.

- [ ] **Step 6: Task 1 checkpoint without commit**

Run:

```powershell
git diff --check -- skills/paper-glossary/scripts/glossary_config.py skills/paper-glossary/scripts/configure_glossary.py skills/paper-glossary/tests/test_glossary_config.py
```

Expected: exit code 0. Record `git status --short`; do not stage or commit.

---

### Task 2: Length-aware deterministic candidate pool

**Files:**
- Modify: `skills/paper-glossary/scripts/plan_glossary.py:14-390`
- Modify: `skills/paper-glossary/tests/test_plan_glossary.py`

**Interfaces:**
- Produces: `effective_prose_text(records: list[dict[str, Any]]) -> str`
- Produces: `shortlist_limit(effective_characters: int) -> int`
- Changes: `propose_candidates(records)` returns a grounded pool capped at `shortlist_limit + 10`
- Changes proposal JSON: `workflow_state`, `next_action`, `summary.effective_body_characters`, `summary.shortlist_limit`, `summary.pool_candidates`
- Preserves: selected-term triage and unresolved-selection rejection

- [ ] **Step 1: Replace the fixed-limit test with failing tier and noise tests**

Add parameterized limit tests and a chapter-style regression:

```python
@pytest.mark.parametrize(
    ("characters", "expected"),
    [(9_999, 10), (10_000, 18), (29_999, 18), (30_000, 25), (59_999, 25), (60_000, 35)],
)
def test_shortlist_limit_uses_effective_body_length(characters: int, expected: int) -> None:
    assert shortlist_limit(characters) == expected


def test_propose_filters_code_noise_and_keeps_emphasized_core_terms() -> None:
    records = [
        {
            "record_type": "section",
            "section_id": "sec:chapter",
            "kind": "chapter",
            "title": "智能体经典范式",
            "text": (
                "**ReAct**、**Plan-and-Solve** 与 **Reflection** 是三种经典范式。\n"
                "<strong>SerpApi</strong> 为智能体提供搜索能力。\n"
                "```python\nLLM_API_KEY = 'KEY'\nREACT_PROMPT_TEMPLATE = 'MODEL'\n"
                "print('HUAWEI phone result')\n```\n"
            ),
        },
        {
            "record_type": "section",
            "section_id": "sec:refs",
            "kind": "references",
            "title": "References",
            "text": "SERPAPI TEMPLATE PLANNER",
        },
    ]

    terms = {item["term"] for item in propose_candidates(records)}

    assert {"ReAct", "Plan-and-Solve", "Reflection", "SerpApi"} <= terms
    assert terms.isdisjoint({"KEY", "MODEL", "TEMPLATE", "HUAWEI"})
    assert not ({"ReAct", "REACT"} <= terms)


def test_proposal_reports_semantic_review_and_dynamic_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _run_proposal(tmp_path, monkeypatch, _records())
    assert payload["workflow_state"] == "awaiting_semantic_review"
    assert payload["next_action"] == "review_candidate_pool_then_present_and_wait"
    assert payload["summary"]["shortlist_limit"] == 10
    assert payload["summary"]["pool_candidates"] == len(payload["candidates"])
```

Update imports to include `shortlist_limit`. Keep the existing no-candidate terminal-state test.

- [ ] **Step 2: Run candidate tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_plan_glossary.py --basetemp .pytest-tmp-paper-glossary-plan
```

Expected: failures for the missing `shortlist_limit`, code-noise candidates, missing `Reflection`, and old workflow-state fields.

- [ ] **Step 3: Implement effective-prose cleanup and limits**

Add standard-library regexes and helpers. Preserve link labels while removing destinations, remove reference tails inside monolithic Markdown records, and count non-whitespace characters:

```python
FENCED_CODE_RE = re.compile(r"(?ms)^(?:`{3,}|~{3,})[^\n]*\n.*?^(?:`{3,}|~{3,})\s*$")
INLINE_CODE_RE = re.compile(r"`+[^`\n]+`+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
URL_RE = re.compile(r"https?://\S+")
REFERENCE_TAIL_RE = re.compile(r"(?ims)^#{1,6}\s*(?:references|参考文献|引用)\s*$.*\Z")
EMPHASIS_RE = re.compile(r"(?:\*\*|__)([^\n*_]{2,80})(?:\*\*|__)")
STRONG_RE = re.compile(r"(?is)<strong>([^<]{2,80})</strong>")


def _candidate_prose(text: str) -> str:
    cleaned = FENCED_CODE_RE.sub("\n", text)
    cleaned = INLINE_CODE_RE.sub(" ", cleaned)
    cleaned = MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = URL_RE.sub(" ", cleaned)
    return REFERENCE_TAIL_RE.sub("", cleaned)


def effective_prose_text(records: list[dict[str, Any]]) -> str:
    return "\n".join(
        _candidate_prose(str(record.get("text", "")))
        for record in _evidence_records(records)
    )


def shortlist_limit(effective_characters: int) -> int:
    if effective_characters < 10_000:
        return 10
    if effective_characters < 30_000:
        return 18
    if effective_characters < 60_000:
        return 25
    return 35
```

Use cleaned record copies only for candidate extraction. Continue using original evidence records for occurrences and snippets.

- [ ] **Step 4: Add grounded emphasis extraction and casefold deduplication**

Change `add()` to use `unicodedata.normalize("NFKC", term).casefold()` as the candidate key. Prefer the first prose form and never emit a second case-only form. Feed bold and `<strong>` terms through conservative length/shape checks so `Reflection` and `SerpApi` survive without admitting sentences. Cap the deterministic pool at `shortlist_limit + 10`; the host semantic pass may present fewer than the final limit and may not invent terms outside this pool.

- [ ] **Step 5: Emit the semantic-review contract**

For a nonempty pool emit:

```python
{
    "workflow_state": "awaiting_semantic_review",
    "next_action": "review_candidate_pool_then_present_and_wait",
    "summary": {
        "effective_body_characters": effective_characters,
        "shortlist_limit": display_limit,
        "pool_candidates": len(candidates),
    },
}
```

For an empty pool preserve `workflow_state: "no_candidates"` and `next_action: "report_no_candidates"`.

- [ ] **Step 6: Run Task 2 tests and verify GREEN**

Run the command from Step 2. Expected: all `test_plan_glossary.py` tests pass.

- [ ] **Step 7: Task 2 checkpoint without commit**

Run `git diff --check` on the two Task 2 files and record the diff. Do not stage or commit.

---

### Task 3: Existing-library inventory and non-destructive enrichment

**Files:**
- Create: `skills/paper-glossary/scripts/glossary_library.py`
- Create: `skills/paper-glossary/scripts/inspect_glossary_library.py`
- Create: `skills/paper-glossary/tests/test_glossary_library.py`
- Modify: `skills/paper-glossary/scripts/write_glossary_terms.py:64-231`
- Modify: `skills/paper-glossary/tests/test_write_and_lint_glossary.py`

**Interfaces:**
- Produces: `inspect_selected_terms(selected: list[dict[str, Any]], terms_dir: Path) -> list[dict[str, Any]]`
- Inventory CLI requires `--source-manifest`, optional `--raw-sections`, and saved `--reviewed-shortlist`; it consumes the saved triage artifact as `--terms triage.json`.
- Produces inventory states: `new`, `existing_thin`, `existing_complete`
- Produces: `missing_concept_fields(text: str) -> list[str]`
- Produces: `add_missing_concept_fields(text: str, patch: dict[str, Any]) -> tuple[str, list[str]]`
- Produces: `write_glossary_entries(glossary: dict[str, Any], inventory: dict[str, Any], terms_dir: Path, paper_link: str) -> dict[str, Any]`
- Changes glossary-entry contract: each entry has `operation` equal to `create`, `enrich`, or `reuse`
- Changes writer CLI: require `--inventory` for the optimized workflow and validate the entire batch before writes
- Changes writer result: include `forms`, `fields_added`, `occurrence_added`, and exact `link_stem`

- [ ] **Step 1: Write failing inventory and preservation tests**

Tests must prove classification by aliases and additive behavior:

```python
def test_inventory_classifies_new_thin_and_complete_notes(tmp_path: Path) -> None:
    terms_dir = tmp_path / "术语"
    terms_dir.mkdir()
    (terms_dir / "LLM.md").write_text(
        "---\naliases:\n  - \"大语言模型\"\n---\n\n# LLM\n\n"
        "## 概念解释\n- 定义：语言模型。\n- 置信度：中\n\n"
        "## 在论文中的出现\n- [[OldPaper]]：旧出处\n",
        encoding="utf-8",
    )
    (terms_dir / "ReAct.md").write_text(
        "# ReAct\n\n## 概念解释\n"
        "- 定义：交替进行推理与行动的智能体范式。\n"
        "- 详解：模型在工具观察后继续推理。\n"
        "- 直觉：边想边做。\n"
        "- 置信度：高\n\n"
        "## 在论文中的出现\n- [[OldPaper]]：旧出处\n",
        encoding="utf-8",
    )
    selected = [
        {"term": "大语言模型", "surface_forms": ["LLM", "大语言模型"]},
        {"term": "ReAct", "surface_forms": ["ReAct"]},
        {"term": "Reflection", "surface_forms": ["Reflection"]},
    ]

    items = inspect_selected_terms(selected, terms_dir)
    states = {item["term"]: item["state"] for item in items}

    assert states == {
        "大语言模型": "existing_thin",
        "ReAct": "existing_complete",
        "Reflection": "new",
    }


def test_enrichment_adds_only_missing_fields_and_preserves_custom_text() -> None:
    original = (
        "# LLM\n\n用户自己的说明。\n\n## 概念解释\n"
        "- 定义：语言模型。\n- 置信度：中\n\n## 自定义\n不要改动。\n"
    )
    updated, fields = add_missing_concept_fields(
        original,
        {"elaboration": "用于智能体推理。", "intuition": "智能体的大脑。"},
    )

    assert fields == ["elaboration", "intuition"]
    assert "用户自己的说明。" in updated
    assert "## 自定义\n不要改动。" in updated
    assert "- 定义：语言模型。" in updated
    assert updated.count("- 详解：用于智能体推理。") == 1
    assert updated.count("- 直觉：智能体的大脑。") == 1
```

Add writer tests that reject an invalid operation before creating any file, enrich a thin note without replacing existing fields, append only a missing occurrence, and remain unchanged on a second identical run.

- [ ] **Step 2: Run Task 3 tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_glossary_library.py skills/paper-glossary/tests/test_write_and_lint_glossary.py --basetemp .pytest-tmp-paper-glossary-library
```

Expected: missing module/functions and old writer behavior fail.

- [ ] **Step 3: Implement deterministic library inspection**

Move frontmatter alias, heading-name, and alias-index parsing into `glossary_library.py`; re-import those names from `write_glossary_terms.py` so existing imports remain compatible. Define completeness as:

```python
CONCEPT_FIELDS = {
    "definition": "定义：",
    "elaboration": "详解：",
    "intuition": "直觉：",
    "distinction": "与相邻概念的区别：",
    "confidence": "置信度：",
}


def note_state(text: str) -> tuple[str, list[str]]:
    missing = missing_concept_fields(text)
    optional_present = sum(
        field not in missing for field in ("elaboration", "intuition", "distinction")
    )
    required_missing = any(field in missing for field in ("definition", "confidence"))
    state = "existing_thin" if required_missing or optional_present < 2 else "existing_complete"
    return state, missing
```

Inventory output must include `term`, `surface_forms`, `state`, `file`, `link_stem`, and `missing_fields`. A missing alias match is `new` with an empty file and link stem based on the canonical term.

- [ ] **Step 4: Implement additive field insertion**

Insert only labels named in `missing_fields`. Place definition first, optional explanatory fields before confidence, and confidence last. If the concept section is absent, append a complete concept section without changing existing custom sections. Never replace a line whose label already exists. Return the exact list of fields added so repeat runs can prove idempotency.

- [ ] **Step 5: Add inventory CLI**

`inspect_glossary_library.py` accepts `--terms` pointing to triage JSON, `--terms-dir`, `--source-manifest`, optional `--raw-sections`, `--reviewed-shortlist`, and `--output`. It emits:

```json
{
  "status": "ok",
  "script": "inspect_glossary_library.py",
  "results": [
    {
      "term": "LLM",
      "surface_forms": ["LLM", "大语言模型"],
      "state": "existing_thin",
      "file": "C:\\Notes\\Vault\\book\\术语\\LLM.md",
      "link_stem": "LLM",
      "missing_fields": ["elaboration", "intuition", "distinction"]
    }
  ]
}
```

- [ ] **Step 6: Extend writer preflight and operations**

Validate every entry against inventory before writing any file:

- `create`: inventory state must be `new`; require name, definition, confidence, occurrence.
- `enrich`: state must be `existing_thin`; allow only fields listed in `missing_fields`; require occurrence and a valid confidence when confidence is missing.
- `reuse`: state must be `existing_complete`; require occurrence; reject concept-field replacements.

Apply writes only after the full batch validates. Enrich missing fields, append the paper occurrence once, and report `created`, `enriched`, `updated`, or `unchanged`. Include all canonical and surface forms in each result for article matching.

- [ ] **Step 7: Run Task 3 tests and verify GREEN**

Run the command from Step 2. Expected: all inventory, writer, and existing lint tests pass.

- [ ] **Step 8: Task 3 checkpoint without commit**

Run `git diff --check` on Task 3 files and record status. Do not stage or commit.

---

### Task 4: Safe first-occurrence article linker

**Files:**
- Create: `skills/paper-glossary/scripts/link_glossary_terms.py`
- Create: `skills/paper-glossary/tests/test_link_glossary_terms.py`

**Interfaces:**
- Consumes: writer JSON `results[].link_stem` and `results[].forms`
- Consumes: configured vault and preview-time article SHA-256
- Produces: `link_article_terms(article: Path, mappings: list[dict[str, Any]], expected_sha256: str) -> dict[str, Any]`
- Produces result records: `linked`, `already_linked`, `not_found`

- [ ] **Step 1: Write failing protected-region, alias, hash, and idempotency tests**

Use a single fixture containing frontmatter, heading, ordinary prose, inline code, fenced code, URL, Markdown link, wiki link, and a references heading:

```python
def test_linker_links_first_safe_alias_and_skips_protected_regions(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text(
        "---\ntitle: ReAct\n---\n"
        "# ReAct heading\n\n"
        "`ReAct` and [ReAct](https://example.test) are protected.\n\n"
        "REACT combines reasoning and acting. ReAct appears again.\n\n"
        "```python\nReAct = 'code'\n```\n\n"
        "## References\nReAct paper\n",
        encoding="utf-8",
    )
    before = article.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    result = link_article_terms(
        article,
        [{"link_stem": "ReAct", "forms": ["ReAct", "REACT"]}],
        digest,
    )

    text = article.read_text(encoding="utf-8")
    assert "[[ReAct|REACT]] combines reasoning" in text
    assert "# ReAct heading" in text
    assert "`ReAct`" in text
    assert "```python\nReAct = 'code'\n```" in text
    assert text.count("[[ReAct|REACT]]") == 1
    assert result["summary"] == {"linked": 1, "already_linked": 0, "not_found": 0}


def test_linker_rejects_stale_article_hash(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("ReAct text\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="changed since preview"):
        link_article_terms(article, [{"link_stem": "ReAct", "forms": ["ReAct"]}], "0" * 64)


def test_linker_is_idempotent(tmp_path: Path) -> None:
    article = tmp_path / "Paper.md"
    article.write_text("ReAct text\n", encoding="utf-8")
    first_hash = hashlib.sha256(article.read_bytes()).hexdigest()
    link_article_terms(article, [{"link_stem": "ReAct", "forms": ["ReAct"]}], first_hash)
    linked_bytes = article.read_bytes()
    second_hash = hashlib.sha256(linked_bytes).hexdigest()
    result = link_article_terms(article, [{"link_stem": "ReAct", "forms": ["ReAct"]}], second_hash)

    assert article.read_bytes() == linked_bytes
    assert result["summary"]["already_linked"] == 1
```

Add tests for longer-term priority (`SerpApi` before `API`), no substring match, existing wiki links, UTF-8 BOM preservation, CRLF preservation, no safe occurrence, and same-vault validation through configured paths.

- [ ] **Step 2: Run linker tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_link_glossary_terms.py --basetemp .pytest-tmp-paper-glossary-link
```

Expected: collection fails because `link_glossary_terms` does not exist.

- [ ] **Step 3: Implement protected-range discovery**

Create spans for frontmatter at file start, heading lines, fenced blocks, inline code, Markdown links, wiki links, HTML tags, URLs, and the references tail. Merge overlapping spans before matching. The linker must test candidate match ranges against these spans and against previously planned edits.

Use ASCII-aware boundaries for ASCII forms:

```python
def term_pattern(form: str) -> re.Pattern[str]:
    escaped = re.escape(form)
    if form.isascii():
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)
```

Sort forms by descending length. Plan all edits against the original text, then apply them from the highest offset to the lowest so offsets remain stable.

- [ ] **Step 4: Implement canonical and alias wiki-link rendering**

Render exact canonical display as `[[link_stem]]`; otherwise preserve the matched source text as `[[link_stem|surface]]`. Before planning a new link, detect whether any existing wiki link already targets `link_stem` and report `already_linked`.

- [ ] **Step 5: Implement hash guard and atomic write**

Read bytes, detect UTF-8 BOM and the dominant newline style, verify SHA-256, edit decoded text, restore newline/BOM, write a temporary sibling, then use `os.replace`. Delete the temporary file in a `finally` block if replacement did not occur. If no edits exist, do not rewrite the article.

- [ ] **Step 6: Add CLI**

Accept `--input`, `--write-result`, `--expected-sha256`, `--config-path`, and `--output`. Load device config, reject a cross-vault article before hashing, use only successful writer results, and emit per-term status plus summary counts.

- [ ] **Step 7: Run Task 4 tests and verify GREEN**

Run the command from Step 2. Expected: all linker tests pass.

- [ ] **Step 8: Task 4 checkpoint without commit**

Run `git diff --check` on Task 4 files and record status. Do not stage or commit.

---

### Task 5: Cross-host skill workflow and public contracts

**Files:**
- Modify: `skills/paper-glossary/SKILL.md`
- Modify: `skills/paper-glossary/agents/openai.yaml`
- Modify: `skills/paper-glossary/README.md`
- Modify: `skills/paper-glossary/references/file-contract.md`
- Modify: `skills/paper-glossary/tests/test_skill_boundary.py`

**Interfaces:**
- Consumes Task 1 configure/show/validate operations
- Consumes Task 2 proposal pool and dynamic shortlist limit
- Consumes Task 3 inventory and action-aware glossary payload
- Consumes Task 4 article-link result
- Produces the same numbered Markdown interaction in terminals, Codex, and Claude Code

- [ ] **Step 1: Write failing workflow-contract tests**

Replace fixed-15 assertions and require the approved behavior:

```python
def test_skill_documents_first_use_dynamic_preview_and_link_consent() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for requirement in (
        "first use",
        ".paper-glossary",
        "same Obsidian vault",
        "semantic review",
        "effective body",
        "全部写入",
        "End the response and wait",
        "article Markdown",
        "first safe occurrence",
        "existing_thin",
        "Do not overwrite",
    ):
        assert requirement in text


def test_readme_explains_per_device_one_time_configuration() -> None:
    text = (SKILL_DIR / "README.md").read_text(encoding="utf-8")
    assert "~/.paper-glossary/config.json" in text
    assert "Windows" in text
    assert "macOS" in text
    assert "Linux" in text
    assert ".obsidian" in text


def test_contract_documents_dynamic_proposal_inventory_and_link_results() -> None:
    text = (SKILL_DIR / "references" / "file-contract.md").read_text(encoding="utf-8")
    for field in (
        '"shortlist_limit"',
        '"awaiting_semantic_review"',
        '"existing_thin"',
        '"operation": "enrich"',
        '"article_sha256"',
        '"already_linked"',
    ):
        assert field in text
```

Keep the existing self-contained boundary test that rejects imports from DeepPaperNote.

- [ ] **Step 2: Run skill-boundary tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_skill_boundary.py --basetemp .pytest-tmp-paper-glossary-skill
```

Expected: failures for missing first-use, dynamic, inventory, and linker documentation.

- [ ] **Step 3: Rewrite `SKILL.md` around the approved interaction**

Keep it concise and route details to references. The operational order must be explicit:

1. Show existing config or ask for an Obsidian term directory on first use.
2. Validate an explicit article Markdown when links are requested.
3. Run deterministic proposal.
4. Perform one grounded semantic review bounded by `shortlist_limit`.
5. Display every retained term as a numbered Markdown list, the term directory, article path, and both write effects.
6. State that no files have been written, end the response, and wait.
7. Resolve numbers/names/`全部写入` from the immediately preceding list.
8. Triage, inventory, generate one action-aware batch, preflight, write/enrich/reuse, link article, lint changed files, and report timing/status.

The default prompt in `agents/openai.yaml` must trigger preview and waiting, not immediate writing.

- [ ] **Step 4: Document first-use setup and contracts**

`README.md` must explain that each person configures a directory once per device, that the directory must be inside an Obsidian vault, where local config lives, how to show/reset it, and that the article must be in the same vault. Include Windows, macOS, and Linux command examples without assuming a fixed drive.

`file-contract.md` must document proposal metrics/state, inventory state, operation-aware entry schema, writer forms, article hash, and linker results. Preserve the manifest/raw-sections collaboration boundary.

- [ ] **Step 5: Run Task 5 tests and verify GREEN**

Run the command from Step 2. Expected: all boundary tests pass.

- [ ] **Step 6: Validate the skill metadata**

Run:

```powershell
python -X utf8 C:\Users\lenovo\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\paper-glossary
```

Expected: `Skill is valid!`

- [ ] **Step 7: Task 5 checkpoint without commit**

Run `git diff --check` on Task 5 files and record status. Do not stage or commit.

---

### Task 6: Changed-file linting, timing, and end-to-end verification

**Files:**
- Modify: `skills/paper-glossary/scripts/glossary_common.py`
- Modify: `skills/paper-glossary/scripts/lint_glossary.py`
- Modify: all paper-glossary CLIs created or changed in Tasks 1-4 to emit elapsed time
- Create: `skills/paper-glossary/tests/test_workflow_integration.py`
- Modify: `skills/paper-glossary/tests/test_write_and_lint_glossary.py`

**Interfaces:**
- Produces: `elapsed_ms(started: float) -> int`
- Changes lint CLI: repeatable `--input` values while preserving `--terms-dir`
- Produces end-to-end status across config, proposal, review recording, triage, inventory, write, link, and lint

- [ ] **Step 1: Write failing timing, multi-input lint, and integration tests**

The integration fixture must exercise the authenticated artifact chain in this exact order: proposal -> recorded review -> explicit selection -> triage -> authenticated inventory -> config-backed writer -> authenticated linker when an article is supplied -> changed-note lint. Its inventory invocation passes `--source-manifest`, optional `--raw-sections`, and `--reviewed-shortlist`; its writer and linker also pass the same saved `--triage`. Use CLI helpers that construct those authenticated commands rather than direct production helpers.

Add a helper test and a complete fixture workflow. The integration test must use temporary files and deterministic model-authored entry JSON:

```python
def test_complete_selected_flow_creates_enriches_links_and_lints(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    article = vault / "Chapter.md"
    article.write_text(
        "# 智能体范式\n\nReAct 与 Reflection 是两种智能体范式。\n",
        encoding="utf-8",
    )
    terms_dir = vault / "book" / "术语"
    config = configure_terms_dir(terms_dir, tmp_path / "config.json")
    article_info = validate_article(article, config)

    entries = {
        "entries": [
            {
                "name": "ReAct",
                "aliases": ["Reasoning and Acting"],
                "operation": "create",
                "definition": "交替进行推理与行动的智能体范式。",
                "confidence": "高",
                "occurrence": "章节正文首次介绍 ReAct。",
            },
            {
                "name": "Reflection",
                "aliases": ["反思"],
                "operation": "create",
                "definition": "利用反馈检查并改进先前结果的智能体范式。",
                "confidence": "高",
                "occurrence": "章节正文将 Reflection 列为经典范式。",
            },
        ]
    }

    inventory = {
        "results": _run_authenticated_inventory_cli(
            [
                {"term": "ReAct", "surface_forms": ["ReAct"]},
                {"term": "Reflection", "surface_forms": ["Reflection", "反思"]},
            ],
            terms_dir,
        )
    }
    write_result = _run_authenticated_writer_cli(entries, inventory, terms_dir, "Chapter")
    link_result = _run_authenticated_linker_cli(
        article,
        write_result["results"],
        article_info["article_sha256"],
    )

    assert link_result["summary"]["linked"] == 2
    assert "[[ReAct]]" in article.read_text(encoding="utf-8")
    assert "[[Reflection]]" in article.read_text(encoding="utf-8")
    for path in terms_dir.glob("*.md"):
        assert lint_term_file_text(path.read_text(encoding="utf-8"))["passes"] is True
```

Keep the CLI helper assertions focused on emitted artifacts and article/note effects; do not duplicate writer or linker logic in the test.

Add a CLI test proving `lint_glossary.py --input A.md --input B.md` checks exactly two files.

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests/test_workflow_integration.py skills/paper-glossary/tests/test_write_and_lint_glossary.py --basetemp .pytest-tmp-paper-glossary-integration
```

Expected: failures for missing helper integration points, repeatable lint input, and elapsed-time fields.

- [ ] **Step 3: Add shared elapsed-time reporting**

In `glossary_common.py` add:

```python
from time import perf_counter


def elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
```

Each CLI captures `started = perf_counter()` immediately inside `main()` and adds `elapsed_ms` to its emitted top-level JSON. The host separately reports semantic-review and model-generation time because those phases do not run inside Python.

- [ ] **Step 4: Make lint input repeatable**

Change `--input` to `action="append", default=[]`, collect each resolved path once, and retain `--terms-dir` for explicit full-library audits. Reject an empty final file list as before.

- [ ] **Step 5: Complete the integration path and run GREEN**

Expose a writer function beneath the CLI so integration tests call production logic. Run the command from Step 2. Expected: all integration and writer/lint tests pass.

- [ ] **Step 6: Run the full focused suite**

Run:

```powershell
py -3.12 -m pytest -q skills/paper-glossary/tests --basetemp .pytest-tmp-paper-glossary
```

Expected: zero failures.

- [ ] **Step 7: Run syntax and style checks available in the environment**

Run:

```powershell
python -m compileall -q skills\paper-glossary\scripts
python -m ruff check skills\paper-glossary
git diff --check -- skills/paper-glossary
```

Expected: all installed checks exit 0. If `ruff` is unavailable, report the exact `No module named ruff` result and do not install a dependency solely for this task.

- [ ] **Step 8: Run the repository test suite**

Run:

```powershell
py -3.12 -m pytest -q --basetemp .pytest-tmp-full
```

Expected: zero failures; existing third-party deprecation warnings may remain and must be reported separately.

- [ ] **Step 9: Measure local chapter-fixture stages**

Use PowerShell `Measure-Command` for proposal, review recording, triage, inventory, writer, linker on a temporary copy, and changed-file lint. The review command must consume the saved proposal and exact proposal names; the triage command must consume that saved reviewed-shortlist artifact and the resolved exact user selection. Record each stage and total. The under-two-second local-script number for the chapter-four fixture is an observed, environment-dependent target: repeated runs must report a median and range, or exact overruns. It is not a flaky pytest threshold.

- [ ] **Step 10: Final implementation checkpoint without commit**

Review `git diff --stat`, `git diff --check`, and `git status --short`. Confirm that no file outside `skills/paper-glossary/` changed and that the six pre-existing modified files remain incorporated. Do not stage, commit, push, or open a PR.

---

### Task 7: Real chapter-four acceptance preview

**Files:**
- Runtime config: `~/.paper-glossary/config.json`
- Input article: `F:\我的笔记\123\学习\hello_agent\docs\chapter4\第四章 智能体经典范式构建.md`
- Central library: `F:\我的笔记\123\book\术语`
- Existing demo directory retained for now: `F:\我的笔记\123\学习\hello_agent\术语`

**Interfaces:**
- Consumes the completed Tasks 1-6 implementation
- Produces the normal numbered selection interaction and stops before write

- [ ] **Step 1: Configure this device once**

Run:

```powershell
python -X utf8 skills\paper-glossary\scripts\configure_glossary.py --terms-dir 'F:\我的笔记\123\book\术语' --output tmp\paper-glossary-chapter4-demo\device_config_result.json
```

Expected: config points to nearest vault `F:\我的笔记\123` and relative directory `book\术语`.

- [ ] **Step 2: Validate the explicit article and capture its preview hash**

Run:

```powershell
python -X utf8 skills\paper-glossary\scripts\configure_glossary.py --validate-article 'F:\我的笔记\123\学习\hello_agent\docs\chapter4\第四章 智能体经典范式构建.md' --output tmp\paper-glossary-chapter4-demo\article_validation.json
```

Expected: article and term library resolve to the same vault and output contains `article_sha256`.

- [ ] **Step 3: Run the improved proposal**

Run:

```powershell
python -X utf8 skills\paper-glossary\scripts\plan_glossary.py --propose --source-manifest tmp\paper-glossary-chapter4-demo\chapter4_source_manifest.json --output tmp\paper-glossary-chapter4-demo\glossary_candidate_pool.json
```

Expected: a dynamic limit derived from effective prose, `Reflection` is present in the grounded pool, case-only duplicates are absent, and code/example noise such as `KEY`, `MODEL`, `TEMPLATE`, and `HUAWEI` is absent.

- [ ] **Step 4: Perform one semantic review, record it, and display the actual selection UI**

Retain only grounded, reusable concepts up to the returned dynamic limit and save their exact ordered proposal `term` strings to `tmp\paper-glossary-chapter4-demo\reviewed_terms.json`. Record that host-reviewed subset before displaying it:

```powershell
python -X utf8 skills\paper-glossary\scripts\plan_glossary.py --review-proposal tmp\paper-glossary-chapter4-demo\glossary_candidate_pool.json --reviewed-terms tmp\paper-glossary-chapter4-demo\reviewed_terms.json --source-manifest tmp\paper-glossary-chapter4-demo\chapter4_source_manifest.json --output tmp\paper-glossary-chapter4-demo\glossary_reviewed_shortlist.json
```

Expected: `glossary_reviewed_shortlist.json` contains the exact retained full candidate objects, ordered forms, and proposal/review provenance. Display every retained item from this reviewed artifact as a numbered Markdown list together with:

- `F:\我的笔记\123\book\术语` as the write destination;
- the exact chapter Markdown path as the link target;
- the statement that selecting terms will create/enrich notes and add first safe article links;
- the statement that no files have yet been written.

End the response and wait for the user's numbers, names, or `全部写入`. This task intentionally stops at the approved selection gate.

- [ ] **Step 5: Preserve old demo output until the corrected flow is approved**

Do not move or delete `F:\我的笔记\123\学习\hello_agent\术语` during preview. After a later explicit selection completes the new write/link/lint flow, compare those assistant-created demo files with their recorded content and ask before removing any file that may contain later user edits.

---

## Execution Completion Criteria

- Tasks 1-6 pass focused and full tests with no unreported failures.
- The skill validator passes.
- Local script timings are reported and the chapter fixture is benchmarked.
- No DeepPaperNote workflow, plugin manifest, dependency file, or unrelated path changes.
- No commit or push occurs.
- Task 7 presents the corrected real shortlist and stops for explicit user selection.
