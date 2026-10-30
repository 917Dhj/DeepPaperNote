from __future__ import annotations

import hashlib
import json
import math
import re

QUALITY_CHECKS = ("central_claims", "mechanism_result_map", "claim_boundaries")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PLAN_REF_RE = re.compile(
    r"/(central_claims|mechanism_result_map|claim_boundaries)/(0|[1-9][0-9]*)"
    r"(/what_it_does_not_prove)?"
)


def strict_json_loads(text: str) -> dict:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonfinite JSON value: {value}")

    def finite_float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            reject_constant(value)
        return result

    value = json.loads(
        text,
        object_pairs_hook=object_pairs,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )
    if not isinstance(value, dict):
        raise ValueError("Final review artifact must be a JSON object.")
    return value


def canonical_note_text(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise ValueError(
            "Final draft must be canonical UTF-8 without BOM and with LF line endings."
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Final draft must be canonical UTF-8.") from exc


def _keys(value: object, keys: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} requires exactly these fields: {', '.join(sorted(keys))}.")


def _version_language(value: dict, language: str, name: str) -> None:
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError(f"{name} requires schema_version 1.")
    if language not in {"en", "zh-CN"} or value["output_language"] != language:
        raise ValueError(f"{name} output_language does not match {language}.")


def _sha(value: object, name: str, *, empty: bool = False) -> None:
    if empty and value == "":
        return
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} requires a lowercase SHA-256.")


def _valid_plan_ref(reference: str, check: str, plan: dict) -> bool:
    match = PLAN_REF_RE.fullmatch(reference)
    if match is None:
        return False
    group, index, suffix = match.groups()
    if suffix:
        if check != "claim_boundaries" or group != "central_claims":
            return False
    elif group != check:
        return False
    items = plan.get(group)
    if not isinstance(items, list) or int(index) >= len(items):
        return False
    return not suffix or (
        isinstance(items[int(index)], dict) and "what_it_does_not_prove" in items[int(index)]
    )


def validate_quality(
    review: dict,
    *,
    note_sha256: str,
    plan_sha256: str,
    plan: dict,
    language: str,
) -> str:
    _keys(
        review,
        {
            "schema_version",
            "output_language",
            "verdict",
            "reviewed_note_sha256",
            "reviewed_plan_sha256",
            "checks",
            "blocking_findings",
        },
        "Final Quality Review",
    )
    _version_language(review, language, "Final Quality Review")
    for key, expected in (
        ("reviewed_note_sha256", note_sha256),
        ("reviewed_plan_sha256", plan_sha256),
    ):
        _sha(review[key], key)
        if review[key] != expected:
            raise ValueError(f"Final Quality Review {key} is stale; rerun the full review.")
    if (
        not isinstance(plan, dict)
        or plan.get("output_language") != language
        or any(not isinstance(plan.get(check), list) or not plan[check] for check in QUALITY_CHECKS)
    ):
        raise ValueError(
            "Note Plan requires the current language and nonempty quality-check lists."
        )
    _keys(review["checks"], set(QUALITY_CHECKS), "Final Quality Review checks")
    if any(type(value) is not bool for value in review["checks"].values()):
        raise ValueError("Final Quality Review checks must be literal booleans.")
    if review["verdict"] not in ("pass", "fail"):
        raise ValueError("Final Quality Review verdict must be pass or fail.")
    findings = review["blocking_findings"]
    if not isinstance(findings, list):
        raise ValueError("Final Quality Review blocking_findings must be an array.")
    false_checks = {key for key, value in review["checks"].items() if not value}
    covered = set()
    for finding in findings:
        _keys(finding, {"check", "plan_ref", "reason", "required_revision"}, "Blocking finding")
        if any(not isinstance(value, str) or not value.strip() for value in finding.values()):
            raise ValueError("Blocking finding fields must be nonempty strings.")
        check = finding["check"]
        if check not in false_checks or not _valid_plan_ref(finding["plan_ref"], check, plan):
            raise ValueError("Blocking finding must reference an existing item of a false check.")
        covered.add(check)
    if (review["verdict"] == "pass" and (false_checks or findings)) or (
        review["verdict"] == "fail" and (not false_checks or covered != false_checks)
    ):
        raise ValueError("Final Quality Review verdict, checks, and findings are inconsistent.")
    return hashlib.sha256(
        json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def validate_readability(receipt: dict, *, note_sha256: str, language: str) -> None:
    _keys(
        receipt,
        {
            "schema_version",
            "output_language",
            "verdict",
            "reviewed_note_sha256",
        },
        "Final Readability Review",
    )
    _version_language(receipt, language, "Final Readability Review")
    _sha(receipt["reviewed_note_sha256"], "reviewed_note_sha256")
    if receipt["verdict"] != "pass" or receipt["reviewed_note_sha256"] != note_sha256:
        raise ValueError("Final Readability Review must pass for the current final note bytes.")


def validate_state(state: dict, *, language: str) -> None:
    _keys(
        state,
        {
            "schema_version",
            "output_language",
            "revisions_used",
            "last_review",
            "pending_note_sha256",
            "exhausted_note_sha256",
            "seen_review_ids",
        },
        "Final quality state",
    )
    _version_language(state, language, "Final quality state")
    if type(state["revisions_used"]) is not int or not 0 <= state["revisions_used"] <= 2:
        raise ValueError("Final quality state revision count must be between zero and two.")
    last = state["last_review"]
    _keys(last, {"review_id", "note_sha256", "plan_sha256", "verdict"}, "Recorded review")
    for key in ("review_id", "note_sha256", "plan_sha256"):
        _sha(last[key], key)
    if last["verdict"] not in ("pass", "fail"):
        raise ValueError("Recorded review verdict must be pass or fail.")
    seen = state["seen_review_ids"]
    if not isinstance(seen, list) or not seen:
        raise ValueError("Final quality state requires seen review identities.")
    for identity in seen:
        _sha(identity, "seen review identity")
    if len(set(seen)) != len(seen) or last["review_id"] not in seen:
        raise ValueError("Final quality state review identities are inconsistent.")
    for key in ("pending_note_sha256", "exhausted_note_sha256"):
        _sha(state[key], key, empty=True)
    pending, exhausted = state["pending_note_sha256"], state["exhausted_note_sha256"]
    if (pending and pending != last["note_sha256"]) or (last["verdict"] == "fail" and not pending):
        raise ValueError("Final quality state pending revision is inconsistent.")
    if exhausted and (state["revisions_used"] != 2 or exhausted != pending):
        raise ValueError("Final quality state exhaustion is inconsistent.")
    if last["verdict"] == "fail" and state["revisions_used"] == 2 and not exhausted:
        raise ValueError("Final quality state must retain its exhausted revision anchor.")


def advance_state(state: dict | None, review: dict, review_id: str, *, language: str) -> dict:
    if state is None:
        state = {
            "schema_version": 1,
            "output_language": language,
            "revisions_used": 0,
            "pending_note_sha256": "",
            "exhausted_note_sha256": "",
            "seen_review_ids": [],
        }
    else:
        validate_state(state, language=language)
        if review_id in state["seen_review_ids"]:
            if review_id != state["last_review"]["review_id"]:
                raise ValueError("Old review replay cannot restore a previous passing observation.")
            return state
    result = {**state, "seen_review_ids": [*state["seen_review_ids"], review_id]}
    note = review["reviewed_note_sha256"]
    if result["exhausted_note_sha256"] and note != result["exhausted_note_sha256"]:
        raise ValueError("Final quality revision limit exhausted; a third revision is not allowed.")
    if result["pending_note_sha256"] and note != result["pending_note_sha256"]:
        if result["revisions_used"] == 2:
            raise ValueError("Final quality revision limit exhausted.")
        result["revisions_used"] += 1
        result["pending_note_sha256"] = ""
    if review["verdict"] == "fail":
        result["pending_note_sha256"] = note
        if result["revisions_used"] == 2:
            result["exhausted_note_sha256"] = note
    result["last_review"] = {
        "review_id": review_id,
        "note_sha256": note,
        "plan_sha256": review["reviewed_plan_sha256"],
        "verdict": review["verdict"],
    }
    return result


def require_recorded_pass(state: dict, review: dict, review_id: str, *, language: str) -> None:
    validate_state(state, language=language)
    expected = {
        "review_id": review_id,
        "note_sha256": review["reviewed_note_sha256"],
        "plan_sha256": review["reviewed_plan_sha256"],
        "verdict": "pass",
    }
    if review["verdict"] != "pass" or state["last_review"] != expected:
        raise ValueError("Formal Save requires a current recorded passing Final Quality Review.")
