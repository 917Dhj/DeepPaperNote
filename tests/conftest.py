from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def configured_user_home(tmp_path: Path, monkeypatch) -> Path:
    config_path = tmp_path / ".deeppapernote" / "config.json"
    config_path.parent.mkdir(exist_ok=True)
    for name in (
        "DEEPPAPERNOTE_OUTPUT_LANGUAGE",
        "DEEPPAPERNOTE_SAVE_MODE",
        "DEEPPAPERNOTE_OBSIDIAN_VAULT",
        "DEEPPAPERNOTE_PAPERS_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPPAPERNOTE_CONFIG_PATH", str(config_path))
    config_path.write_text(
        json.dumps(
            {
                "output_language": "zh-CN",
                "save_mode": "workspace",
                "papers_dir": "Research/Papers",
            }
        ),
        encoding="utf-8",
    )
    return config_path
