from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "deeppapernote" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


TESTS_DIR = Path(__file__).resolve().parent
# Subprocess shims: an empty HTTP cassette fails every request like an unreachable host,
# and a shadow pytesseract keeps pages from being OCRed, matching CI, which has no tesseract.
OFFLINE_SHIMS = (TESTS_DIR / "http_cassette", TESTS_DIR / "no_ocr")


@pytest.fixture(autouse=True)
def offline_and_ocr_free(tmp_path_factory, monkeypatch) -> None:
    paths = [str(path) for path in OFFLINE_SHIMS]
    if os.environ.get("PYTHONPATH"):
        paths.append(os.environ["PYTHONPATH"])
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(paths))
    monkeypatch.setenv(
        "DEEPPAPERNOTE_HTTP_CASSETTE", str(tmp_path_factory.getbasetemp() / "offline-cassette.json")
    )
    monkeypatch.delenv("DEEPPAPERNOTE_HTTP_RECORD", raising=False)
    import extract_pdf_assets

    monkeypatch.setattr(extract_pdf_assets, "load_pytesseract", lambda: None)


def pytest_report_header() -> str:
    from common import fitz

    return f"PyMuPDF: {fitz.__version__ if fitz else 'unavailable'}"


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
