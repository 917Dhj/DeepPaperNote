from __future__ import annotations

from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from glossary_common import canonical_sha256, selection_sha256
from glossary_library import inspect_selected_terms
from plan_glossary import _proposal_artifact, _review_artifact, _triage_candidates


def build_triage_payload(
    terms: list[dict[str, Any]], *, paper_id: str = "paper-fixture"
) -> dict[str, Any]:
    candidates = deepcopy(terms)
    summary = {
        "effective_body_characters": 100,
        "shortlist_limit": max(1, len(candidates)),
        "pool_candidates": len(candidates),
    }
    source_sha256 = canonical_sha256(
        {"paper_id": paper_id, "fixture_source": "paper-glossary tests"}
    )
    proposal = {
        "paper_id": paper_id,
        "source_sha256": source_sha256,
        "candidates": candidates,
        "summary": summary,
    }
    proposal["proposal_sha256"] = canonical_sha256(proposal)
    review = {
        **deepcopy(proposal),
        "reviewed_shortlist": deepcopy(candidates),
    }
    review["review_sha256"] = canonical_sha256(
        {
            "paper_id": paper_id,
            "proposal_provenance": proposal,
            "reviewed_shortlist": review["reviewed_shortlist"],
        }
    )
    return {
        "mode": "triage",
        "paper_id": paper_id,
        "provenance": {
            "proposal": proposal,
            "review": review,
            "selection_sha256": selection_sha256(review["review_sha256"], terms),
        },
        "terms": deepcopy(terms),
    }


def build_inventory_payload(
    terms: list[dict[str, Any]], terms_dir: Path, *, paper_id: str = "paper-fixture"
) -> dict[str, Any]:
    return bind_inventory_results(
        inspect_selected_terms(terms, terms_dir), paper_id=paper_id
    )


def bind_inventory_results(
    results: list[dict[str, Any]], *, paper_id: str = "paper-fixture"
) -> dict[str, Any]:
    exact_results = deepcopy(results)
    terms = [
        {"term": item.get("term"), "surface_forms": item.get("surface_forms")}
        for item in exact_results
    ]
    triage = build_triage_payload(terms, paper_id=paper_id)
    return {
        "status": "ok",
        "script": "inspect_glossary_library.py",
        "paper_id": paper_id,
        "provenance": triage["provenance"],
        "results": exact_results,
    }


def write_current_workflow(
    root: Path,
    reviewed_names: list[str],
    *,
    selected_names: list[str] | None = None,
    paper_id: str = "paper-fixture",
    source_text: str | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    selected_names = reviewed_names if selected_names is None else selected_names
    text = source_text or " ".join(
        f"**{name}** is a paper concept." for name in reviewed_names
    )
    records = [
        {
            "record_type": "section",
            "section_id": "sec:fixture",
            "kind": "body",
            "title": "Fixture",
            "text": text,
        }
    ]
    raw_path = root / "paper_raw_sections.jsonl"
    raw_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    manifest = {"paper_id": paper_id, "raw_sections_path": str(raw_path.resolve())}
    manifest_path = root / "paper_source_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    proposal = _proposal_artifact(manifest, records)
    review = _review_artifact(proposal, reviewed_names)
    reviewed_by_name = {
        candidate["term"]: candidate for candidate in review["reviewed_shortlist"]
    }
    selected_candidates = [reviewed_by_name[name] for name in selected_names]
    triaged = _triage_candidates(selected_candidates, records)
    triage = {
        "status": "ok",
        "script": "plan_glossary.py",
        "mode": "triage",
        "paper_id": paper_id,
        "terms": triaged,
        "provenance": {
            "proposal": proposal["provenance"],
            "review": review["provenance"],
            "selection_sha256": selection_sha256(
                review["provenance"]["review_sha256"], triaged
            ),
        },
    }
    proposal_path = root / "proposal.json"
    review_path = root / "reviewed.json"
    triage_path = root / "triage.json"
    for path, payload in (
        (proposal_path, proposal),
        (review_path, review),
        (triage_path, triage),
    ):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "raw_path": raw_path,
        "proposal": proposal,
        "proposal_path": proposal_path,
        "review": review,
        "review_path": review_path,
        "triage": triage,
        "triage_path": triage_path,
    }


def build_current_inventory(workflow: dict[str, Any], terms_dir: Path) -> dict[str, Any]:
    triage = workflow["triage"]
    return {
        "status": "ok",
        "script": "inspect_glossary_library.py",
        "paper_id": triage["paper_id"],
        "provenance": deepcopy(triage["provenance"]),
        "results": inspect_selected_terms(triage["terms"], terms_dir),
    }
