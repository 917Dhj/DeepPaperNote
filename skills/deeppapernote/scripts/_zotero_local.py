#!/usr/bin/env python3
"""Read-only client and matching helpers for Zotero's desktop Local API."""

from __future__ import annotations

import json
import os
import re
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping

from common import (
    DEFAULT_USER_AGENT,
    apply_identity_confidence,
    extract_arxiv_id,
    extract_doi,
    infer_source_type,
    normalize_whitespace,
    paper_id_for_record,
)

ZOTERO_LOCAL_BASE_URL = "http://127.0.0.1:23119/api"
ZOTERO_API_VERSION = "3"
DEFAULT_TIMEOUT_SECONDS = 1.5
MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FILE_URL_BYTES = 16 * 1024
ZOTERO_ITEM_KEY_PATTERN = re.compile(r"^[A-Z0-9]{8}$")
ZOTERO_SELECT_KEY_PATTERN = re.compile(
    r"^zotero://select/library/items/([A-Z0-9]{8})$",
    flags=re.IGNORECASE,
)
ZOTERO_GROUP_SELECT_PATTERN = re.compile(
    r"^zotero://select/groups/\d+/items/[A-Z0-9]{8}$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class HttpResult:
    """Small transport-neutral HTTP response used by tests and the stdlib client."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class ZoteroLocalError(RuntimeError):
    """Stable error contract for Local API failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        return payload


Transport = Callable[[str, dict[str, str], float], HttpResult]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep every Local API transport request on the validated loopback endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _read_limited(response: Any, limit: int) -> bytes:
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ZoteroLocalError(
            "zotero_invalid_response",
            "Zotero Local API returned an unexpectedly large response.",
        )
    return body


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> HttpResult:
    # Local library queries should never inherit a corporate/system HTTP proxy.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResult(
                status=int(getattr(response, "status", 200)),
                headers=_normalized_headers(response.headers),
                body=_read_limited(response, MAX_JSON_RESPONSE_BYTES),
            )
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = _read_limited(exc, MAX_JSON_RESPONSE_BYTES)
        except Exception:
            pass
        return HttpResult(
            status=int(exc.code),
            headers=_normalized_headers(exc.headers or {}),
            body=body,
        )
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise ZoteroLocalError(
                "zotero_timeout",
                "Timed out while connecting to the Zotero Local API.",
                retryable=True,
            ) from exc
        raise ZoteroLocalError(
            "zotero_not_running",
            "Could not connect to the Zotero Local API on this computer.",
            retryable=True,
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ZoteroLocalError(
            "zotero_timeout",
            "Timed out while connecting to the Zotero Local API.",
            retryable=True,
        ) from exc
    except OSError as exc:
        raise ZoteroLocalError(
            "zotero_not_running",
            "Could not connect to the Zotero Local API on this computer.",
            retryable=True,
        ) from exc


def _validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url.rstrip("/"))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/api"
    ):
        raise ValueError("Zotero Local API base URL must be a loopback HTTP /api endpoint.")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _error_for_http_status(status: int) -> ZoteroLocalError:
    if status == 400:
        return ZoteroLocalError(
            "zotero_bad_request",
            "Zotero Local API rejected the request.",
            http_status=status,
        )
    if status == 403:
        return ZoteroLocalError(
            "zotero_api_disabled",
            "Zotero Local API access is disabled in Zotero settings.",
            http_status=status,
        )
    if status == 404:
        return ZoteroLocalError(
            "zotero_item_not_found",
            "The requested Zotero item was not found.",
            http_status=status,
        )
    if status == 501:
        return ZoteroLocalError(
            "zotero_unsupported_version",
            "This Zotero installation does not support the requested Local API version.",
            http_status=status,
        )
    if status >= 500:
        return ZoteroLocalError(
            "zotero_server_error",
            "Zotero Local API returned a server error.",
            http_status=status,
            retryable=True,
        )
    return ZoteroLocalError(
        "zotero_invalid_response",
        f"Zotero Local API returned unexpected HTTP status {status}.",
        http_status=status,
    )


class ZoteroLocalClient:
    """Minimal read-only Zotero Local API v3 client."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: Transport | None = None,
        base_url: str = ZOTERO_LOCAL_BASE_URL,
    ) -> None:
        self.timeout = timeout
        self.transport = transport or _default_transport
        self.base_url = _validate_base_url(base_url)
        self._probe_result: dict[str, Any] | None = None

    def _url(self, path: str = "", params: Mapping[str, Any] | None = None) -> str:
        url = f"{self.base_url}/{path.lstrip('/')}" if path else f"{self.base_url}/"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def _request(
        self,
        path: str = "",
        *,
        params: Mapping[str, Any] | None = None,
        accept: str = "application/json",
        max_bytes: int = MAX_JSON_RESPONSE_BYTES,
    ) -> HttpResult:
        headers = {
            "Accept": accept,
            "User-Agent": DEFAULT_USER_AGENT,
            "Zotero-API-Version": ZOTERO_API_VERSION,
        }
        result = self.transport(self._url(path, params), headers, self.timeout)
        if not 200 <= result.status < 300:
            raise _error_for_http_status(result.status)
        if len(result.body) > max_bytes:
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero Local API returned an unexpectedly large response.",
            )
        return result

    def probe(self) -> dict[str, Any]:
        if self._probe_result is not None:
            return dict(self._probe_result)
        result = self._request()
        headers = _normalized_headers(result.headers)
        api_version = normalize_whitespace(headers.get("zotero-api-version", ""))
        if api_version != ZOTERO_API_VERSION:
            raise ZoteroLocalError(
                "zotero_unsupported_version",
                "Zotero Local API did not report compatible API version 3.",
            )
        self._probe_result = {
            "status": "available",
            "reachable": True,
            "ready": True,
            "base_url": self.base_url,
            "api_version": api_version,
            "schema_version": normalize_whitespace(headers.get("zotero-schema-version", "")),
        }
        return dict(self._probe_result)

    def _ensure_ready(self) -> None:
        if self._probe_result is None:
            self.probe()

    def _request_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        self._ensure_ready()
        result = self._request(path, params=params)
        try:
            return json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero Local API returned invalid JSON.",
            ) from exc

    def get_item(self, item_key: str) -> dict[str, Any]:
        key = normalize_whitespace(item_key).upper()
        if not ZOTERO_ITEM_KEY_PATTERN.fullmatch(key):
            raise ValueError("Zotero item keys must contain exactly eight letters or digits.")
        payload = self._request_json(
            f"users/0/items/{key}",
            params={"format": "json", "include": "data"},
        )
        if not isinstance(payload, dict):
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero item response was not a JSON object.",
            )
        return payload

    def search_top_items(
        self,
        query: str,
        *,
        qmode: str,
    ) -> list[dict[str, Any]]:
        if qmode not in {"everything", "titleCreatorYear"}:
            raise ValueError("Unsupported Zotero quick-search mode.")
        payload = self._request_json(
            "users/0/items/top",
            params={
                "format": "json",
                "include": "data",
                "itemType": "-attachment",
                "q": query,
                "qmode": qmode,
            },
        )
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero search response was not a JSON item list.",
            )
        return payload

    def get_children(self, parent_key: str) -> list[dict[str, Any]]:
        key = normalize_whitespace(parent_key).upper()
        if not ZOTERO_ITEM_KEY_PATTERN.fullmatch(key):
            raise ValueError("Zotero item keys must contain exactly eight letters or digits.")
        payload = self._request_json(
            f"users/0/items/{key}/children",
            params={"format": "json", "include": "data"},
        )
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero children response was not a JSON item list.",
            )
        return payload

    def get_attachment_file_url(self, attachment_key: str) -> str:
        key = normalize_whitespace(attachment_key).upper()
        if not ZOTERO_ITEM_KEY_PATTERN.fullmatch(key):
            raise ValueError("Zotero item keys must contain exactly eight letters or digits.")
        self._ensure_ready()
        result = self._request(
            f"users/0/items/{key}/file/view/url",
            accept="text/plain",
            max_bytes=MAX_FILE_URL_BYTES,
        )
        try:
            return result.body.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ZoteroLocalError(
                "zotero_invalid_response",
                "Zotero attachment URL was not UTF-8 text.",
            ) from exc


def _item_data(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = raw.get("data", {})
    return dict(data) if isinstance(data, dict) else {}


def zotero_item_key(raw: Mapping[str, Any]) -> str:
    data = _item_data(raw)
    return normalize_whitespace(str(raw.get("key") or data.get("key") or "")).upper()


def _creator_name(creator: Mapping[str, Any]) -> str:
    corporate = normalize_whitespace(str(creator.get("name", "")))
    if corporate:
        return corporate
    return normalize_whitespace(f"{creator.get('firstName', '')} {creator.get('lastName', '')}")


def _publication_year(value: str) -> str:
    match = re.search(r"(?<!\d)((?:18|19|20|21)\d{2})(?!\d)", value or "")
    return match.group(1) if match else ""


def normalize_zotero_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map a Zotero item wrapper into DeepPaperNote's metadata vocabulary."""

    data = _item_data(raw)
    item_type = normalize_whitespace(str(data.get("itemType", "")))
    key = zotero_item_key(raw)
    authors: list[str] = []
    for creator in data.get("creators", []) or []:
        if not isinstance(creator, dict):
            continue
        if creator.get("creatorType") not in {"author", "bookAuthor"}:
            continue
        name = _creator_name(creator)
        if name and name not in authors:
            authors.append(name)

    doi = (extract_doi(str(data.get("DOI", ""))) or "").lower()
    arxiv_text = " ".join(
        str(data.get(field, "")) for field in ("archiveLocation", "extra", "url", "DOI")
    )
    arxiv_id = extract_arxiv_id(arxiv_text) or ""
    venue = next(
        (
            normalize_whitespace(str(data.get(field, "")))
            for field in (
                "publicationTitle",
                "conferenceName",
                "proceedingsTitle",
                "bookTitle",
                "websiteTitle",
                "repository",
                "publisher",
            )
            if normalize_whitespace(str(data.get(field, "")))
        ),
        "",
    )
    source_url = normalize_whitespace(str(data.get("url", "")))
    if urllib.parse.urlsplit(source_url).scheme.lower() not in {"http", "https"}:
        source_url = ""
    if not source_url and doi:
        source_url = f"https://doi.org/{doi}"

    record: dict[str, Any] = {
        "status": "ok",
        "source_type": "zotero",
        "metadata_sources": ["zotero"],
        "zotero_key": key,
        "zotero_item_type": item_type,
        "title": normalize_whitespace(str(data.get("title", ""))),
        "authors": authors,
        "affiliations": [],
        "abstract": normalize_whitespace(str(data.get("abstractNote", ""))),
        "venue": venue,
        "year": _publication_year(str(data.get("date", ""))),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "source_url": source_url,
    }
    version = raw.get("version")
    if version not in (None, ""):
        record["zotero_version"] = version
    return record


def normalize_zotero_attachment(raw: Mapping[str, Any]) -> dict[str, Any]:
    data = _item_data(raw)
    return {
        "key": zotero_item_key(raw),
        "parent_key": normalize_whitespace(str(data.get("parentItem", ""))).upper(),
        "item_type": normalize_whitespace(str(data.get("itemType", ""))),
        "link_mode": normalize_whitespace(str(data.get("linkMode", ""))),
        "title": normalize_whitespace(str(data.get("title", ""))),
        "content_type": normalize_whitespace(str(data.get("contentType", ""))).lower(),
        "filename": normalize_whitespace(str(data.get("filename", ""))),
        "url": normalize_whitespace(str(data.get("url", ""))),
    }


def is_pdf_attachment(attachment: Mapping[str, Any]) -> bool:
    if attachment.get("item_type") != "attachment":
        return False
    if attachment.get("link_mode") == "linked_url":
        return False
    return attachment.get("content_type") == "application/pdf" or any(
        str(attachment.get(field, "")).lower().endswith(".pdf") for field in ("filename", "title")
    )


def file_url_to_local_path(raw_url: str, *, platform: str | None = None) -> str:
    """Convert a safe local ``file://`` URL without touching the filesystem."""

    value = (raw_url or "").strip()
    if not value or "\x00" in value:
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero returned an empty or invalid attachment file URL.",
        )
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero attachment URL contained an invalid network location.",
        ) from exc
    if (
        parsed.scheme.lower() != "file"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname not in {None, "", "localhost"}
    ):
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero attachment URL did not identify a local file.",
        )
    try:
        decoded = urllib.parse.unquote(parsed.path, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero attachment URL contained invalid UTF-8 path data.",
        ) from exc
    if "\x00" in decoded:
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero attachment URL contained an invalid path.",
        )
    target_platform = platform or os.name
    if target_platform == "nt":
        windows_path = decoded.replace("/", "\\")
        if windows_path.startswith("\\\\"):
            raise ZoteroLocalError(
                "zotero_unsafe_file_url",
                "Zotero attachment URL identified a remote UNC path.",
            )
        if re.match(r"^/[A-Za-z]:/", decoded):
            decoded = decoded[1:]
        path = PureWindowsPath(decoded.replace("/", "\\"))
    else:
        if decoded.startswith("//"):
            raise ZoteroLocalError(
                "zotero_unsafe_file_url",
                "Zotero attachment URL identified an ambiguous network path.",
            )
        path = PurePosixPath(decoded)
    if not path.is_absolute():
        raise ZoteroLocalError(
            "zotero_unsafe_file_url",
            "Zotero attachment URL was not an absolute local path.",
        )
    return str(path)


def existing_pdf_from_file_url(raw_url: str) -> str:
    path_value = file_url_to_local_path(raw_url)
    try:
        path = Path(path_value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return ""
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return ""
    return str(path)


def normalize_lookup_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", normalize_whitespace(title)).casefold()
    normalized = "".join(char if char.isalnum() or char.isspace() else " " for char in normalized)
    return normalize_whitespace(normalized)


def _match_search_results(
    raw_items: list[dict[str, Any]],
    *,
    match_kind: str,
    query: str,
) -> dict[str, Any]:
    candidates = [
        normalize_zotero_item(item)
        for item in raw_items
        if _item_data(item).get("itemType") not in {"", "attachment", "note", "annotation"}
        and ZOTERO_ITEM_KEY_PATTERN.fullmatch(zotero_item_key(item))
    ]
    if match_kind == "doi":
        expected = (extract_doi(query) or "").lower()
        matches = [item for item in candidates if item.get("doi", "").lower() == expected]
    elif match_kind == "arxiv_id":
        expected = extract_arxiv_id(query) or ""
        matches = [item for item in candidates if item.get("arxiv_id") == expected]
    else:
        expected_title = normalize_lookup_title(query)
        matches = [
            item
            for item in candidates
            if normalize_lookup_title(str(item.get("title", ""))) == expected_title
        ]
    if not matches:
        return {"status": "not_found", "match_kind": match_kind, "candidate_count": 0}
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "match_kind": match_kind,
            "candidate_count": len(matches),
        }
    return {"status": "match", "match_kind": match_kind, "record": matches[0]}


def _attachment_priority(attachment: Mapping[str, Any]) -> tuple[int, int, int, int]:
    label = f"{attachment.get('title', '')} {attachment.get('filename', '')}".casefold()
    supplementary = any(
        term in label
        for term in ("supplementary", "supplemental", "supporting information", "appendix")
    )
    link_mode_score = {
        "imported_file": 3,
        "linked_file": 2,
        "imported_url": 1,
    }.get(str(attachment.get("link_mode", "")), 0)
    explicit_pdf = int(attachment.get("content_type") == "application/pdf")
    full_text = int("full text" in label or "pdf" in label)
    return (int(not supplementary), link_mode_score, explicit_pdf, full_text)


def _attach_local_pdf(
    client: ZoteroLocalClient,
    record: dict[str, Any],
    raw_children: list[dict[str, Any]],
    *,
    preferred_attachment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parent_key = str(record.get("zotero_key", ""))
    raw_candidates = list(raw_children)
    if preferred_attachment and zotero_item_key(preferred_attachment) not in {
        zotero_item_key(item) for item in raw_candidates
    }:
        raw_candidates.append(dict(preferred_attachment))
    candidates = [normalize_zotero_attachment(item) for item in raw_candidates]
    candidates = [
        item
        for item in candidates
        if is_pdf_attachment(item)
        and item.get("parent_key") == parent_key
        and ZOTERO_ITEM_KEY_PATTERN.fullmatch(str(item.get("key", "")))
    ]
    preferred_key = zotero_item_key(preferred_attachment or {})
    if preferred_key:
        candidates = [item for item in candidates if item.get("key") == preferred_key]
    if not candidates:
        record["zotero_attachment_status"] = "not_found"
        return record

    local_candidates: list[tuple[dict[str, Any], str]] = []
    attachment_errors: list[str] = []
    for attachment in sorted(candidates, key=lambda item: str(item.get("key", ""))):
        try:
            file_url = client.get_attachment_file_url(str(attachment.get("key", "")))
            local_path = existing_pdf_from_file_url(file_url)
        except ZoteroLocalError as exc:
            attachment_errors.append(exc.code)
            continue
        if local_path:
            local_candidates.append((attachment, local_path))

    if preferred_key:
        preferred = [pair for pair in local_candidates if pair[0].get("key") == preferred_key]
        if preferred:
            local_candidates = preferred
    if local_candidates:
        best_priority = max(_attachment_priority(item) for item, _ in local_candidates)
        best = [pair for pair in local_candidates if _attachment_priority(pair[0]) == best_priority]
        distinct_paths = {path for _, path in best}
        if len(distinct_paths) == 1:
            attachment, local_path = best[0]
            record["zotero_attachment_status"] = "available"
            record["zotero_attachment_key"] = attachment["key"]
            record["zotero_attachment_filename"] = attachment["filename"]
            record["local_pdf_path"] = local_path
            return record
        record["zotero_attachment_status"] = "ambiguous"
        return record

    pdf_urls = sorted(
        {
            str(item.get("url", ""))
            for item in candidates
            if urllib.parse.urlsplit(str(item.get("url", ""))).scheme == "https"
            and urllib.parse.urlsplit(str(item.get("url", ""))).path.lower().endswith(".pdf")
        }
    )
    if len(pdf_urls) == 1:
        record["pdf_url"] = pdf_urls[0]
        record["zotero_attachment_status"] = "remote_only"
    else:
        record["zotero_attachment_status"] = "unavailable"
    if attachment_errors:
        record["zotero_attachment_error"] = attachment_errors[0]
    return record


def _zotero_key_from_reference(reference: str, *, reference_type: str) -> str:
    value = normalize_whitespace(reference)
    if ZOTERO_GROUP_SELECT_PATTERN.fullmatch(value):
        raise ZoteroLocalError(
            "zotero_unsupported_library",
            "Zotero group-library select links are not supported by the local user-library client.",
        )
    match = ZOTERO_SELECT_KEY_PATTERN.fullmatch(value)
    if match:
        return match.group(1).upper()
    if reference_type == "zotero_key" or ZOTERO_ITEM_KEY_PATTERN.fullmatch(value):
        return value.upper()
    return ""


def _resolve_parent_item(
    client: ZoteroLocalClient,
    raw_item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    data = _item_data(raw_item)
    if data.get("itemType") != "attachment":
        return raw_item, None
    parent_key = normalize_whitespace(str(data.get("parentItem", ""))).upper()
    if not ZOTERO_ITEM_KEY_PATTERN.fullmatch(parent_key):
        raise ZoteroLocalError(
            "zotero_item_not_bibliographic",
            "The Zotero attachment is not linked to a bibliographic parent item.",
        )
    return client.get_item(parent_key), raw_item


def lookup_zotero_local(
    reference: str,
    *,
    reference_type: str = "",
    client: ZoteroLocalClient | None = None,
) -> dict[str, Any]:
    """Resolve one scalar reference against the local Zotero library."""

    local_client = client or ZoteroLocalClient()
    source_type = reference_type or infer_source_type(reference)
    try:
        probe = local_client.probe()
        explicit_key = _zotero_key_from_reference(reference, reference_type=source_type)
        preferred_attachment: dict[str, Any] | None = None
        if explicit_key:
            raw_item = local_client.get_item(explicit_key)
            if zotero_item_key(raw_item) != explicit_key:
                raise ZoteroLocalError(
                    "zotero_invalid_response",
                    "Zotero returned a different item than the requested key.",
                )
            raw_parent, preferred_attachment = _resolve_parent_item(local_client, raw_item)
            record = normalize_zotero_item(raw_parent)
            parent_key = str(record.get("zotero_key", ""))
            if record.get("zotero_item_type") in {"attachment", "note", "annotation", ""}:
                raise ZoteroLocalError(
                    "zotero_item_not_bibliographic",
                    "The Zotero item is not a bibliographic parent item.",
                )
            if not ZOTERO_ITEM_KEY_PATTERN.fullmatch(parent_key):
                raise ZoteroLocalError(
                    "zotero_invalid_response",
                    "Zotero bibliographic item did not contain a valid item key.",
                )
            match_kind = "zotero_key"
        else:
            doi = extract_doi(reference) or ""
            arxiv_id = extract_arxiv_id(reference) or ""
            if source_type in {"doi", "doi_url"} or doi:
                match_kind = "doi"
                query = doi
                qmode = "everything"
            elif source_type in {"arxiv_id", "arxiv_url"} or arxiv_id:
                match_kind = "arxiv_id"
                query = arxiv_id
                qmode = "everything"
            elif source_type in {"title", "title_query"}:
                match_kind = "title"
                query = reference
                qmode = "titleCreatorYear"
            else:
                return {
                    "status": "not_found",
                    "match_kind": "unsupported_reference",
                    "probe": probe,
                }
            raw_items = local_client.search_top_items(query, qmode=qmode)
            match = _match_search_results(raw_items, match_kind=match_kind, query=query)
            if match["status"] != "match":
                match["probe"] = probe
                return match
            record = dict(match["record"])

        try:
            raw_children = local_client.get_children(str(record.get("zotero_key", "")))
            record = _attach_local_pdf(
                local_client,
                record,
                raw_children,
                preferred_attachment=preferred_attachment,
            )
        except ZoteroLocalError as exc:
            record["zotero_attachment_status"] = "unavailable"
            record["zotero_attachment_error"] = exc.code
        record["paper_id"] = paper_id_for_record(record)
        record = apply_identity_confidence(record)
        return {
            "status": "match",
            "match_kind": match_kind,
            "record": record,
            "probe": probe,
        }
    except ZoteroLocalError as exc:
        if exc.code == "zotero_item_not_found":
            return {
                "status": "not_found",
                "match_kind": source_type,
                "error": exc.as_dict(),
            }
        return {
            "status": "error",
            "match_kind": source_type,
            "error": exc.as_dict(),
        }


def probe_zotero_local_api(
    *,
    client: ZoteroLocalClient | None = None,
) -> dict[str, Any]:
    """Return a non-raising environment diagnostic for the Local API."""

    local_client = client or ZoteroLocalClient()
    try:
        return local_client.probe()
    except ZoteroLocalError as exc:
        if exc.code == "zotero_api_disabled":
            status = "disabled"
        elif exc.code == "zotero_unsupported_version":
            status = "incompatible"
        elif exc.code in {"zotero_not_running", "zotero_timeout", "zotero_server_error"}:
            status = "unavailable"
        else:
            status = "error"
        return {
            "status": status,
            "reachable": exc.code not in {"zotero_not_running", "zotero_timeout"},
            "ready": False,
            "base_url": local_client.base_url,
            "api_version": "",
            "schema_version": "",
            "error": exc.as_dict(),
        }
