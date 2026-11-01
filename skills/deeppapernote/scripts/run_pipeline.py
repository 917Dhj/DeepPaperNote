#!/usr/bin/env python3
"""Run the deterministic DeepPaperNote stages for one paper.

`acquire` runs through the Source Manifest. `prepare` builds the evidence through
the Synthesis Bundle from those artifacts, after Save Target Admission in Obsidian
mode. Without a phase, workspace mode runs both in one pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from common import runtime_config
from user_configuration import ENV_FIELDS

BLOCKED_EXIT_CODE = 2
WORKDIR_NAME_LENGTH = 40
PHASES = ("acquire", "prepare")
ADMISSION_STEPS = (
    "Obsidian mode needs Save Target Admission before evidence: run `run_pipeline.py acquire`, "
    "then `write_obsidian_note.py --preflight --output <admission.json>`, "
    "then `run_pipeline.py prepare --admission <admission.json>`."
)


def pipeline_artifact_paths(workdir: Path, prefix: str) -> dict[str, Path]:
    """Return the pipeline's filenames without reading or creating anything."""
    return {
        "resolve": workdir / f"{prefix}_resolve.json",
        "metadata": workdir / f"{prefix}_metadata.json",
        "identity": workdir / f"{prefix}_identity.json",
        "identity_repair_trace": workdir / f"{prefix}_identity_repair_trace.json",
        "fetch": workdir / f"{prefix}_fetch.json",
        "pdfs": workdir / f"{prefix}_pdfs",
        "source_manifest": workdir / f"{prefix}_source_manifest.json",
        "raw_sections": workdir / f"{prefix}_raw_sections.jsonl",
        "full_text": workdir / f"{prefix}_full_text.md",
        "evidence": workdir / f"{prefix}_evidence.json",
        "assets": workdir / f"{prefix}_assets.json",
        "assets_directory": workdir / f"{prefix}_assets",
        "figures": workdir / f"{prefix}_figures.json",
        "figure_table_decisions": workdir / f"{prefix}_figure_table_decisions.json",
        "bundle": workdir / f"{prefix}_bundle.json",
    }


def default_workdir(reference: str) -> Path:
    """Name each paper's directory after its reference, away from the user's project."""
    reference = name = reference.strip()
    if os.path.isfile(reference):
        name = Path(reference).stem
        reference = os.path.abspath(reference)
    name = re.sub(r"[^\w-]+", "_", name)[:WORKDIR_NAME_LENGTH].strip("_") or "paper"
    digest = hashlib.sha256(reference.encode("utf-8")).hexdigest()[:8]
    return Path.home() / ".deeppapernote" / "runs" / f"{name}-{digest}"


def has_review_work(record: dict) -> bool:
    items = record.get("decisions")
    reviews = (
        [item.get("visual_review") for item in items if isinstance(item, dict)]
        if isinstance(items, list)
        else []
    )
    return any(
        isinstance(review, dict)
        and (review.get("status") != "pending" or review.get("repair_attempts"))
        for review in reviews
    )


def read_json_object(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def parser(phase: str = "") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=" ".join(("run_pipeline.py", phase)).strip(),
        description=__doc__ or "run pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    if phase != "prepare":
        p.add_argument(
            "--input",
            required=True,
            help="Paper title, DOI, URL, arXiv id, local PDF path, or JSON artifact.",
        )
    p.add_argument(
        "--workdir",
        required=phase == "prepare",
        default="",
        help=(
            "Directory for intermediate artifacts. "
            "Defaults to a per-paper directory under ~/.deeppapernote/runs."
        ),
    )
    p.add_argument("--prefix", default="run", help="Filename prefix for artifacts.")
    p.add_argument(
        "--language",
        default="",
        choices=("", "en", "zh-CN"),
        help="Run Override for the output language contract.",
    )
    p.add_argument("--save-mode", choices=("workspace", "obsidian"), default="")
    p.add_argument("--vault", default="", help="Run Override for the Obsidian Vault.")
    p.add_argument("--papers-dir", default="", help="Run Override for the Vault paper directory.")
    if phase != "prepare":
        p.add_argument(
            "--zotero-mode",
            choices=("auto", "off", "required"),
            default="auto",
            help="Local Zotero lookup policy used by the resolve stage.",
        )
        p.add_argument("--target-directory", default="", help="Chosen existing paper directory.")
        p.add_argument("--source-sha256", default="", help="Chosen archived source.")
    if phase == "prepare":
        p.add_argument("--admission", default="", help="Obsidian Save Target Admission JSON.")
    if phase != "acquire":
        p.add_argument(
            "--discard-reviews",
            action="store_true",
            help="Replace figure/table decisions that already record Visual Review work.",
        )
    return p


def run_step(cmd: list[str], *, env: dict[str, str]) -> None:
    try:
        subprocess.run(cmd, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        if exc.returncode == BLOCKED_EXIT_CODE:
            raise SystemExit(BLOCKED_EXIT_CODE) from exc
        raise


def require_acquired_source(paths: dict[str, Path]) -> dict:
    manifest = read_json_object(paths["source_manifest"])
    if manifest is None or manifest.get("status") != "ok":
        raise SystemExit(
            f"Expected successful Source Manifest JSON: {paths['source_manifest']}. "
            "Run `run_pipeline.py acquire` first."
        )
    return manifest


def admitted_asset_subdir(admission_path: str, source_manifest: dict, language: str) -> str:
    """Fail before the offline stages when the admission belongs to another run."""
    admission = read_json_object(Path(admission_path).expanduser())
    if (
        admission is None
        or admission.get("status") != "ok"
        or admission.get("phase") != "save_target_admission"
    ):
        raise SystemExit(f"Expected successful Save Target Admission JSON: {admission_path}")
    if admission.get("source_sha256") != source_manifest.get("source_sha256"):
        raise SystemExit("Save Target Admission source_sha256 does not match the Source Manifest.")
    if admission.get("output_language") != language:
        raise SystemExit(
            f"Save Target Admission output_language does not match resolved language {language}."
        )
    return str(admission.get("asset_subdir", ""))


def require_replaceable_decisions(path: Path) -> None:
    if not path.exists():
        return
    record = read_json_object(path)
    if record is None or has_review_work(record):
        raise SystemExit(
            f"{path} may hold Visual Review work that rebuilding would replace. Update it in "
            "place, or pass --discard-reviews to start the reviews over."
        )


def acquire_steps(args: argparse.Namespace, paths: dict[str, Path]) -> list[list[str]]:
    scripts_dir = Path(__file__).resolve().parent
    py = sys.executable
    return [
        [
            py,
            str(scripts_dir / "resolve_paper.py"),
            "--input",
            args.input,
            "--zotero-mode",
            args.zotero_mode,
            "--output",
            str(paths["resolve"]),
        ],
        [
            py,
            str(scripts_dir / "collect_metadata.py"),
            "--input",
            str(paths["resolve"]),
            "--output",
            str(paths["metadata"]),
        ],
        [
            py,
            str(scripts_dir / "build_identity_contract.py"),
            "--input",
            str(paths["metadata"]),
            "--resolve",
            str(paths["resolve"]),
            "--trace-output",
            str(paths["identity_repair_trace"]),
            "--output",
            str(paths["identity"]),
        ],
        [
            py,
            str(scripts_dir / "fetch_pdf.py"),
            "--input",
            str(paths["metadata"]),
            "--identity",
            str(paths["identity"]),
            "--reference",
            args.input,
            "--target-directory",
            args.target_directory,
            "--source-sha256",
            args.source_sha256,
            "--dest-dir",
            str(paths["pdfs"]),
            "--output",
            str(paths["fetch"]),
        ],
        [
            py,
            str(scripts_dir / "extract_source_text.py"),
            "--input",
            str(paths["fetch"]),
            "--output",
            str(paths["source_manifest"]),
            "--raw-sections-output",
            str(paths["raw_sections"]),
            "--full-text-output",
            str(paths["full_text"]),
        ],
    ]


def prepare_steps(
    args: argparse.Namespace, paths: dict[str, Path], asset_subdir: str
) -> list[list[str]]:
    scripts_dir = Path(__file__).resolve().parent
    py = sys.executable
    return [
        [
            py,
            str(scripts_dir / "extract_evidence.py"),
            "--input",
            str(paths["fetch"]),
            "--source-manifest",
            str(paths["source_manifest"]),
            "--output",
            str(paths["evidence"]),
        ],
        [
            py,
            str(scripts_dir / "extract_pdf_assets.py"),
            "--input",
            str(paths["fetch"]),
            "--assets-dir",
            str(paths["assets_directory"]),
            "--output",
            str(paths["assets"]),
        ],
        [
            py,
            str(scripts_dir / "plan_figures.py"),
            "--evidence",
            str(paths["evidence"]),
            "--assets",
            str(paths["assets"]),
            "--language",
            args.language,
            "--output",
            str(paths["figures"]),
        ],
        [
            py,
            str(scripts_dir / "plan_figure_table_decisions.py"),
            "--source-manifest",
            str(paths["source_manifest"]),
            "--figures",
            str(paths["figures"]),
            "--assets",
            str(paths["assets"]),
            "--language",
            args.language,
            "--asset-subdir",
            asset_subdir,
            "--output",
            str(paths["figure_table_decisions"]),
        ],
        [
            py,
            str(scripts_dir / "build_synthesis_bundle.py"),
            "--metadata",
            str(paths["metadata"]),
            "--evidence",
            str(paths["evidence"]),
            "--figures",
            str(paths["figures"]),
            "--assets",
            str(paths["assets"]),
            "--source-manifest",
            str(paths["source_manifest"]),
            "--figure-decisions",
            str(paths["figure_table_decisions"]),
            "--language",
            args.language,
            "--output",
            str(paths["bundle"]),
        ],
    ]


def main() -> None:
    argv = sys.argv[1:]
    phase = argv[0] if argv and argv[0] in PHASES else ""
    args = parser(phase).parse_args(argv[1:] if phase else argv)
    try:
        config = runtime_config(
            cli_overrides={
                "output_language": args.language,
                "save_mode": args.save_mode,
                "obsidian_vault": args.vault,
                "papers_dir": args.papers_dir,
            }
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    args.language = config["output_language"]
    obsidian = config["save_mode"] == "obsidian"
    if obsidian and not phase:
        raise SystemExit(ADMISSION_STEPS)
    run_environment = os.environ.copy()
    for field, name in ENV_FIELDS.items():
        value = str(config.get(field, "")).strip()
        if value:
            run_environment[name] = value
        else:
            run_environment.pop(name, None)
    workdir = Path(args.workdir or default_workdir(args.input)).expanduser().resolve()
    paths = pipeline_artifact_paths(workdir, args.prefix)

    asset_subdir = "images"
    if phase == "prepare":
        source_manifest = require_acquired_source(paths)
        if obsidian:
            if not args.admission:
                raise SystemExit(f"prepare requires --admission. {ADMISSION_STEPS}")
            asset_subdir = admitted_asset_subdir(args.admission, source_manifest, args.language)
    if phase != "acquire" and not args.discard_reviews:
        require_replaceable_decisions(paths["figure_table_decisions"])

    workdir.mkdir(parents=True, exist_ok=True)
    steps = []
    if phase != "prepare":
        steps += acquire_steps(args, paths)
    if phase != "acquire":
        steps += prepare_steps(args, paths, asset_subdir)
    for step in steps:
        run_step(step, env=run_environment)

    outputs = [("workdir", workdir)]
    if phase != "prepare":
        outputs += [
            ("resolve", paths["resolve"]),
            ("metadata", paths["metadata"]),
            ("identity", paths["identity"]),
            ("identity_repair_trace", paths["identity_repair_trace"]),
            ("fetch", paths["fetch"]),
            ("source_manifest", paths["source_manifest"]),
            ("raw_sections", paths["raw_sections"]),
            ("full_text_md", paths["full_text"]),
        ]
    if phase != "acquire":
        outputs += [
            ("evidence", paths["evidence"]),
            ("assets", paths["assets"]),
            ("figures", paths["figures"]),
            ("figure_table_decisions", paths["figure_table_decisions"]),
            ("bundle", paths["bundle"]),
        ]
    print("\n".join(f"{name}={path}" for name, path in outputs))


if __name__ == "__main__":
    main()
