from __future__ import annotations

import json
import sys
from pathlib import Path

import check_environment
import pytest


def run_environment_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_api: dict,
) -> dict:
    output = tmp_path / "environment.json"
    monkeypatch.setattr(check_environment, "probe_zotero_local_api", lambda: dict(local_api))
    monkeypatch.setattr(check_environment, "find_obsidian_candidates", lambda: [])
    monkeypatch.setattr(check_environment, "find_local_zotero_hints", lambda: [])
    monkeypatch.setattr(
        check_environment,
        "runtime_config",
        lambda: {
            "obsidian_vault": "",
            "papers_dir": "Research/Papers",
            "output_dir": "tmp/DeepPaperNote",
            "workspace_output_dir": "DeepPaperNote_output",
        },
    )
    monkeypatch.setattr(sys, "argv", ["check_environment.py", "--output", str(output)])
    check_environment.main()
    return json.loads(output.read_text(encoding="utf-8"))


def test_environment_reports_available_zotero_local_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = run_environment_check(
        tmp_path,
        monkeypatch,
        {
            "status": "available",
            "reachable": True,
            "ready": True,
            "base_url": "http://127.0.0.1:23119/api",
            "api_version": "3",
            "schema_version": "37",
        },
    )

    assert payload["status"] == "ok"
    assert payload["tool_role"] == "maintenance"
    assert payload["zotero"]["local_api_available"] is True
    assert payload["zotero"]["local_api_status"] == "available"
    assert payload["zotero"]["local_api_version"] == "3"
    assert payload["zotero"]["local_api_schema_version"] == "37"
    assert payload["zotero"]["local_api"]["base_url"].startswith("http://127.0.0.1")
    assert payload["zotero"]["mcp_available_from_script"] is False
    assert payload["zotero"]["session_integration_checked_by_script"] is False


@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        ("unavailable", "zotero_not_running"),
        ("disabled", "zotero_api_disabled"),
        ("incompatible", "zotero_unsupported_version"),
    ],
)
def test_environment_keeps_full_report_when_zotero_is_not_ready(
    status: str,
    error_code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = run_environment_check(
        tmp_path,
        monkeypatch,
        {
            "status": status,
            "reachable": status != "unavailable",
            "ready": False,
            "base_url": "http://127.0.0.1:23119/api",
            "api_version": "",
            "schema_version": "",
            "error": {
                "code": error_code,
                "message": "fixture error",
                "retryable": status == "unavailable",
            },
        },
    )

    assert payload["status"] == "ok"
    assert payload["workspace_fallback"]["available"] is True
    assert payload["zotero"]["local_api_available"] is False
    assert payload["zotero"]["local_api_status"] == status
    assert payload["zotero"]["local_api"]["error"]["code"] == error_code
