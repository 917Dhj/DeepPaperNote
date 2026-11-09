"""Record or replay every HTTP response a pipeline script receives.

Put this directory on PYTHONPATH and set DEEPPAPERNOTE_HTTP_CASSETTE to a JSON file.
With DEEPPAPERNOTE_HTTP_RECORD=1 the script reaches the network and adds each response
to the cassette. Otherwise every response comes from the cassette, and a request that
was never recorded fails like an unreachable host and is listed in the cassette's
``.misses`` file, so a test can tell a stale cassette from a provider outage.
"""

from __future__ import annotations

import email.message
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

CASSETTE = os.environ.get("DEEPPAPERNOTE_HTTP_CASSETTE", "")
RECORD = os.environ.get("DEEPPAPERNOTE_HTTP_RECORD") == "1"
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _load(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": 1, "responses": {}}


def _save(path: Path, cassette: dict) -> None:
    cassette["responses"] = dict(sorted(cassette["responses"].items()))
    path.write_text(json.dumps(cassette, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _url(request: object) -> str:
    return request.full_url if isinstance(request, urllib.request.Request) else str(request)


class _Response(io.BytesIO):
    def __init__(self, url: str, status: int, body: bytes) -> None:
        super().__init__(body)
        self.url = url
        self.status = status
        self.headers = email.message.Message()

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status


def _replay(url: str, entry: dict) -> _Response:
    body = entry["body"].encode("utf-8")
    if entry["status"] >= 400:
        raise urllib.error.HTTPError(url, entry["status"], "recorded error", None, io.BytesIO(body))
    return _Response(url, entry["status"], body)


def _install(path: Path) -> None:
    real_urlopen = urllib.request.urlopen

    def urlopen(request, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        url = _url(request)
        cassette = _load(path)
        if not RECORD:
            if url in cassette["responses"]:
                return _replay(url, cassette["responses"][url])
            with path.with_suffix(".misses").open("a", encoding="utf-8") as misses:
                misses.write(url + "\n")
            raise urllib.error.URLError(f"not in cassette: {url}")
        for attempt in range(4):
            try:
                with real_urlopen(request, *args, **kwargs) as response:
                    entry = {"status": response.status, "body": response.read().decode("utf-8")}
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt < 3:
                    time.sleep(5 * (attempt + 1))
                    continue
                entry = {"status": exc.code, "body": exc.read().decode("utf-8", "replace")}
            break
        cassette["responses"][url] = entry
        _save(path, cassette)
        return _replay(url, entry)

    urllib.request.urlopen = urlopen


if CASSETTE:
    _install(Path(CASSETTE))
