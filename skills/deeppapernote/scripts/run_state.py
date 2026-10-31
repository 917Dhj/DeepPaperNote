#!/usr/bin/env python3
"""Inspect selected DeepPaperNote artifacts without running or changing the workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from _final_quality import (
    canonical_note_text,
    require_recorded_pass,
    strict_json_loads,
    validate_quality,
    validate_readability,
    validate_state,
)
from common import canonical_identity_acceptance_error, safe_relative_path_parts
from lint_grounding import validate_bundle_contract, validate_figure_decisions, validate_note_plan
from run_pipeline import pipeline_artifact_paths
from source_corpus import SourceCorpusLoadError, load_source_corpus, validate_source_corpus


@dataclass(frozen=True)
class Stage:
    id: str
    dependencies: tuple[str, ...]
    evaluator: str
    producer: str = ""
    language: bool = False
    structure: tuple[tuple[str, type], ...] = ()
    action: str = ""


@dataclass
class StageResult:
    id: str
    status: str = "passed"
    issues: list[dict[str, str]] = field(default_factory=list)
    unmet_dependencies: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


STAGES = (
    Stage("resolve", (), "historical", "resolve_paper.py", structure=(("paper_id", str),)),
    Stage(
        "metadata", ("resolve",), "historical", "collect_metadata.py", structure=(("title", str),)
    ),
    Stage("identity", ("metadata",), "identity", "build_identity_contract.py"),
    Stage("fetch", ("identity",), "pdf", "fetch_pdf.py"),
    Stage("source_manifest", ("fetch",), "source", "extract_source_text.py"),
    Stage(
        "admission", ("identity", "source_manifest"), "admission", "write_obsidian_note.py", True
    ),
    Stage(
        "evidence",
        ("source_manifest", "admission"),
        "historical",
        "extract_evidence.py",
        structure=(("evidence_pack", dict),),
    ),
    Stage(
        "assets",
        ("fetch", "admission"),
        "historical",
        "extract_pdf_assets.py",
        structure=(("pdf_path", str),),
    ),
    Stage(
        "figures",
        ("assets", "evidence", "source_manifest"),
        "historical",
        "plan_figures.py",
        True,
        (("figure_plan", dict),),
    ),
    Stage(
        "figure_table_decisions",
        ("figures", "source_manifest"),
        "decisions",
        "plan_figure_table_decisions.py",
        True,
        (("decisions", list),),
    ),
    Stage(
        "bundle",
        ("metadata", "evidence", "figure_table_decisions"),
        "historical",
        "build_synthesis_bundle.py",
        True,
        (("writing_contract", dict),),
    ),
    Stage(
        "note_plan",
        ("source_manifest", "bundle", "figure_table_decisions", "admission"),
        "plan",
        language=True,
        action="model",
    ),
    Stage(
        "grounding_lint",
        ("note_plan", "source_manifest", "figure_table_decisions"),
        "grounding",
        "lint_grounding.py",
        True,
    ),
    Stage("draft", ("grounding_lint",), "draft", action="model"),
    Stage("note_lint", ("draft", "note_plan"), "lint", "lint_note.py", True),
    Stage("quality_review", ("note_lint", "note_plan"), "quality", action="model"),
    Stage("readability_review", ("quality_review", "draft"), "readability", action="model"),
    Stage(
        "save_receipt",
        (
            "source_manifest",
            "figure_table_decisions",
            "note_plan",
            "grounding_lint",
            "note_lint",
            "quality_review",
            "readability_review",
            "admission",
        ),
        "save",
        "write_obsidian_note.py",
        True,
    ),
)
LATE_ARTIFACTS = tuple(
    stage.id for stage in STAGES if stage.id not in pipeline_artifact_paths(Path(), "run")
)
CONTEXT_KEYS = {
    "paper_reference",
    "output_language",
    "save_mode",
    "vault",
    "papers_dir",
    "target_directory",
}
LINT_GATES = (
    "passes_basic_structure",
    "passes_style_gate",
    "passes_math_gate",
    "passes_figure_gate",
    "passes_reference_hygiene_gate",
    "passes_plan_gate",
    "passes_substantive_content",
)
DIRECTORIES = {"pdfs", "assets_directory"}
SHA_RE = re.compile(r"[0-9a-f]{64}")


def validate_bindings(bindings: dict) -> dict:
    if not isinstance(bindings, dict) or set(bindings) - {"schema_version", "artifacts", "context"}:
        raise ValueError("Bindings require only schema_version, artifacts, and context.")
    if type(bindings.get("schema_version")) is not int or bindings["schema_version"] != 1:
        raise ValueError("Bindings require schema_version 1.")
    artifacts, context = bindings.get("artifacts", {}), bindings.get("context", {})
    known = set(pipeline_artifact_paths(Path(), "run")) | set(LATE_ARTIFACTS)
    for value, keys, name in ((artifacts, known, "artifacts"), (context, CONTEXT_KEYS, "context")):
        if not isinstance(value, dict) or set(value) - keys:
            raise ValueError(f"Unknown or invalid bindings {name}.")
        if any(
            not isinstance(item, str) or not item.strip() or "\x00" in item
            for item in value.values()
        ):
            raise ValueError(f"Bindings {name} values must be nonempty strings.")
    if "output_language" in context and context["output_language"] not in {"en", "zh-CN"}:
        raise ValueError("Bindings output_language must be en or zh-CN.")
    if "save_mode" in context and context["save_mode"] not in {"workspace", "obsidian"}:
        raise ValueError("Bindings save_mode must be workspace or obsidian.")
    return {"artifacts": artifacts, "context": context}


def resolved_path(value: str | Path, base: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


class Inspection:
    def __init__(self, workdir: Path, prefix: str, bindings: dict):
        self.workdir = workdir
        self.prefix = prefix
        self.context = dict(bindings["context"])
        for key in ("vault", "target_directory"):
            if key in self.context:
                self.context[key] = str(resolved_path(self.context[key], workdir))
        self.paths: dict[str, Path | None] = {
            **pipeline_artifact_paths(workdir, prefix),
            **dict.fromkeys(LATE_ARTIFACTS),
        }
        self.selections = {
            key: "default" if path else "unselected" for key, path in self.paths.items()
        }
        for key, value in bindings["artifacts"].items():
            self.paths[key] = resolved_path(value, workdir)
            self.selections[key] = "binding"
        self.raw: dict[str, bytes] = {}
        self.data: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.hashes: dict[str, str] = {}
        for key, path in self.paths.items():
            if path is None or key in DIRECTORIES:
                continue
            try:
                self.raw[key] = path.read_bytes()
                self.hashes[key] = hashlib.sha256(self.raw[key]).hexdigest()
                if key not in {"draft", "raw_sections", "full_text"}:
                    self.data[key] = strict_json_loads(self.raw[key].decode("utf-8-sig"))
            except FileNotFoundError:
                pass
            except (OSError, ValueError, UnicodeError) as exc:
                self.errors[key] = str(exc)
        if "output_language" not in self.context:
            languages = {
                record["output_language"]
                for record in self.data.values()
                if isinstance(record.get("output_language"), str)
                and record["output_language"] in {"en", "zh-CN"}
            }
            if len(languages) == 1:
                self.context["output_language"] = languages.pop()
        self.results: dict[str, StageResult] = {}
        self.provenance_gaps: list[dict[str, str]] = []

    def problem(
        self,
        result: StageResult,
        status: str,
        code: str,
        message: str,
        path: str | Path | None = None,
    ) -> None:
        priority = {
            "passed": 0,
            "present_unverified": 1,
            "missing": 2,
            "failed": 3,
            "stale": 4,
            "invalid": 5,
        }
        if priority[status] > priority[result.status]:
            result.status = status
        result.issues.append(
            {"code": code, "path": str(path or self.paths.get(result.id) or ""), "message": message}
        )

    def gap(self, result: StageResult, message: str) -> None:
        self.provenance_gaps.append({"stage": result.id, "message": message})

    def matches(
        self,
        result: StageResult,
        record: dict,
        field_name: str,
        artifact: str,
        *,
        expected: str | None = None,
    ) -> None:
        digest = expected if expected is not None else self.hashes.get(artifact)
        recorded = record.get(field_name)
        if not isinstance(recorded, str) or SHA_RE.fullmatch(recorded) is None:
            self.problem(
                result,
                "invalid",
                "fingerprint_missing_or_invalid",
                f"{field_name} requires a lowercase SHA-256.",
            )
        elif digest is None:
            self.problem(
                result,
                "present_unverified",
                "input_unavailable",
                f"Cannot compare {field_name}; {artifact} is unavailable.",
            )
        elif recorded != digest:
            self.problem(
                result,
                "stale",
                "input_sha256_mismatch",
                f"{field_name} does not match current {artifact} bytes.",
            )

    def language(self, result: StageResult, record: dict) -> bool:
        declared = record.get("output_language")
        if not isinstance(declared, str) or declared not in {"en", "zh-CN"}:
            self.problem(
                result,
                "invalid",
                "output_language_invalid",
                "Artifact output_language must be en or zh-CN.",
            )
            return False
        language = self.context.get("output_language")
        if language is None:
            self.problem(
                result,
                "present_unverified",
                "language_context_missing",
                "Select output_language; the selected evidence does not establish one.",
            )
            return False
        if record.get("output_language") != language:
            self.problem(
                result,
                "invalid",
                "output_language_mismatch",
                f"Artifact output_language must equal {language}.",
            )
            return False
        return True

    def evaluate(self, stage: Stage) -> StageResult:
        result = StageResult(stage.id)
        if stage.id == "admission" and self.context.get("save_mode") == "workspace":
            result.details["required"] = False
            if self.paths[stage.id] is None:
                return result
        path = self.paths[stage.id]
        if path is None:
            self.problem(result, "missing", "artifact_unselected", "No explicit artifact selected.")
        elif stage.id in self.errors:
            self.problem(result, "invalid", "artifact_unreadable", self.errors[stage.id])
        elif stage.id not in self.raw:
            self.problem(result, "missing", "artifact_missing", "Selected artifact does not exist.")
        else:
            record = self.data.get(stage.id)
            if stage.evaluator != "draft" and record is None:
                try:
                    record = strict_json_loads(self.raw[stage.id].decode("utf-8-sig"))
                    self.data[stage.id] = record
                except (ValueError, UnicodeError) as exc:
                    self.problem(result, "invalid", "artifact_json_invalid", str(exc))
            if record is not None:
                identity = self.data.get("identity", {})
                selected_id = identity.get("paper_id")
                if (
                    stage.id not in {"resolve", "metadata"}
                    and not canonical_identity_acceptance_error(identity)
                    and identity.get("script") == "build_identity_contract.py"
                    and identity.get("status") == "ok"
                    and isinstance(selected_id, str)
                    and selected_id
                    and record.get("paper_id")
                    and record["paper_id"] != selected_id
                ):
                    self.problem(
                        result,
                        "invalid",
                        "paper_id_mismatch",
                        "Artifact paper_id differs from the selected accepted identity.",
                    )
                if stage.producer and record.get("script") != stage.producer:
                    self.problem(
                        result,
                        "invalid",
                        "producer_mismatch",
                        f"Expected producer {stage.producer}.",
                    )
                if stage.producer and record.get("status") != "ok":
                    self.problem(
                        result,
                        "failed",
                        "producer_not_ok",
                        f"Producer reported {record.get('status')!r}.",
                    )
                if stage.language or "output_language" in record:
                    self.language(result, record)
                for key, kind in stage.structure:
                    if not isinstance(record.get(key), kind) or (
                        kind is str and not record[key].strip()
                    ):
                        self.problem(
                            result,
                            "invalid",
                            "artifact_structure_invalid",
                            f"{key} requires {kind.__name__}.",
                        )
            if result.status != "invalid":
                try:
                    getattr(self, f"check_{stage.evaluator}")(result, record or {})
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    AttributeError,
                    SourceCorpusLoadError,
                    RuntimeError,
                ) as exc:
                    self.problem(result, "invalid", "artifact_validation_failed", str(exc))
        accepted_statuses = (
            {"passed"} if stage.id == "save_receipt" else {"passed", "present_unverified"}
        )
        result.unmet_dependencies = [
            key
            for key in stage.dependencies
            if self.results[key].details.get("required") is not False
            and (
                self.results[key].status not in accepted_statuses
                or self.results[key].unmet_dependencies
            )
        ]
        return result

    def check_historical(self, result: StageResult, record: dict) -> None:
        self.problem(
            result,
            "present_unverified",
            "producer_provenance_unknown",
            "Producer did not record enough input fingerprints to verify its history.",
        )
        self.gap(result, "Input history cannot be reconstructed from this producer artifact.")

    def check_identity(self, result: StageResult, record: dict) -> None:
        error = canonical_identity_acceptance_error(record)
        if error:
            self.problem(result, "failed", "identity_not_accepted", error)
        self.gap(result, "Accepted identity has no parent-byte fingerprints.")

    def check_pdf(self, result: StageResult, record: dict) -> None:
        value = record.get("pdf_path")
        if not isinstance(value, str) or not value.strip():
            self.problem(result, "invalid", "pdf_path_invalid", "PDF path is missing.")
            return
        path = resolved_path(value, self.workdir)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            self.problem(result, "missing", "source_pdf_missing", "Source PDF is missing.", path)
            return
        self.matches(result, record, "source_sha256", "source PDF", expected=digest)
        result.details["pdf_path"] = str(path)
        result.details["source_sha256"] = digest

    def check_source(self, result: StageResult, record: dict) -> None:
        pdf = record.get("pdf")
        if not isinstance(pdf, dict):
            self.problem(
                result, "invalid", "source_pdf_reference_invalid", "pdf must be an object."
            )
        else:
            self.check_pdf(result, {**record, "pdf_path": pdf.get("path")})
        corpus = load_source_corpus(self.paths[result.id])
        raw_path = self.paths["raw_sections"]
        if corpus.raw_sections_path != raw_path:
            self.problem(
                result,
                "invalid",
                "raw_sections_selection_mismatch",
                "Selected raw_sections differs from the manifest's referenced corpus.",
                raw_path,
            )
        for item in validate_source_corpus(corpus):
            self.problem(
                result,
                "stale" if "hash_mismatch" in item["code"] else "invalid",
                item["code"],
                item.get("message", item["code"]),
                item.get("path"),
            )
        fetch = self.data.get("fetch", {})
        if fetch.get("source_sha256") and record.get("source_sha256") != fetch["source_sha256"]:
            self.problem(
                result,
                "stale",
                "source_fetch_sha256_mismatch",
                "Source manifest and selected fetch refer to different PDF bytes.",
            )

    def check_decisions(self, result: StageResult, record: dict) -> None:
        source = self.data.get("source_manifest")
        if source is None:
            self.problem(
                result,
                "present_unverified",
                "input_unavailable",
                "Source manifest is required to validate all figure/table decisions.",
            )
            return
        for item in validate_figure_decisions(source, record, str(self.paths["source_manifest"])):
            self.problem(
                result, "stale" if "stale" in item["code"] else "failed", item["code"], str(item)
            )
        self.gap(
            result, "Decision validation checks current visuals; producer input history is unknown."
        )

    def check_admission(self, result: StageResult, record: dict) -> None:
        if record.get("phase") != "save_target_admission" and record.get("status") != "blocked":
            self.problem(
                result,
                "invalid",
                "admission_phase_invalid",
                "Expected a Save Target Admission receipt.",
            )
        self.matches(
            result,
            record,
            "source_sha256",
            "source_manifest",
            expected=self.data.get("source_manifest", {}).get("source_sha256"),
        )
        if record.get("status") == "blocked":
            result.details["requires_user_action"] = True
        self.gap(result, "Admission is historical; current target conflicts have not been checked.")
        if self.context.get("save_mode") is None:
            self.problem(
                result,
                "present_unverified",
                "save_mode_context_missing",
                "Select save_mode; an admission receipt does not establish the save mode.",
            )

    def check_plan(self, result: StageResult, record: dict) -> None:
        source = self.data.get("source_manifest")
        if not self.context.get("output_language"):
            return
        if source is None:
            self.problem(
                result,
                "present_unverified",
                "input_unavailable",
                "Source manifest is required to validate the Note Plan.",
            )
            return
        for item in validate_note_plan(
            record, source, self.context.get("output_language")
        ) + validate_bundle_contract(record, self.data.get("bundle", {})):
            self.problem(result, "failed", item["code"], str(item))
        self.gap(result, "The model-authored plan has no recorded parent-byte fingerprints.")

    def check_grounding(self, result: StageResult, record: dict) -> None:
        if record.get("passes_grounding") is not True:
            self.problem(
                result,
                "failed",
                "grounding_gate_not_true",
                "passes_grounding must be literal true.",
            )
        for field_name, artifact in (
            ("note_plan_sha256", "note_plan"),
            ("source_manifest_sha256", "source_manifest"),
            ("figure_decisions_sha256", "figure_table_decisions"),
        ):
            self.matches(result, record, field_name, artifact)
        self.gap(result, "Grounding Lint does not fingerprint its optional synthesis bundle.")

    def check_draft(self, result: StageResult, record: dict) -> None:
        text = self.raw[result.id].decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            self.problem(result, "invalid", "draft_empty", "Draft is empty.")
        self.gap(result, "Draft authorship and grounding history require model review.")

    def check_lint(self, result: StageResult, record: dict) -> None:
        for gate in LINT_GATES:
            if record.get(gate) is not True:
                self.problem(
                    result, "failed", "lint_gate_not_true", f"{gate} must be literal true."
                )
        self.matches(result, record, "note_plan_sha256", "note_plan")
        normalized = None
        if "draft" in self.raw:
            text = self.raw["draft"].decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            normalized = hashlib.sha256(text.encode()).hexdigest()
        self.matches(result, record, "note_sha256", "draft", expected=normalized)

    def check_quality(self, result: StageResult, record: dict) -> None:
        language = self.context.get("output_language")
        if not self.language(result, record):
            return
        if "draft" not in self.raw or "note_plan" not in self.data:
            self.problem(
                result,
                "present_unverified",
                "input_unavailable",
                "Quality review requires the selected draft and Note Plan.",
            )
            return
        canonical_note_text(self.raw["draft"])
        state_path = self.paths[result.id].with_suffix(".state.json")
        result.details["state_path"] = str(state_path)
        try:
            state = strict_json_loads(state_path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            state = None
        if state is not None:
            validate_state(state, language=language)
            result.details.update(
                revisions_used=state["revisions_used"],
                revisions_remaining=2 - state["revisions_used"],
            )
            if state["exhausted_note_sha256"]:
                result.details["revision_allowed"] = False
                if state["exhausted_note_sha256"] != self.hashes["draft"]:
                    self.problem(
                        result,
                        "failed",
                        "quality_revision_limit_exhausted",
                        "Draft changed after the two-revision budget was exhausted.",
                        state_path,
                    )
        for field_name, artifact in (
            ("reviewed_note_sha256", "draft"),
            ("reviewed_plan_sha256", "note_plan"),
        ):
            self.matches(result, record, field_name, artifact)
        if result.status == "stale":
            return
        review_id = validate_quality(
            record,
            note_sha256=self.hashes["draft"],
            plan_sha256=self.hashes["note_plan"],
            plan=self.data["note_plan"],
            language=language,
        )
        result.details["review_id"] = review_id
        if state is None:
            self.problem(
                result,
                "present_unverified",
                "quality_review_unrecorded",
                "Review is valid but has not been recorded.",
                state_path,
            )
            result.details["record_required"] = True
            return
        if (
            state["exhausted_note_sha256"]
            and state["exhausted_note_sha256"] != self.hashes["draft"]
        ):
            self.problem(
                result,
                "failed",
                "quality_revision_limit_exhausted",
                "Draft changed after the two-revision budget was exhausted.",
                state_path,
            )
        elif review_id != state["last_review"]["review_id"]:
            if review_id in state["seen_review_ids"]:
                self.problem(
                    result,
                    "failed",
                    "quality_review_replay",
                    "An old review cannot restore an earlier pass.",
                    state_path,
                )
            else:
                self.problem(
                    result,
                    "present_unverified",
                    "quality_review_unrecorded",
                    "Current review is valid but has not been recorded.",
                    state_path,
                )
                result.details["record_required"] = True
        elif record["verdict"] == "fail":
            expected = {
                "review_id": review_id,
                "note_sha256": self.hashes["draft"],
                "plan_sha256": self.hashes["note_plan"],
                "verdict": "fail",
            }
            if state["last_review"] != expected:
                raise ValueError("Recorded failing review does not match current inputs.")
            result.details["revision_allowed"] = state["revisions_used"] < 2
            self.problem(
                result, "failed", "quality_review_failed", "Recorded quality review failed."
            )
        else:
            require_recorded_pass(state, record, review_id, language=language)

    def check_readability(self, result: StageResult, record: dict) -> None:
        if not self.language(result, record):
            return
        if "draft" not in self.raw:
            self.problem(result, "present_unverified", "input_unavailable", "Draft is unavailable.")
            return
        canonical_note_text(self.raw["draft"])
        self.matches(result, record, "reviewed_note_sha256", "draft")
        if record.get("verdict") == "fail":
            validate_readability(
                {**record, "verdict": "pass"},
                note_sha256=record.get("reviewed_note_sha256"),
                language=self.context["output_language"],
            )
            self.problem(
                result, "failed", "readability_review_failed", "Readability review failed."
            )
        elif result.status != "stale":
            validate_readability(
                record, note_sha256=self.hashes["draft"], language=self.context["output_language"]
            )

    def check_save(self, result: StageResult, record: dict) -> None:
        for key in ("note_path", "base_output_root"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"Save receipt requires {key}.")
        mode = record.get("output_mode")
        if mode not in {"workspace", "obsidian"}:
            raise ValueError("Save receipt requires output_mode workspace or obsidian.")
        path = resolved_path(record["note_path"], self.workdir)
        root = resolved_path(record["base_output_root"], self.workdir)
        if not path.is_relative_to(root) or path == root:
            raise ValueError("Saved note_path must be below base_output_root.")
        if path.parent == root:
            raise ValueError("Saved note requires a paper-local directory below its output root.")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            self.problem(
                result,
                "missing",
                "saved_note_missing",
                "Receipt exists but the saved note is missing.",
                path,
            )
            return
        canonical_note_text(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.matches(result, record, "reviewed_note_sha256", "saved note", expected=digest)
        matched = self.hashes.get("draft") == digest
        if not matched:
            self.problem(
                result,
                "stale",
                "saved_note_sha256_mismatch",
                "Saved note bytes differ from the selected draft.",
                path,
            )
        if (
            record.get("final_quality_review") != "pass"
            or record.get("final_readability_review") != "pass"
        ):
            self.problem(
                result,
                "failed",
                "save_review_receipts_not_passed",
                "Save receipt must record both final reviews as pass.",
            )
        if mode == "obsidian":
            self.matches(
                result,
                record,
                "source_sha256",
                "source_manifest",
                expected=self.data.get("source_manifest", {}).get("source_sha256"),
            )
        subdir = record.get("subdir")
        if not isinstance(subdir, str):
            raise ValueError("Save receipt requires subdir.")
        subdir_parts = safe_relative_path_parts(subdir, "receipt subdir")
        domain = path.parent.parent.relative_to(root)
        ancestors = [
            parent.relative_to(root).parts for parent in path.parents if parent.is_relative_to(root)
        ]
        if subdir_parts and not any(
            parts[-len(subdir_parts) :] == subdir_parts for parts in ancestors
        ):
            raise ValueError(
                "Save receipt subdir does not match the saved note's actual ancestors."
            )
        domain_name = domain.as_posix()
        if mode == "obsidian":
            papers_dir = self.context.get("papers_dir")
            if papers_dir:
                papers_root = root.joinpath(
                    *safe_relative_path_parts(papers_dir, "papers_dir")
                ).resolve()
                if papers_root.is_relative_to(root) and path.parent.parent.is_relative_to(
                    papers_root
                ):
                    domain_name = path.parent.parent.relative_to(papers_root).as_posix()
                else:
                    domain_name = None
                    self.gap(
                        result, "Selected papers_dir does not establish the saved note's domain."
                    )
            else:
                domain_name = None
                self.gap(result, "Obsidian saved domain requires explicit papers_dir context.")
        result.details.update(
            note_path=str(path),
            output_mode=mode,
            base_output_root=str(root),
            domain=domain_name,
            saved_sha256=digest,
            saved_sha256_match=matched,
        )


COMMANDS = {
    "resolve": ("resolve_paper.py", (("--input", "@paper_reference"), ("--output", "resolve"))),
    "metadata": ("collect_metadata.py", (("--input", "resolve"), ("--output", "metadata"))),
    "identity": (
        "build_identity_contract.py",
        (
            ("--input", "metadata"),
            ("--resolve", "resolve"),
            ("--trace-output", "identity_repair_trace"),
            ("--output", "identity"),
        ),
    ),
    "fetch": (
        "fetch_pdf.py",
        (
            ("--input", "metadata"),
            ("--identity", "identity"),
            ("--reference", "@paper_reference"),
            ("--dest-dir", "pdfs"),
            ("--output", "fetch"),
        ),
    ),
    "source_manifest": (
        "extract_source_text.py",
        (
            ("--input", "fetch"),
            ("--output", "source_manifest"),
            ("--raw-sections-output", "raw_sections"),
            ("--full-text-output", "full_text"),
        ),
    ),
    "evidence": (
        "extract_evidence.py",
        (("--input", "fetch"), ("--source-manifest", "source_manifest"), ("--output", "evidence")),
    ),
    "assets": (
        "extract_pdf_assets.py",
        (("--input", "fetch"), ("--assets-dir", "assets_directory"), ("--output", "assets")),
    ),
    "figures": (
        "plan_figures.py",
        (
            ("--evidence", "evidence"),
            ("--assets", "assets"),
            ("--language", "@output_language"),
            ("--output", "figures"),
        ),
    ),
    "figure_table_decisions": (
        "plan_figure_table_decisions.py",
        (
            ("--source-manifest", "source_manifest"),
            ("--figures", "figures"),
            ("--assets", "assets"),
            ("--language", "@output_language"),
            ("--output", "figure_table_decisions"),
        ),
    ),
    "bundle": (
        "build_synthesis_bundle.py",
        (
            ("--metadata", "metadata"),
            ("--evidence", "evidence"),
            ("--figures", "figures"),
            ("--assets", "assets"),
            ("--source-manifest", "source_manifest"),
            ("--figure-decisions", "figure_table_decisions"),
            ("--language", "@output_language"),
            ("--output", "bundle"),
        ),
    ),
    "admission": (
        "write_obsidian_note.py",
        (
            ("--preflight", ""),
            ("--input", "metadata"),
            ("--source-manifest", "source_manifest"),
            ("--language", "@output_language"),
            ("--save-mode", "@save_mode"),
            ("--vault", "@vault"),
            ("--papers-dir", "@papers_dir"),
            ("--output", "admission"),
        ),
    ),
    "grounding_lint": (
        "lint_grounding.py",
        (
            ("--note-plan", "note_plan"),
            ("--source-manifest", "source_manifest"),
            ("--figure-decisions", "figure_table_decisions"),
            ("--bundle-json", "bundle"),
            ("--language", "@output_language"),
            ("--output", "grounding_lint"),
        ),
    ),
    "note_lint": (
        "lint_note.py",
        (
            ("--input", "draft"),
            ("--plan-file", "note_plan"),
            ("--language", "@output_language"),
            ("--output", "note_lint"),
        ),
    ),
    "record_quality": (
        "write_obsidian_note.py",
        (
            ("--record-final-quality-review", ""),
            ("--language", "@output_language"),
            ("--content-file", "draft"),
            ("--plan-file", "note_plan"),
            ("--final-quality-review", "quality_review"),
        ),
    ),
    "save_receipt": (
        "write_obsidian_note.py",
        (
            ("--input", "metadata"),
            ("--content-file", "draft"),
            ("--plan-file", "note_plan"),
            ("--source-manifest", "source_manifest"),
            ("--lint-json", "note_lint"),
            ("--grounding-lint-json", "grounding_lint"),
            ("--figure-decisions", "figure_table_decisions"),
            ("--final-quality-review", "quality_review"),
            ("--final-readability-review", "readability_review"),
            ("--language", "@output_language"),
            ("--save-mode", "@save_mode"),
            ("--output", "save_receipt"),
        ),
    ),
}


def next_action(run: Inspection) -> dict:
    for stage in STAGES:
        result = run.results[stage.id]
        if result.details.get("required") is False:
            continue
        codes = {item["code"] for item in result.issues}
        if (
            result.status in {"passed", "present_unverified"}
            and not result.details.get("record_required")
            and not codes & {"language_context_missing", "save_mode_context_missing"}
        ):
            continue
        action = {
            "stage": stage.id,
            "kind": "missing_context",
            "missing_context": [],
            "input_paths": {
                key: str(run.paths[key]) for key in stage.dependencies if run.paths.get(key)
            },
            "reference": str(Path(__file__).resolve().parents[1] / "SKILL.md"),
        }
        if stage.id == "admission" and run.context.get("save_mode") is None:
            action["missing_context"] = ["save_mode"]
            return action
        if "language_context_missing" in codes:
            action["missing_context"] = ["output_language"]
            return action
        if result.details.get("requires_user_action") or codes & {
            "quality_revision_limit_exhausted",
            "quality_review_replay",
        }:
            action.update(
                kind="user_action", message="Resolve the recorded conflict or review history."
            )
            return action
        if (
            stage.id == "quality_review"
            and result.details.get("revision_allowed") is False
            and not result.details.get("record_required")
        ):
            action.update(
                kind="user_action", message="Two quality revisions are exhausted; stop rewriting."
            )
            return action
        if stage.action == "model" and not result.details.get("record_required"):
            action.update(
                kind="model_action",
                output_path=str(run.paths[stage.id]) if run.paths[stage.id] else None,
                message="Perform the canonical model-led stage with the selected input artifacts.",
            )
            for key in (
                "source_manifest",
                "raw_sections",
                "bundle",
                "figure_table_decisions",
                "note_plan",
                "draft",
            ):
                if key != stage.id and run.paths.get(key):
                    action["input_paths"][key] = str(run.paths[key])
            if run.context.get("output_language") is None:
                action["missing_context"].append("output_language")
            if run.paths[stage.id] is None:
                action["missing_context"].append(f"artifacts.{stage.id}")
            return action
        recipe_id = "record_quality" if result.details.get("record_required") else stage.id
        script, recipe = COMMANDS[recipe_id]
        argv = [sys.executable, str(Path(__file__).resolve().parent / script)]
        for flag, source in recipe:
            value = run.context.get(source[1:]) if source.startswith("@") else run.paths.get(source)
            if not source:
                argv.append(flag)
            elif value is None:
                action["missing_context"].append(
                    source[1:] if source.startswith("@") else f"artifacts.{source}"
                )
            else:
                argv.extend((flag, str(value)))
        if stage.id == "figure_table_decisions":
            mode = run.context.get("save_mode")
            if mode == "workspace":
                argv.extend(("--asset-subdir", "images"))
            elif mode == "obsidian":
                admission = run.results["admission"]
                asset_subdir = run.data.get("admission", {}).get("asset_subdir")
                source_sha = run.data.get("source_manifest", {}).get("source_sha256")
                if (
                    admission.status != "passed"
                    or admission.unmet_dependencies
                    or not isinstance(asset_subdir, str)
                    or asset_subdir not in ("images", f"images/{source_sha}")
                ):
                    action["missing_context"].append("admission.asset_subdir")
                else:
                    argv.extend(("--asset-subdir", asset_subdir))
            else:
                action["missing_context"].append("save_mode")
        if stage.id == "save_receipt" and run.context.get("save_mode") == "obsidian":
            for key in ("vault", "papers_dir"):
                value = run.context.get(key)
                if value is None:
                    action["missing_context"].append(key)
                else:
                    argv.extend(("--" + key.replace("_", "-"), value))
        if run.context.get("target_directory") and stage.id in {
            "admission",
            "fetch",
            "save_receipt",
        }:
            argv.extend(("--target-directory", run.context["target_directory"]))
        if not action["missing_context"]:
            action.update(kind="command", argv=argv, cwd=str(run.workdir))
        return action
    unresolved = [
        stage.id for stage in STAGES if run.results[stage.id].status == "present_unverified"
    ]
    return {
        "kind": "manual_verification",
        "stage": unresolved[0] if unresolved else None,
        "stages": unresolved,
        "reference": str(Path(__file__).resolve().parents[1] / "SKILL.md"),
        "message": (
            "Review unprovable producer history; this report does not certify the whole workflow."
        ),
    }


def inspect_run(workdir: str | Path, prefix: str = "run", bindings: dict | None = None) -> dict:
    workdir = Path(workdir).expanduser().resolve()
    if not workdir.is_dir():
        raise ValueError("workdir must be an existing directory.")
    if (
        not isinstance(prefix, str)
        or not prefix.strip()
        or prefix in {".", ".."}
        or any(char in prefix for char in ("/", "\\", "\x00"))
    ):
        raise ValueError("prefix must be a nonempty basename without traversal or separators.")
    run = Inspection(
        workdir, prefix, validate_bindings({"schema_version": 1} if bindings is None else bindings)
    )
    for stage in STAGES:
        run.results[stage.id] = run.evaluate(stage)
    save = run.results["save_receipt"]
    verified = save.status == "passed" and not save.unmet_dependencies
    decisions = run.data.get("figure_table_decisions", {}).get("decisions")
    counts = None
    if isinstance(decisions, list) and all(isinstance(item, dict) for item in decisions):
        counts = {
            "insert": sum(item.get("decision") == "insert" for item in decisions),
            "placeholder": sum(item.get("decision") == "placeholder" for item in decisions),
        }
    metadata = (
        run.data.get("metadata", {})
        if (
            run.results["metadata"].status in {"passed", "present_unverified"}
            and not run.results["metadata"].unmet_dependencies
        )
        else {}
    )
    identity = (
        run.data.get("identity", {})
        if (
            run.results["identity"].status == "passed"
            and not run.results["identity"].unmet_dependencies
        )
        else {}
    )
    accepted = identity if not canonical_identity_acceptance_error(identity) else {}
    if (
        accepted.get("paper_id")
        and metadata.get("paper_id")
        and accepted["paper_id"] != metadata["paper_id"]
    ):
        metadata = {}
    canonical = accepted.get("work_level_identity", {})
    if not isinstance(canonical, dict):
        canonical = {}
    title = canonical.get("title") or accepted.get("title") or metadata.get("title")
    identifier = next(
        (
            canonical.get(key) or metadata.get(key)
            for key in ("doi", "arxiv_id", "zotero_key")
            if canonical.get(key) or metadata.get(key)
        ),
        None,
    )
    warnings = [record.get("warnings") for record in run.data.values()]
    warning_count = sum(len(value) for value in warnings if isinstance(value, list))
    summary = {
        "saved_verified": verified,
        "title": title,
        "strong_identifier": identifier,
        "gate_verdicts": {
            key: run.results[key].status
            for key in ("grounding_lint", "note_lint", "quality_review", "readability_review")
        },
        "warning_count": warning_count,
        "figure_counts": counts,
        "saved_mode": save.details.get("output_mode") if verified else None,
        "saved_path": save.details.get("note_path") if verified else None,
        "saved_domain": save.details.get("domain") if verified else None,
        "saved_sha256_match": save.details.get("saved_sha256_match"),
    }
    if "save_receipt" not in run.raw:
        run.gap(save, "No selected save receipt; this does not prove that no save occurred.")
    return {
        "schema_version": 1,
        "script": "run_state.py",
        "status": "ok",
        "workdir": str(workdir),
        "prefix": prefix,
        "resolved_context": run.context,
        "artifacts": {
            key: {
                "path": str(path) if path else None,
                "selection": run.selections[key],
                "sha256": run.hashes.get(key),
            }
            for key, path in run.paths.items()
        },
        "stages": [asdict(result) for result in run.results.values()],
        "next_action": next_action(run),
        "provenance_gaps": run.provenance_gaps,
        "summary": summary,
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(
            json.dumps(
                {"schema_version": 1, "script": "run_state.py", "status": "error", "error": message}
            )
        )
        raise SystemExit(2)


def main() -> None:
    parser = JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(
        dest="command", required=True, parser_class=JsonArgumentParser
    )
    status = subparsers.add_parser("status")
    status.add_argument("--workdir", required=True)
    status.add_argument("--prefix", default="run")
    status.add_argument("--bindings", help="Bindings JSON file, resolved against the caller's cwd.")
    args = parser.parse_args()
    try:
        bindings = (
            strict_json_loads(Path(args.bindings).expanduser().read_text(encoding="utf-8-sig"))
            if args.bindings
            else None
        )
        report = inspect_run(args.workdir, args.prefix, bindings)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
