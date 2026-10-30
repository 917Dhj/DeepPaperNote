from __future__ import annotations

import hashlib
import json
from pathlib import Path


def formal_save_args(
    tmp_path: Path,
    note_text: str,
    output_language: str = "zh-CN",
    *,
    lint_path: Path | None = None,
    decisions_path: Path | None = None,
    source_manifest_path: Path | None = None,
    plan_path: Path | None = None,
) -> list[str]:
    plan_path = plan_path or tmp_path / f"save-plan.{output_language}.json"
    if not plan_path.exists():
        plan_path.write_text(json.dumps({"output_language": output_language}), encoding="utf-8")
    source_manifest_path = source_manifest_path or tmp_path / "source-manifest.json"
    if not source_manifest_path.exists():
        source_manifest_path.write_text(
            json.dumps({"status": "ok", "paper_id": "paper:test", "source_sha256": "a" * 64}),
            encoding="utf-8",
        )
    if decisions_path is None:
        decisions_path = tmp_path / "figure-decisions.json"
        decisions_path.write_text(
            json.dumps({"output_language": output_language, "decisions": []}), encoding="utf-8"
        )
    new_lint = lint_path is None or not lint_path.exists()
    lint = (
        json.loads(lint_path.read_text(encoding="utf-8-sig"))
        if lint_path is not None and lint_path.exists()
        else {}
    )
    lint_path = lint_path or tmp_path / "passing-lint.json"
    for key, value in {
        "status": "ok",
        "script": "lint_note.py",
        **({"output_language": output_language} if new_lint else {}),
        "note_sha256": hashlib.sha256(
            note_text.removeprefix("\ufeff").replace("\r\n", "\n").encode("utf-8")
        ).hexdigest(),
        "passes_basic_structure": True,
        "passes_style_gate": True,
        "passes_math_gate": True,
        "passes_figure_gate": True,
        "passes_plan_gate": True,
        "passes_substantive_content": True,
        "passes_reference_hygiene_gate": True,
    }.items():
        lint.setdefault(key, value)
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    lint["note_plan_sha256"] = plan_hash
    lint_path.write_text(json.dumps(lint), encoding="utf-8")
    grounding_path = tmp_path / "passing-grounding.json"
    grounding_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "script": "lint_grounding.py",
                "output_language": output_language,
                "passes_grounding": True,
                "note_plan_sha256": plan_hash,
                "source_manifest_sha256": hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
                "figure_decisions_sha256": hashlib.sha256(decisions_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return [
        "--lint-json", str(lint_path),
        "--figure-decisions", str(decisions_path),
        "--plan-file", str(plan_path),
        "--grounding-lint-json", str(grounding_path),
        "--source-manifest", str(source_manifest_path),
    ]


def reviewed_insert_fields(source_image: Path) -> dict:
    digest = hashlib.sha256(source_image.read_bytes()).hexdigest()
    preview = source_image.with_name(f"{source_image.stem}-preview.png")
    preview.write_bytes(b"page-preview")
    source_pdf = source_image.with_name(f"{source_image.stem}-source.pdf")
    source_pdf.write_bytes(b"source-pdf")
    return {
        "source_image_sha256": digest,
        "review_evidence": {
            "candidate_path": str(source_image),
            "page_preview_path": str(preview),
            "source_pdf_path": str(source_pdf),
            "source_page": 1,
            "caption": "Architecture",
            "bbox_pt": [10.0, 20.0, 190.0, 220.0],
            "normalized_bbox": [0.05, 0.05, 0.95, 0.55],
            "render_dpi": 300,
        },
        "visual_review": {
            "status": "pass",
            "reviewed_asset_sha256": digest,
            "preserved_scientific_elements": ["complete figure"],
            "omitted_scientific_elements": [],
            "notes": "Caption-free visual body.",
            "failure_reason": "",
            "repair_attempts": 0,
            "revised_bbox": [],
        },
    }
