from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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
