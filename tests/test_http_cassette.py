"""The corpus cassette shim replays recorded responses and refuses everything else."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SHIM_DIR = Path(__file__).resolve().parent / "http_cassette"
PROBE = """
import json, sys, urllib.error, urllib.request
results = {}
for url in sys.argv[1:]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=1) as response:
            results[url] = ["ok", response.status, response.read().decode()]
    except urllib.error.HTTPError as exc:
        results[url] = ["http_error", exc.code, exc.read().decode()]
    except urllib.error.URLError as exc:
        results[url] = ["unreachable", 0, str(exc.reason)]
print(json.dumps(results))
"""


def probe(cassette: Path, *urls: str) -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": str(SHIM_DIR),
        "DEEPPAPERNOTE_HTTP_CASSETTE": str(cassette),
        "DEEPPAPERNOTE_HTTP_RECORD": "0",
    }
    result = subprocess.run(
        [sys.executable, "-c", PROBE, *urls], env=env, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_replay_serves_recorded_responses_and_lists_misses(tmp_path: Path) -> None:
    cassette = tmp_path / "paper.json"
    cassette.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "responses": {
                    "https://provider.test/ok": {"status": 200, "body": "{\"title\": \"T\"}"},
                    "https://provider.test/limited": {"status": 429, "body": "slow down"},
                },
            }
        ),
        encoding="utf-8",
    )

    results = probe(
        cassette,
        "https://provider.test/ok",
        "https://provider.test/limited",
        "https://provider.test/unrecorded",
    )

    assert results["https://provider.test/ok"] == ["ok", 200, "{\"title\": \"T\"}"]
    assert results["https://provider.test/limited"] == ["http_error", 429, "slow down"]
    assert results["https://provider.test/unrecorded"][0] == "unreachable"
    misses = cassette.with_suffix(".misses").read_text(encoding="utf-8").split()
    assert misses == ["https://provider.test/unrecorded"]
