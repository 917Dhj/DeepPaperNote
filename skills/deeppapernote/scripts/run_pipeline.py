#!/usr/bin/env python3
"""Run the deterministic DeepPaperNote stages sequentially for one paper."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from common import runtime_config


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


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "run pipeline")
    p.add_argument(
        "--input",
        required=True,
        help="Paper title, DOI, URL, arXiv id, local PDF path, or JSON artifact.",
    )
    p.add_argument(
        "--workdir",
        default="tmp/DeepPaperNote_runs",
        help="Directory for intermediate artifacts.",
    )
    p.add_argument("--prefix", default="run", help="Filename prefix for artifacts.")
    p.add_argument(
        "--zotero-mode",
        choices=("auto", "off", "required"),
        default="auto",
        help="Local Zotero lookup policy used by the resolve stage.",
    )
    p.add_argument(
        "--language",
        default="",
        choices=("", "en", "zh-CN"),
        help="Run Override for the output language contract.",
    )
    p.add_argument("--save-mode", choices=("workspace", "obsidian"), default="")
    p.add_argument("--vault", default="", help="Run Override for the Obsidian Vault.")
    p.add_argument("--target-directory", default="", help="Chosen existing paper directory.")
    p.add_argument("--source-sha256", default="", help="Chosen archived source.")
    p.add_argument("--papers-dir", default="", help="Run Override for the Vault paper directory.")
    return p


def run_step(cmd: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    args = parser().parse_args()
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
    run_environment = os.environ.copy()
    for field, name in {
        "output_language": "DEEPPAPERNOTE_OUTPUT_LANGUAGE",
        "save_mode": "DEEPPAPERNOTE_SAVE_MODE",
        "obsidian_vault": "DEEPPAPERNOTE_OBSIDIAN_VAULT",
        "papers_dir": "DEEPPAPERNOTE_PAPERS_DIR",
    }.items():
        value = str(config.get(field, "")).strip()
        if value:
            run_environment[name] = value
        else:
            run_environment.pop(name, None)
    scripts_dir = Path(__file__).resolve().parent
    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    paths = pipeline_artifact_paths(workdir, args.prefix)
    resolve_json = paths["resolve"]
    metadata_json = paths["metadata"]
    identity_json = paths["identity"]
    identity_trace_json = paths["identity_repair_trace"]
    fetch_json = paths["fetch"]
    pdf_dir = paths["pdfs"]
    source_manifest_json = paths["source_manifest"]
    raw_sections_jsonl = paths["raw_sections"]
    full_text_md = paths["full_text"]
    evidence_json = paths["evidence"]
    assets_json = paths["assets"]
    assets_dir = paths["assets_directory"]
    figures_json = paths["figures"]
    figure_decisions_json = paths["figure_table_decisions"]
    bundle_json = paths["bundle"]
    py = sys.executable
    run_step(
        [
            py,
            str(scripts_dir / "resolve_paper.py"),
            "--input",
            args.input,
            "--zotero-mode",
            args.zotero_mode,
            "--output",
            str(resolve_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "collect_metadata.py"),
            "--input",
            str(resolve_json),
            "--output",
            str(metadata_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "build_identity_contract.py"),
            "--input",
            str(metadata_json),
            "--resolve",
            str(resolve_json),
            "--trace-output",
            str(identity_trace_json),
            "--output",
            str(identity_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "fetch_pdf.py"),
            "--input",
            str(metadata_json),
            "--identity",
            str(identity_json),
            "--reference",
            args.input,
            "--target-directory",
            args.target_directory,
            "--source-sha256",
            args.source_sha256,
            "--dest-dir",
            str(pdf_dir),
            "--output",
            str(fetch_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "extract_source_text.py"),
            "--input",
            str(fetch_json),
            "--output",
            str(source_manifest_json),
            "--raw-sections-output",
            str(raw_sections_jsonl),
            "--full-text-output",
            str(full_text_md),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "extract_evidence.py"),
            "--input",
            str(fetch_json),
            "--source-manifest",
            str(source_manifest_json),
            "--output",
            str(evidence_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "extract_pdf_assets.py"),
            "--input",
            str(fetch_json),
            "--assets-dir",
            str(assets_dir),
            "--output",
            str(assets_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "plan_figures.py"),
            "--evidence",
            str(evidence_json),
            "--assets",
            str(assets_json),
            "--language",
            args.language,
            "--output",
            str(figures_json),
        ],
        env=run_environment,
    )
    run_step(
        [
            py,
            str(scripts_dir / "plan_figure_table_decisions.py"),
            "--source-manifest",
            str(source_manifest_json),
            "--figures",
            str(figures_json),
            "--assets",
            str(assets_json),
            "--language",
            args.language,
            "--output",
            str(figure_decisions_json),
        ],
        env=run_environment,
    )
    bundle_command = [
            py,
            str(scripts_dir / "build_synthesis_bundle.py"),
            "--metadata",
            str(metadata_json),
            "--evidence",
            str(evidence_json),
            "--figures",
            str(figures_json),
            "--assets",
            str(assets_json),
            "--source-manifest",
            str(source_manifest_json),
            "--figure-decisions",
            str(figure_decisions_json),
            "--output",
            str(bundle_json),
        ]
    if args.language:
        bundle_command.extend(["--language", args.language])
    run_step(bundle_command, env=run_environment)

    print(
        "\n".join(
            [
                f"resolve={resolve_json}",
                f"metadata={metadata_json}",
                f"identity={identity_json}",
                f"identity_repair_trace={identity_trace_json}",
                f"fetch={fetch_json}",
                f"source_manifest={source_manifest_json}",
                f"raw_sections={raw_sections_jsonl}",
                f"full_text_md={full_text_md}",
                f"evidence={evidence_json}",
                f"assets={assets_json}",
                f"figures={figures_json}",
                f"figure_table_decisions={figure_decisions_json}",
                f"bundle={bundle_json}",
            ]
        )
    )


if __name__ == "__main__":
    main()
