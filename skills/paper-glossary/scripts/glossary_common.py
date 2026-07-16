from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any


def elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def proposal_sha256(
    paper_id: str,
    source_sha256: str,
    candidates: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str:
    return canonical_sha256(
        {
            "paper_id": paper_id,
            "source_sha256": source_sha256,
            "candidates": candidates,
            "summary": summary,
        }
    )


def review_sha256(
    proposal_provenance: dict[str, Any], reviewed_shortlist: list[dict[str, Any]]
) -> str:
    return canonical_sha256(
        {
            "paper_id": proposal_provenance.get("paper_id"),
            "proposal_provenance": proposal_provenance,
            "reviewed_shortlist": reviewed_shortlist,
        }
    )


def selection_sha256(review_sha256: str, items: list[dict[str, Any]]) -> str:
    selected_terms = [
        {"term": item.get("term"), "surface_forms": item.get("surface_forms")}
        for item in items
    ]
    return canonical_sha256(
        {"review_sha256": review_sha256, "selected_terms": selected_terms}
    )


def writer_mappings_sha256(
    provenance: dict[str, Any],
    results: list[dict[str, Any]],
    context: dict[str, Any],
    triage_sha256: str,
) -> str:
    mappings: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            raise SystemExit("Writer results must contain mapping objects.")
        try:
            mappings.append(
                {
                    field: item[field]
                    for field in ("name", "forms", "file", "link_stem")
                }
            )
        except KeyError as exc:
            raise SystemExit(
                f"Writer mapping is missing required field: {exc.args[0]}"
            ) from None
    if not _valid_digest(triage_sha256):
        raise SystemExit("Writer mappings require a valid triage artifact digest.")
    return canonical_sha256(
        {
            "provenance": provenance,
            "mappings": mappings,
            "context": context,
            "triage_sha256": triage_sha256,
        }
    )


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _validated_term_sequence(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SystemExit(f"Invalid {label} provenance structure.")
    terms: set[str] = set()
    for item in value:
        term = item.get("term")
        forms = item.get("surface_forms")
        if (
            not isinstance(term, str)
            or not term
            or normalize_whitespace(term) != term
            or term in terms
            or not isinstance(forms, list)
            or not forms
        ):
            raise SystemExit(f"Invalid {label} term or surface_forms provenance.")
        exact_forms: set[str] = set()
        for form in forms:
            if (
                not isinstance(form, str)
                or not form
                or normalize_whitespace(form) != form
                or form in exact_forms
            ):
                raise SystemExit(f"Invalid or duplicate {label} surface_forms provenance.")
            exact_forms.add(form)
        if term not in exact_forms:
            raise SystemExit(f"Canonical {label} term must be present in surface_forms.")
        terms.add(term)
    return value


def validate_provenance_chain(
    payload: dict[str, Any], selected_items: Any
) -> dict[str, Any]:
    paper_id = payload.get("paper_id")
    provenance = payload.get("provenance")
    proposal = provenance.get("proposal") if isinstance(provenance, dict) else None
    review = provenance.get("review") if isinstance(provenance, dict) else None
    selection_digest = (
        provenance.get("selection_sha256") if isinstance(provenance, dict) else None
    )
    if (
        not isinstance(paper_id, str)
        or not paper_id
        or not isinstance(proposal, dict)
        or not isinstance(review, dict)
        or not _valid_digest(selection_digest)
    ):
        raise SystemExit("Artifact must contain valid paper and selection provenance.")

    source_digest = proposal.get("source_sha256")
    proposal_digest = proposal.get("proposal_sha256")
    candidates = _validated_term_sequence(
        proposal.get("candidates"), "proposal candidates"
    )
    summary = proposal.get("summary")
    if (
        proposal.get("paper_id") != paper_id
        or not _valid_digest(source_digest)
        or not _valid_digest(proposal_digest)
        or not isinstance(summary, dict)
    ):
        raise SystemExit("Invalid proposal provenance or top-level paper binding.")
    expected_proposal_digest = proposal_sha256(
        paper_id, source_digest, candidates, summary
    )
    if proposal_digest != expected_proposal_digest:
        raise SystemExit("Proposal digest does not match embedded provenance material.")

    proposal_fields = (
        "paper_id",
        "source_sha256",
        "candidates",
        "summary",
        "proposal_sha256",
    )
    if any(review.get(field) != proposal[field] for field in proposal_fields):
        raise SystemExit("Proposal and review provenance fields do not match.")
    reviewed_shortlist = _validated_term_sequence(
        review.get("reviewed_shortlist"), "reviewed shortlist"
    )
    reviewed_terms: set[str] = set()
    candidates_by_term = {candidate["term"]: candidate for candidate in candidates}
    for candidate in reviewed_shortlist:
        term = candidate["term"]
        if candidate != candidates_by_term.get(term) or term in reviewed_terms:
            raise SystemExit("Reviewed shortlist is not an exact proposal subset.")
        reviewed_terms.add(term)
    limit = summary.get("shortlist_limit")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise SystemExit("Invalid proposal shortlist limit provenance.")
    if len(reviewed_shortlist) > limit:
        raise SystemExit("Reviewed shortlist exceeds proposal shortlist limit.")

    review_digest = review.get("review_sha256")
    if not _valid_digest(review_digest):
        raise SystemExit("Invalid review digest provenance.")
    proposal_material = {field: proposal[field] for field in proposal_fields}
    if review_digest != review_sha256(proposal_material, reviewed_shortlist):
        raise SystemExit("Review digest does not match embedded provenance material.")

    selected = _validated_term_sequence(selected_items, "selected")
    reviewed_by_term = {candidate["term"]: candidate for candidate in reviewed_shortlist}
    for item in selected:
        reviewed = reviewed_by_term.get(item["term"])
        if reviewed is None or item["surface_forms"] != reviewed["surface_forms"]:
            raise SystemExit(
                "Selected term and surface_forms must exactly match the reviewed shortlist."
            )
    if selection_digest != selection_sha256(review_digest, selected):
        raise SystemExit("Selection digest does not match selected term provenance.")
    return provenance


def validate_current_provenance_chain(
    payload: dict[str, Any],
    selected_items: Any,
    source_manifest: str,
    raw_sections: str,
    reviewed_shortlist: str,
) -> dict[str, Any]:
    # Imported lazily because plan_glossary itself uses the digest helpers above.
    from plan_glossary import _validated_review, load_manifest_and_sections

    manifest, records = load_manifest_and_sections(source_manifest, raw_sections)
    review_payload = load_json_file(
        Path(reviewed_shortlist).expanduser().resolve()
    )
    current_review, current_proposal = _validated_review(
        review_payload, manifest, records
    )
    provenance = validate_provenance_chain(payload, selected_items)
    if (
        payload.get("paper_id") != current_proposal["paper_id"]
        or provenance.get("proposal") != current_proposal["provenance"]
        or provenance.get("review") != current_review["provenance"]
    ):
        raise SystemExit(
            "Artifact provenance does not match the current source and reviewed shortlist."
        )
    return {
        "paper_id": current_proposal["paper_id"],
        "manifest": manifest,
        "provenance": provenance,
    }


def _selected_term_forms(
    value: Any,
    label: str,
    term_field: str = "term",
    forms_field: str = "surface_forms",
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SystemExit(f"Invalid {label} authorization structure.")
    selected = [
        {"term": item.get(term_field), "surface_forms": item.get(forms_field)}
        for item in value
    ]
    return _validated_term_sequence(selected, label)


def triage_artifact_sha256(triage: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "paper_id": triage["paper_id"],
            "provenance": triage["provenance"],
            "terms": triage["terms"],
        }
    )


def validate_authorized_selection(
    payload: dict[str, Any],
    selected_items: Any,
    triage_artifact: str,
    source_manifest: str,
    raw_sections: str,
    reviewed_shortlist: str,
    *,
    term_field: str = "term",
    forms_field: str = "surface_forms",
) -> dict[str, Any]:
    triage = load_json_file(Path(triage_artifact).expanduser().resolve())
    if (
        triage.get("status") != "ok"
        or triage.get("script") != "plan_glossary.py"
        or triage.get("mode") != "triage"
    ):
        raise SystemExit("Authorized selection must be a saved triage artifact.")
    authorized = _selected_term_forms(triage.get("terms"), "authorized triage")
    current = validate_current_provenance_chain(
        triage,
        authorized,
        source_manifest,
        raw_sections,
        reviewed_shortlist,
    )
    selected = _selected_term_forms(
        selected_items,
        "downstream selected",
        term_field,
        forms_field,
    )
    provenance = validate_provenance_chain(payload, selected)
    if (
        selected != authorized
        or payload.get("paper_id") != current["paper_id"]
        or provenance != current["provenance"]
    ):
        raise SystemExit(
            "Downstream selection does not exactly match the authorized triage artifact."
        )
    return {
        **current,
        "authorized_selection": authorized,
        "triage_sha256": triage_artifact_sha256(triage),
    }


def load_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}.")
    return data


def maybe_load_json_record(value: str) -> dict[str, Any] | None:
    raw = value.strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise SystemExit("Expected JSON object.")
        return data
    path = Path(raw).expanduser()
    if path.is_file():
        return load_json_file(path)
    return None


def emit(payload: dict[str, Any], output: str = "") -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        Path(output).expanduser().write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
