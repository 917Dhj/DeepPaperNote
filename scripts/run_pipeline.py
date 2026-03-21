#!/usr/bin/env python3
"""Run the deterministic DeepPaperNote stages sequentially for one paper."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__ or "run pipeline")
    p.add_argument("--input", required=True, help="Paper title, DOI, URL, arXiv id, local PDF path, or JSON artifact.")
    p.add_argument("--workdir", default="tmp/DeepPaperNote_runs", help="Directory for intermediate artifacts.")
    p.add_argument("--prefix", default="run", help="Filename prefix for artifacts.")
    return p


def run_step(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parser().parse_args()
    scripts_dir = Path(__file__).resolve().parent
    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    resolve_json = workdir / f"{args.prefix}_resolve.json"
    metadata_json = workdir / f"{args.prefix}_metadata.json"
    fetch_json = workdir / f"{args.prefix}_fetch.json"
    evidence_json = workdir / f"{args.prefix}_evidence.json"
    assets_json = workdir / f"{args.prefix}_assets.json"
    figures_json = workdir / f"{args.prefix}_figures.json"
    bundle_json = workdir / f"{args.prefix}_bundle.json"
    py = sys.executable
    run_step([py, str(scripts_dir / "resolve_paper.py"), "--input", args.input, "--output", str(resolve_json)])
    run_step([py, str(scripts_dir / "collect_metadata.py"), "--input", args.input, "--output", str(metadata_json)])
    run_step([py, str(scripts_dir / "fetch_pdf.py"), "--input", args.input, "--output", str(fetch_json)])
    run_step([py, str(scripts_dir / "extract_evidence.py"), "--input", str(fetch_json), "--output", str(evidence_json)])
    run_step([py, str(scripts_dir / "extract_pdf_assets.py"), "--input", str(fetch_json), "--output", str(assets_json)])
    run_step(
        [
            py,
            str(scripts_dir / "plan_figures.py"),
            "--evidence",
            str(evidence_json),
            "--assets",
            str(assets_json),
            "--output",
            str(figures_json),
        ]
    )
    run_step(
        [
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
            "--output",
            str(bundle_json),
        ]
    )

    print(
        "\n".join(
            [
                f"resolve={resolve_json}",
                f"metadata={metadata_json}",
                f"fetch={fetch_json}",
                f"evidence={evidence_json}",
                f"assets={assets_json}",
                f"figures={figures_json}",
                f"bundle={bundle_json}",
            ]
        )
    )


if __name__ == "__main__":
    main()
