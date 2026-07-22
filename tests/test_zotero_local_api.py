from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import pytest
from _zotero_local import (
    HttpResult,
    ZoteroLocalClient,
    ZoteroLocalError,
    _match_search_results,
    file_url_to_local_path,
    lookup_zotero_local,
    normalize_zotero_item,
    probe_zotero_local_api,
)


def json_result(
    payload: object, *, status: int = 200, headers: dict[str, str] | None = None
) -> HttpResult:
    return HttpResult(
        status=status,
        headers=headers or {},
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def text_result(payload: str, *, status: int = 200) -> HttpResult:
    return HttpResult(status=status, headers={}, body=payload.encode("utf-8"))


def root_result(*, api_version: str = "3") -> HttpResult:
    return json_result(
        {},
        headers={
            "Zotero-API-Version": api_version,
            "Zotero-Schema-Version": "37",
        },
    )


Route = HttpResult | Callable[[urllib.parse.SplitResult, dict[str, str], float], HttpResult]


def routed_transport(
    routes: dict[str, Route],
) -> tuple[Callable[..., HttpResult], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def transport(url: str, headers: dict[str, str], timeout: float) -> HttpResult:
        parsed = urllib.parse.urlsplit(url)
        calls.append(
            {
                "url": url,
                "path": parsed.path,
                "query": urllib.parse.parse_qs(parsed.query),
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        route = routes.get(parsed.path)
        if route is None:
            return text_result("missing fixture route", status=404)
        return route(parsed, headers, timeout) if callable(route) else route

    return transport, calls


def zotero_item(
    key: str = "PARENT01",
    *,
    title: str = "Attention Is All You Need",
    doi: str = "10.5555/Example",
    extra: str = "arXiv: 1706.03762",
    item_type: str = "journalArticle",
) -> dict[str, Any]:
    return {
        "key": key,
        "version": 7,
        "data": {
            "key": key,
            "itemType": item_type,
            "title": title,
            "creators": [
                {
                    "creatorType": "author",
                    "firstName": "Ashish",
                    "lastName": "Vaswani",
                },
                {"creatorType": "author", "name": "Example Research Lab"},
                {"creatorType": "editor", "firstName": "Ignored", "lastName": "Editor"},
            ],
            "DOI": doi,
            "date": "2017-06-12",
            "publicationTitle": "NeurIPS",
            "url": "https://example.test/paper",
            "extra": extra,
            "abstractNote": "A transformer paper.",
        },
    }


def zotero_attachment(
    key: str = "ATTACH01",
    *,
    parent_key: str = "PARENT01",
    filename: str = "paper.pdf",
    title: str = "Full Text PDF",
    link_mode: str = "imported_file",
    url: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "data": {
            "key": key,
            "itemType": "attachment",
            "parentItem": parent_key,
            "linkMode": link_mode,
            "title": title,
            "contentType": "application/pdf",
            "filename": filename,
            "url": url,
        },
    }


def base_routes() -> dict[str, Route]:
    return {"/api/": root_result()}


def test_client_rejects_non_loopback_base_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        ZoteroLocalClient(base_url="https://example.test/api")


def test_probe_checks_api_version_and_is_cached() -> None:
    transport, calls = routed_transport(base_routes())
    client = ZoteroLocalClient(transport=transport, timeout=0.25)

    first = client.probe()
    second = client.probe()

    assert first == second
    assert first == {
        "status": "available",
        "reachable": True,
        "ready": True,
        "base_url": "http://127.0.0.1:23119/api",
        "api_version": "3",
        "schema_version": "37",
    }
    assert len(calls) == 1
    assert calls[0]["headers"]["Zotero-API-Version"] == "3"
    assert calls[0]["headers"]["Accept"] == "application/json"
    assert "Authorization" not in calls[0]["headers"]
    assert calls[0]["timeout"] == 0.25


def test_probe_reports_disabled_and_incompatible_api() -> None:
    disabled_transport, _ = routed_transport({"/api/": text_result("", status=403)})
    disabled = probe_zotero_local_api(client=ZoteroLocalClient(transport=disabled_transport))
    assert disabled["status"] == "disabled"
    assert disabled["ready"] is False
    assert disabled["error"]["code"] == "zotero_api_disabled"

    old_transport, _ = routed_transport({"/api/": root_result(api_version="2")})
    incompatible = probe_zotero_local_api(client=ZoteroLocalClient(transport=old_transport))
    assert incompatible["status"] == "incompatible"
    assert incompatible["error"]["code"] == "zotero_unsupported_version"


def test_default_transport_does_not_follow_redirects_off_the_api_endpoint() -> None:
    outside_requested = False

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal outside_requested
            if self.path == "/api/":
                self.send_response(302)
                self.send_header("Location", "/outside")
                self.end_headers()
                return
            outside_requested = True
            self.send_response(200)
            self.send_header("Zotero-API-Version", "3")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = ZoteroLocalClient(
            base_url=f"http://127.0.0.1:{server.server_port}/api",
            timeout=1,
        )
        with pytest.raises(ZoteroLocalError) as exc_info:
            client.probe()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert exc_info.value.code == "zotero_invalid_response"
    assert exc_info.value.http_status == 302
    assert outside_requested is False


def test_search_encodes_unicode_and_doi_queries_without_api_key() -> None:
    routes = base_routes()
    routes["/api/users/0/items/top"] = json_result([])
    transport, calls = routed_transport(routes)
    client = ZoteroLocalClient(transport=transport)

    client.search_top_items("中文 标题", qmode="titleCreatorYear")
    client.search_top_items("10.1000/test(1)/part", qmode="everything")

    assert calls[1]["query"]["q"] == ["中文 标题"]
    assert calls[1]["query"]["qmode"] == ["titleCreatorYear"]
    assert calls[1]["query"]["itemType"] == ["-attachment"]
    assert "limit" not in calls[1]["query"]
    assert calls[2]["query"]["q"] == ["10.1000/test(1)/part"]
    assert "key" not in calls[1]["query"]


def test_client_rejects_invalid_json_and_wrong_search_shape() -> None:
    routes = base_routes()
    routes["/api/users/0/items/top"] = text_result("not-json")
    transport, _ = routed_transport(routes)
    with pytest.raises(ZoteroLocalError) as invalid_json:
        ZoteroLocalClient(transport=transport).search_top_items("paper", qmode="everything")
    assert invalid_json.value.code == "zotero_invalid_response"

    routes["/api/users/0/items/top"] = json_result({"items": []})
    transport, _ = routed_transport(routes)
    with pytest.raises(ZoteroLocalError) as wrong_shape:
        ZoteroLocalClient(transport=transport).search_top_items("paper", qmode="everything")
    assert wrong_shape.value.code == "zotero_invalid_response"


def test_normalize_item_maps_bibliographic_fields_without_editors() -> None:
    record = normalize_zotero_item(zotero_item())

    assert record["zotero_key"] == "PARENT01"
    assert record["title"] == "Attention Is All You Need"
    assert record["authors"] == ["Ashish Vaswani", "Example Research Lab"]
    assert record["doi"] == "10.5555/example"
    assert record["arxiv_id"] == "1706.03762"
    assert record["year"] == "2017"
    assert record["venue"] == "NeurIPS"
    assert record["abstract"] == "A transformer paper."
    assert record["source_type"] == "zotero"
    assert record["metadata_sources"] == ["zotero"]


def test_normalize_item_does_not_promote_local_file_url_to_source_url() -> None:
    item = zotero_item(doi="")
    item["data"]["url"] = "file:///tmp/untrusted.pdf"

    record = normalize_zotero_item(item)

    assert record["source_url"] == ""


def test_file_url_parser_handles_windows_unicode_spaces_and_literal_plus() -> None:
    url = "file:///C:/Users/%E5%BC%A0%E4%B8%89/Zotero/storage/ABC12345/My%20Paper+Notes.pdf"
    assert file_url_to_local_path(url, platform="nt") == (
        "C:\\Users\\张三\\Zotero\\storage\\ABC12345\\My Paper+Notes.pdf"
    )


def test_file_url_parser_handles_posix_and_rejects_remote_or_web_urls() -> None:
    assert file_url_to_local_path("file:///Users/name/My%20Paper.pdf", platform="posix") == (
        "/Users/name/My Paper.pdf"
    )
    assert file_url_to_local_path("file://localhost/Users/name/paper.pdf", platform="posix") == (
        "/Users/name/paper.pdf"
    )
    for unsafe in (
        "file://server/share/paper.pdf",
        "file:////server/share/paper.pdf",
        "file://localhost:99/tmp/paper.pdf",
        "https://example.test/paper.pdf",
        "file:///tmp/paper.pdf?download=1",
        "file:///tmp/bad\x00name.pdf",
        "file:///tmp/bad%00name.pdf",
        "file:///tmp/bad%FFname.pdf",
        "file://[invalid/paper.pdf",
    ):
        with pytest.raises(ZoteroLocalError) as exc:
            file_url_to_local_path(unsafe, platform="posix")
        assert exc.value.code == "zotero_unsafe_file_url"


def test_matcher_prefers_exact_doi_over_similar_titles() -> None:
    items = [
        zotero_item("PARENT01", doi="10.5555/exact"),
        zotero_item("PARENT02", title="Attention Is Almost All You Need", doi="10.5555/other"),
    ]
    match = _match_search_results(items, match_kind="doi", query="https://doi.org/10.5555/EXACT")
    assert match["status"] == "match"
    assert match["record"]["zotero_key"] == "PARENT01"


def test_matcher_rejects_duplicate_strong_identifier() -> None:
    items = [
        zotero_item("PARENT01", doi="10.5555/duplicate"),
        zotero_item("PARENT02", doi="10.5555/DUPLICATE"),
    ]
    match = _match_search_results(items, match_kind="doi", query="10.5555/duplicate")
    assert match == {
        "status": "ambiguous",
        "match_kind": "doi",
        "candidate_count": 2,
    }


def test_matcher_supports_nfkc_unicode_title_and_detects_ties() -> None:
    unique = _match_search_results(
        [zotero_item(title="深度学习：方法Ａ")],
        match_kind="title",
        query="深度学习:方法A",
    )
    assert unique["status"] == "match"

    tied = _match_search_results(
        [
            zotero_item("PARENT01", title="A Study of Reliable Agents"),
            zotero_item("PARENT02", title="A Study of Reliable Agents"),
        ],
        match_kind="title",
        query="A Study of Reliable Agents",
    )
    assert tied["status"] == "ambiguous"


def test_matcher_rejects_a_non_exact_title_without_independent_identity_evidence() -> None:
    match = _match_search_results(
        [zotero_item(title="Deep Learning for Dogs")],
        match_kind="title",
        query="Deep Learning for Cats",
    )

    assert match == {
        "status": "not_found",
        "match_kind": "title",
        "candidate_count": 0,
    }

    symbol_difference = _match_search_results(
        [zotero_item(title="Reliable C Agents")],
        match_kind="title",
        query="Reliable C++ Agents",
    )
    assert symbol_difference == {
        "status": "not_found",
        "match_kind": "title",
        "candidate_count": 0,
    }


def test_lookup_by_key_returns_parent_metadata_and_existing_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "论文 附件.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result(
        [zotero_attachment(filename=pdf_path.name)]
    )
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(pdf_path.as_uri())
    transport, calls = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["match_kind"] == "zotero_key"
    assert result["record"]["zotero_key"] == "PARENT01"
    assert result["record"]["zotero_attachment_key"] == "ATTACH01"
    assert result["record"]["local_pdf_path"] == str(pdf_path.resolve())
    assert result["record"]["paper_id"] == "doi:10.5555/example"
    assert result["record"]["identity_confidence"] == "high"
    assert [call["path"] for call in calls] == [
        "/api/",
        "/api/users/0/items/PARENT01",
        "/api/users/0/items/PARENT01/children",
        "/api/users/0/items/ATTACH01/file/view/url",
    ]


@pytest.mark.parametrize("title", ["research", "learning", "ResearcH"])
def test_lookup_does_not_treat_lowercase_or_mixed_case_title_as_item_key(title: str) -> None:
    routes = base_routes()
    routes["/api/users/0/items/top"] = json_result([])
    transport, calls = routed_transport(routes)

    result = lookup_zotero_local(
        title,
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "not_found"
    assert calls[1]["path"] == "/api/users/0/items/top"
    assert calls[1]["query"]["q"] == [title]


def test_lookup_by_attachment_key_resolves_bibliographic_parent(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    attachment = zotero_attachment()
    routes = base_routes()
    routes["/api/users/0/items/ATTACH01"] = json_result(attachment)
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result([])
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(pdf_path.as_uri())
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "ATTACH01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["zotero_key"] == "PARENT01"
    assert result["record"]["zotero_attachment_key"] == "ATTACH01"
    assert result["record"]["local_pdf_path"] == str(pdf_path.resolve())


def test_lookup_by_attachment_key_does_not_substitute_a_sibling_pdf(tmp_path: Path) -> None:
    sibling_path = tmp_path / "sibling.pdf"
    sibling_path.write_bytes(b"%PDF-1.4\n")
    selected = zotero_attachment("ATTACH01", filename="missing.pdf")
    sibling = zotero_attachment("ATTACH02", filename=sibling_path.name)
    routes = base_routes()
    routes["/api/users/0/items/ATTACH01"] = json_result(selected)
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result([selected, sibling])
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(
        (tmp_path / "missing.pdf").as_uri()
    )
    routes["/api/users/0/items/ATTACH02/file/view/url"] = text_result(sibling_path.as_uri())
    transport, calls = routed_transport(routes)

    result = lookup_zotero_local(
        "ATTACH01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["zotero_attachment_status"] == "unavailable"
    assert "local_pdf_path" not in result["record"]
    assert "/api/users/0/items/ATTACH02/file/view/url" not in {call["path"] for call in calls}


def test_lookup_keeps_identity_when_attachment_is_missing(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.pdf"
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result([zotero_attachment()])
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(missing_path.as_uri())
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["zotero_attachment_status"] == "unavailable"
    assert "local_pdf_path" not in result["record"]


def test_lookup_does_not_choose_between_equal_local_pdf_attachments(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result(
        [
            zotero_attachment("ATTACH01", filename=first.name),
            zotero_attachment("ATTACH02", filename=second.name),
        ]
    )
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(first.as_uri())
    routes["/api/users/0/items/ATTACH02/file/view/url"] = text_result(second.as_uri())
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["zotero_attachment_status"] == "ambiguous"
    assert "local_pdf_path" not in result["record"]


def test_lookup_returns_ambiguous_for_duplicate_local_doi() -> None:
    routes = base_routes()
    routes["/api/users/0/items/top"] = json_result(
        [
            zotero_item("PARENT01", doi="10.5555/duplicate"),
            zotero_item("PARENT02", doi="10.5555/duplicate"),
        ]
    )
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "10.5555/duplicate",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "ambiguous"
    assert result["candidate_count"] == 2


def test_lookup_checks_all_unpaginated_local_results_for_duplicates() -> None:
    items = [zotero_item("PARENT01", doi="10.5555/duplicate")]
    items.extend(
        zotero_item(f"OTHER{index:03d}", doi=f"10.5555/other-{index}") for index in range(2, 11)
    )
    items.append(zotero_item("PARENT11", doi="10.5555/duplicate"))
    routes = base_routes()
    routes["/api/users/0/items/top"] = json_result(items)
    transport, calls = routed_transport(routes)

    result = lookup_zotero_local(
        "10.5555/duplicate",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "ambiguous"
    assert result["candidate_count"] == 2
    assert "limit" not in calls[1]["query"]


def test_lookup_ignores_search_results_without_valid_item_keys() -> None:
    invalid = zotero_item("PARENT01", doi="10.5555/invalid")
    invalid["key"] = ""
    invalid["data"]["key"] = ""
    routes = base_routes()
    routes["/api/users/0/items/top"] = json_result([invalid])
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "10.5555/invalid",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "not_found"


def test_lookup_preserves_parent_metadata_when_children_endpoint_fails() -> None:
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = text_result("", status=500)
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["zotero_attachment_status"] == "unavailable"
    assert result["record"]["zotero_attachment_error"] == "zotero_server_error"


def test_lookup_preserves_parent_metadata_when_attachment_file_url_is_malformed() -> None:
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result([zotero_attachment()])
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(
        "file://[invalid/paper.pdf"
    )
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["title"] == "Attention Is All You Need"
    assert result["record"]["paper_id"] == "doi:10.5555/example"
    assert result["record"]["zotero_attachment_status"] == "unavailable"
    assert result["record"]["zotero_attachment_error"] == "zotero_unsafe_file_url"


def test_lookup_preserves_parent_identity_when_parent_url_is_malformed(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\ntrusted")
    parent = zotero_item()
    parent["data"]["url"] = "https://[invalid/paper"
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(parent)
    routes["/api/users/0/items/PARENT01/children"] = json_result([zotero_attachment()])
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(pdf_path.as_uri())
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["title"] == "Attention Is All You Need"
    assert result["record"]["paper_id"] == "doi:10.5555/example"
    assert result["record"]["source_url"] == "https://doi.org/10.5555/example"
    assert result["record"]["local_pdf_path"] == str(pdf_path.resolve())
    assert result["record"]["zotero_parent_url_error"] == "zotero_unsafe_file_url"


def test_lookup_preserves_parent_metadata_when_remote_attachment_url_is_malformed(
    tmp_path: Path,
) -> None:
    routes = base_routes()
    routes["/api/users/0/items/PARENT01"] = json_result(zotero_item())
    routes["/api/users/0/items/PARENT01/children"] = json_result(
        [zotero_attachment(url="https://[invalid/paper.pdf")]
    )
    routes["/api/users/0/items/ATTACH01/file/view/url"] = text_result(
        (tmp_path / "missing.pdf").as_uri()
    )
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "match"
    assert result["record"]["title"] == "Attention Is All You Need"
    assert result["record"]["paper_id"] == "doi:10.5555/example"
    assert result["record"]["zotero_attachment_status"] == "unavailable"
    assert result["record"]["zotero_attachment_error"] == "zotero_unsafe_file_url"


def test_lookup_reports_not_found_for_missing_key() -> None:
    routes = base_routes()
    routes["/api/users/0/items/MISSING1"] = text_result("", status=404)
    transport, _ = routed_transport(routes)

    result = lookup_zotero_local(
        "MISSING1",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "not_found"
    assert result["error"]["code"] == "zotero_item_not_found"


def test_lookup_rejects_group_select_link_instead_of_dropping_library_scope() -> None:
    transport, calls = routed_transport(base_routes())

    result = lookup_zotero_local(
        "zotero://select/groups/42/items/PARENT01",
        client=ZoteroLocalClient(transport=transport),
    )

    assert result["status"] == "error"
    assert result["error"]["code"] == "zotero_unsupported_library"
    assert [call["path"] for call in calls] == ["/api/"]
