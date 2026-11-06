"""Recall vault paper notes a new note may link to, and check generated wikilinks.

Scripts recall candidates; the model decides which ones are real connections.
Two kinds of candidate reach the synthesis bundle:

- cited: a bibliography entry of this paper matches a vault paper by DOI, arXiv
  ID, or title/alias. An entry matching two different papers is dropped.
- related: the paper's full text mentions at least two distinct `methods`,
  `datasets`, `tasks`, or alias values of a vault paper, or one dataset/task value.

The zh-CN and en notes of one paper share a directory and count as one paper;
the link target prefers the note in the run's output language.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _frontmatter import FrontmatterError, parse_frontmatter
from _note_paths import configured_obsidian_vault
from citation_links import (
    _candidate_arxiv_ids,
    _candidate_doi,
    _contains_key,
    _frontmatter_fields,
    _h1_title,
    _match_key,
    _normalize_arxiv_id,
    _normalize_doi,
    _safe_text_key,
)
from common import normalize_whitespace

MAX_CITED = 30
# Titles this long are matched with spaces removed, so PDF line-break hyphenation
# ("Instruc- tions") still matches; shorter aliases keep word boundaries.
COMPACT_MATCH_MIN_CHARS = 20
MAX_RELATED = 15
PROPERTY_FIELDS = ("methods", "datasets", "tasks")
LANG_SUFFIX_RE = re.compile(r"\.(zh-CN|en)$")
WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "cited": [], "related": []}


def _link_text(value: str) -> str:
    """`[[target|label]]` -> label, `[[target]]` -> target, plain text unchanged."""
    match = re.fullmatch(r"\[\[([^\[\]]+)\]\]", value.strip())
    if match is None:
        return normalize_whitespace(value)
    target, _, label = match.group(1).partition("|")
    return normalize_whitespace(label or target.split("#", 1)[0])


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _read_note(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]
    except OSError:
        return None
    try:
        fields = parse_frontmatter(text)
    except FrontmatterError:
        # A note with richer YAML than our subset still yields identifiers.
        fields = _frontmatter_fields(text)
    if fields is None:
        return None
    doi = normalize_whitespace(str(fields.get("doi", "") or ""))
    arxiv = normalize_whitespace(str(fields.get("arxiv_id", "") or fields.get("arxiv", "") or ""))
    return {
        "path": path,
        "language": (LANG_SUFFIX_RE.search(path.stem) or [None, ""])[1],
        "title": normalize_whitespace(str(fields.get("title", "") or "")) or _h1_title(text),
        "dois": {_normalize_doi(doi)} - {""} if doi else set(),
        "arxiv_ids": {_normalize_arxiv_id(value) for value in (arxiv, doi)} - {""},
        "aliases": [_link_text(item) for item in _as_list(fields.get("aliases"))],
        **{
            field: [_link_text(item) for item in _as_list(fields.get(field))]
            for field in PROPERTY_FIELDS
        },
    }


def _merge(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        if value and value.casefold() not in seen:
            seen[value.casefold()] = value
    return list(seen.values())


def _paper_groups(
    base_dir: Path, vault: Path, language: str, own_directory: Path | None
) -> list[dict]:
    groups: dict[tuple[Path, str], list[dict]] = {}
    for path in sorted(base_dir.glob("**/*.md")):
        if own_directory is not None and path.parent.resolve() == own_directory:
            continue
        note = _read_note(path)
        if note is None:
            continue
        key = (path.parent, LANG_SUFFIX_RE.sub("", path.stem))
        groups.setdefault(key, []).append(note)

    papers = []
    for (_, base), notes in groups.items():
        chosen = next((note for note in notes if note["language"] == language), notes[0])
        aliases = _merge([alias for note in notes for alias in note["aliases"]])
        papers.append(
            {
                "target": chosen["path"].stem,
                "title": chosen["title"],
                "vault_relative_path": chosen["path"].relative_to(vault).as_posix(),
                "dois": set().union(*(note["dois"] for note in notes)),
                "arxiv_ids": set().union(*(note["arxiv_ids"] for note in notes)),
                "aliases": aliases,
                "text_keys": _merge(
                    [
                        key
                        for value in [base, *(note["title"] for note in notes), *aliases]
                        if (key := _safe_text_key(value))
                    ]
                ),
                **{
                    field: _merge([value for note in notes for value in note[field]])
                    for field in PROPERTY_FIELDS
                },
            }
        )
    return papers


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", _match_key(value))


def _cites_text_key(text: str, compact_text: str, key: str) -> bool:
    if _contains_key(text, key):
        return True
    compact_key = _compact(key)
    return len(compact_key) >= COMPACT_MATCH_MIN_CHARS and compact_key in compact_text


def _cited(papers: list[dict], references: list[dict]) -> list[dict]:
    cited: dict[str, dict] = {}
    for reference in references:
        if not isinstance(reference, dict):
            continue
        raw = str(reference.get("raw_text", "") or reference.get("display_text", ""))
        display = normalize_whitespace(
            str(reference.get("display_text", ""))
        ) or normalize_whitespace(raw)
        text = normalize_whitespace(f"{raw} {display}")
        doi = _candidate_doi(reference, text)
        arxiv_ids = _candidate_arxiv_ids(reference, text)
        tiers = []
        if doi:
            tiers.append(("doi", [paper for paper in papers if doi in paper["dois"]]))
        if arxiv_ids:
            tiers.append(
                ("arxiv_id", [paper for paper in papers if arxiv_ids & paper["arxiv_ids"]])
            )
        compact_text = _compact(text)
        tiers.append(
            (
                "title_or_alias",
                [
                    p
                    for p in papers
                    if any(_cites_text_key(text, compact_text, key) for key in p["text_keys"])
                ],
            )
        )
        for reason, matches in tiers:
            if not matches:
                continue
            if len(matches) == 1 and matches[0]["target"] not in cited:
                paper = matches[0]
                cited[paper["target"]] = {
                    "target": paper["target"],
                    "title": paper["title"],
                    "vault_relative_path": paper["vault_relative_path"],
                    "match_reason": reason,
                    "reference": display,
                    **{field: paper[field] for field in PROPERTY_FIELDS},
                }
            break  # an ambiguous tier drops the reference instead of guessing
        if len(cited) >= MAX_CITED:
            break
    return list(cited.values())


def _related(papers: list[dict], full_text: str, exclude: set[str]) -> list[dict]:
    scored = []
    for paper in papers:
        if paper["target"] in exclude:
            continue
        matched = {
            field: [
                value
                for value in paper[field]
                if len(value) >= 2 and _contains_key(full_text, value)
            ]
            for field in (*PROPERTY_FIELDS, "aliases")
        }
        distinct = {value.casefold() for values in matched.values() for value in values}
        strong = len(matched["datasets"]) + len(matched["tasks"])
        if len(distinct) < 2 and strong < 1:
            continue
        scored.append(
            (
                (-len(distinct), -strong, paper["target"]),
                {
                    "target": paper["target"],
                    "title": paper["title"],
                    "vault_relative_path": paper["vault_relative_path"],
                    "matched_values": matched,
                },
            )
        )
    return [item for _, item in sorted(scored, key=lambda pair: pair[0])[:MAX_RELATED]]


def connection_candidates(
    config: dict[str, Any],
    references: list[dict],
    full_text: str,
    language: str,
    *,
    own_directory: str | Path | None = None,
) -> dict[str, Any]:
    save_mode = str(config.get("save_mode", "")).strip()
    if save_mode == "workspace" or (
        not save_mode and not str(config.get("obsidian_vault", "")).strip()
    ):
        return _empty("workspace")
    try:
        vault = configured_obsidian_vault(config)
    except Exception:
        return _empty("vault_unavailable")
    if vault is None:
        return _empty("vault_unavailable")
    papers_dir = str(config.get("papers_dir", "") or "Research/Papers").strip() or "Research/Papers"
    base_dir = (vault / papers_dir).resolve()
    if not base_dir.is_relative_to(vault):
        return _empty("vault_unavailable")
    if not base_dir.is_dir():
        return _empty("ok")
    own = Path(own_directory).expanduser().resolve() if own_directory else None
    papers = _paper_groups(base_dir, vault, language, own)
    cited = _cited(papers, references or [])
    related = _related(papers, full_text or "", {item["target"] for item in cited})
    return {"status": "ok", "cited": cited, "related": related}


# --- Formal Save -------------------------------------------------------------


def generated_wikilinks(text: str) -> list[str]:
    """Link targets of every non-embed `[[link]]`, without `|label` or `#heading`."""
    targets = []
    for bang, inner in WIKILINK_RE.findall(text):
        if bang:
            continue
        target = inner.split("|", 1)[0].split("#", 1)[0].strip()
        targets.append(target)
    return targets


def _vault_link_keys(vault: Path) -> set[str]:
    keys: set[str] = set()
    for path in vault.rglob("*"):
        relative = path.relative_to(vault)
        if any(part.startswith(".") for part in relative.parts) or not path.is_file():
            continue
        posix = relative.as_posix()
        keys.add(path.name.casefold())
        keys.add(posix.casefold())
        if path.suffix == ".md":
            keys.add(path.stem.casefold())
            keys.add(posix[: -len(".md")].casefold())
    return keys


def unresolved_wikilinks(text: str, vault: Path) -> list[str]:
    """Targets Obsidian would not resolve to an existing vault file."""
    targets = generated_wikilinks(text)
    if not targets:
        return []
    keys = _vault_link_keys(vault)
    missing = []
    for target in targets:
        folded = target.casefold().lstrip("/")
        resolved = folded in keys or (
            "/" in folded and any(key.endswith("/" + folded) for key in keys)
        )
        if folded and resolved:
            continue
        if target not in missing:
            missing.append(target)
    return missing
