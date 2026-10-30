from __future__ import annotations

import copy
import importlib

import pytest


def quality_module():
    return importlib.import_module("_final_quality")


def plan_payload() -> dict:
    return {
        "output_language": "en",
        "central_claims": [{
            "claim": "Recorded states improve traceability.",
            "what_it_does_not_prove": "Production reliability is untested.",
        }],
        "mechanism_result_map": ["State logs explain fewer untraceable failures."],
        "claim_boundaries": ["Evidence covers only the reported benchmark."],
    }


def review_payload(note_sha: str = "a" * 64, plan_sha: str = "b" * 64,
                   *, failed: str = "") -> dict:
    checks = dict.fromkeys(("central_claims", "mechanism_result_map", "claim_boundaries"), True)
    findings = []
    if failed:
        checks[failed] = False
        findings = [{
            "check": failed,
            "plan_ref": f"/{failed}/0",
            "reason": "The planned relationship is missing.",
            "required_revision": "Explain the relationship using the planned evidence.",
        }]
    return {
        "schema_version": 1, "output_language": "en",
        "verdict": "fail" if failed else "pass",
        "reviewed_note_sha256": note_sha, "reviewed_plan_sha256": plan_sha,
        "checks": checks, "blocking_findings": findings,
    }


def validate(review: dict) -> str:
    return quality_module().validate_quality(
        review, note_sha256="a" * 64, plan_sha256="b" * 64,
        plan=plan_payload(), language="en",
    )


@pytest.mark.parametrize("failed", ["", "central_claims", "mechanism_result_map", "claim_boundaries"])
def test_quality_schema_accepts_complete_consistent_review(failed: str) -> None:
    assert len(validate(review_payload(failed=failed))) == 64


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2), ("output_language", "English"),
    ("verdict", "approved"), ("reviewed_note_sha256", "A" * 64),
    ("reviewed_plan_sha256", "c" * 64), ("extra", "unrecognized"),
])
def test_quality_schema_rejects_invalid_or_stale_fields(field: str, value: object) -> None:
    review = review_payload()
    review[field] = value
    with pytest.raises(ValueError):
        validate(review)


@pytest.mark.parametrize("change", ["missing", "integer", "extra", "fail_without_finding", "pass_with_failure"])
def test_quality_checks_require_literal_booleans_and_matching_findings(change: str) -> None:
    review = review_payload()
    if change == "missing":
        review["checks"].pop("central_claims")
    elif change == "integer":
        review["checks"]["central_claims"] = 1
    elif change == "extra":
        review["checks"]["style"] = True
    else:
        review["checks"]["central_claims"] = False
        if change == "fail_without_finding":
            review["verdict"] = "fail"
    with pytest.raises(ValueError):
        validate(review)


@pytest.mark.parametrize("reference", [
    "/central_claims/1", "/central_claims/-1", "/central_claims/00",
    "/mechanism_result_map/0", "/central_claims/0/claim", "central_claims[0]",
])
def test_quality_finding_references_must_name_existing_items_of_the_failed_check(reference: str) -> None:
    review = review_payload(failed="central_claims")
    review["blocking_findings"][0]["plan_ref"] = reference
    with pytest.raises(ValueError):
        validate(review)


def test_claim_boundary_finding_can_reference_the_claims_unproven_scope() -> None:
    review = review_payload(failed="claim_boundaries")
    review["blocking_findings"][0]["plan_ref"] = "/central_claims/0/what_it_does_not_prove"
    validate(review)


@pytest.mark.parametrize("field,value", [("reason", ""), ("required_revision", " "), ("extra", True)])
def test_quality_findings_have_closed_nonempty_fields(field: str, value: object) -> None:
    review = review_payload(failed="central_claims")
    review["blocking_findings"][0][field] = value
    with pytest.raises(ValueError):
        validate(review)


@pytest.mark.parametrize("text", ['{"verdict":"fail","verdict":"pass"}', '{"value":NaN}'])
def test_review_json_rejects_duplicate_keys_and_nonfinite_values(text: str) -> None:
    with pytest.raises(ValueError):
        quality_module().strict_json_loads(text)


def test_readability_requires_its_own_current_closed_receipt() -> None:
    receipt = {
        "schema_version": 1, "output_language": "en", "verdict": "pass",
        "reviewed_note_sha256": "a" * 64,
    }
    quality_module().validate_readability(receipt, note_sha256="a" * 64, language="en")
    for field, value in [("verdict", "fail"), ("schema_version", True),
                         ("reviewed_note_sha256", "b" * 64), ("quality", True)]:
        invalid = {**receipt, field: value}
        with pytest.raises(ValueError):
            quality_module().validate_readability(invalid, note_sha256="a" * 64, language="en")


def observe(state: dict | None, note: str, *, failed: str = "", plan: str = "b") -> dict:
    review = review_payload(note * 64, plan * 64, failed=failed)
    module = quality_module()
    identity = module.validate_quality(
        review, note_sha256=note * 64, plan_sha256=plan * 64,
        plan=plan_payload(), language="en",
    )
    return module.advance_state(state, review, identity, language="en")


def test_two_failure_driven_revisions_survive_replans_and_cannot_accept_a_third_pass() -> None:
    state = observe(None, "a", failed="central_claims")
    assert state["revisions_used"] == 0
    state = observe(state, "c", failed="central_claims", plan="d")
    assert state["revisions_used"] == 1
    state = observe(state, "e", failed="claim_boundaries", plan="f")
    assert state["revisions_used"] == 2
    assert state["exhausted_note_sha256"] == "e" * 64
    original = copy.deepcopy(state)
    with pytest.raises(ValueError, match="revision"):
        observe(state, "1", plan="2")
    assert state == original


def test_same_byte_rereview_cannot_erase_pending_or_exhausted_failure() -> None:
    state = observe(None, "a", failed="central_claims")
    state = observe(state, "a")
    assert state["pending_note_sha256"] == "a" * 64
    state = observe(state, "c", failed="central_claims")
    state = observe(state, "d", failed="central_claims")
    state = observe(state, "d")
    assert state["revisions_used"] == 2
    assert state["exhausted_note_sha256"] == "d" * 64
    with pytest.raises(ValueError):
        observe(state, "e")


def test_review_replay_is_idempotent_and_cannot_restore_an_old_passing_review() -> None:
    first = observe(None, "a")
    assert observe(first, "a") == first
    second = observe(first, "c", failed="central_claims")
    with pytest.raises(ValueError, match="replay"):
        observe(second, "a")


def test_formatting_does_not_create_a_new_review_identity() -> None:
    original = review_payload()
    reordered = dict(reversed(list(original.items())))
    assert validate(original) == validate(reordered)


def test_corrupt_journal_does_not_reset_revision_usage() -> None:
    state = observe(None, "a", failed="central_claims")
    for field, value in [("revisions_used", True), ("revisions_used", 3),
                         ("output_language", "zh-CN"), ("seen_review_ids", [])]:
        with pytest.raises(ValueError):
            observe({**state, field: value}, "c")
