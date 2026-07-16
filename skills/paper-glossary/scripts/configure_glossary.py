#!/usr/bin/env python3
"""Configure and inspect the device-local paper-glossary vault."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from glossary_common import elapsed_ms
from glossary_config import (
    configure_terms_dir,
    default_config_path,
    load_config,
    resolve_terms_dir,
    validate_article,
)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description=__doc__ or "configure paper-glossary"
    )
    modes = command.add_mutually_exclusive_group(required=True)
    modes.add_argument("--terms-dir", metavar="PATH", help="Term-library directory.")
    modes.add_argument("--show", action="store_true", help="Show saved configuration.")
    modes.add_argument("--reset", action="store_true", help="Remove saved configuration.")
    modes.add_argument(
        "--validate-article", metavar="PATH", help="Validate an article Markdown path."
    )
    command.add_argument("--config-path", metavar="PATH", help="Config JSON path.")
    command.add_argument("--output", default="", metavar="PATH", help="Output JSON path.")
    return command


def _emit(payload: dict[str, Any], output: str) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def main() -> None:
    started = perf_counter()
    args = parser().parse_args()
    config_path = Path(args.config_path).expanduser() if args.config_path else None

    if args.terms_dir:
        payload = configure_terms_dir(Path(args.terms_dir), config_path)
    elif args.show:
        config = load_config(config_path)
        if config is None:
            payload = {"workflow_state": "needs_configuration"}
        else:
            payload = {**config, "terms_dir": str(resolve_terms_dir(config))}
    elif args.reset:
        target = config_path or default_config_path()
        if target.expanduser().is_file():
            target.expanduser().unlink()
        payload = {"workflow_state": "reset"}
    else:
        config = load_config(config_path)
        if config is None:
            raise SystemExit(
                "Paper-glossary is not configured; run with --terms-dir first."
            )
        terms_dir = resolve_terms_dir(config)
        payload = {"terms_dir": str(terms_dir), **validate_article(Path(args.validate_article), config)}

    _emit({**payload, "elapsed_ms": elapsed_ms(started)}, args.output)


if __name__ == "__main__":
    main()
