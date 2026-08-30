from dataclasses import dataclass

from deadbot.deadnet import (
    DeadnetConfig,
    DeadnetResearchAdapter,
    EntityReadRequest,
    EntitySearchRequest,
    EntityType,
    HttpResponse,
    ResultState,
)


@dataclass
class FakeTransport:
    response: HttpResponse
    calls: list[tuple[str, dict, float]] | None = None

    def get(self, url, *, params, timeout):
        if self.calls is not None:
            self.calls.append((url, dict(params), timeout))
        return self.response


def test_search_is_entity_scoped_and_returns_metadata_only():
    transport = FakeTransport(HttpResponse(200, {"results": [{"id": "bird-song", "title": "Bird Song", "body": "secret"}]}), [])
    result = DeadnetResearchAdapter(transport).search(EntitySearchRequest("Bird Song", EntityType.SONG))

    assert result.state == ResultState.OK
    assert result.records[0].title == "Bird Song"
    assert not hasattr(result.records[0], "body")
    assert transport.calls[0][0] == "https://www.dead.net/search"
    assert transport.calls[0][1]["type"] == "song"


def test_read_rejects_path_escape_without_transport_call():
    transport = FakeTransport(HttpResponse(200, {}), [])
    result = DeadnetResearchAdapter(transport).read(EntityReadRequest(EntityType.SONG, "../secrets"))
    assert result.state == ResultState.INVALID
    assert transport.calls == []


def test_configured_path_allowlist_blocks_unapproved_entity():
    transport = FakeTransport(HttpResponse(200, {}), [])
    config = DeadnetConfig(allowed_paths=("/search",), search_path="/search")
    result = DeadnetResearchAdapter(transport, config).read(EntityReadRequest(EntityType.SONG, "bird-song"))
    assert result.state == ResultState.BLOCKED
    assert transport.calls == []


def test_http_failure_is_explicit_and_does_not_raise():
    result = DeadnetResearchAdapter(FakeTransport(HttpResponse(503, {}))).search(EntitySearchRequest("Garcia", EntityType.PERSON))
    assert result.state == ResultState.UNAVAILABLE
    assert result.records == ()


def test_unapproved_metadata_url_is_not_returned_and_marks_partial():
    transport = FakeTransport(HttpResponse(200, {"results": [{"id": "x", "title": "X", "url": "https://evil.example/x"}]}))
    result = DeadnetResearchAdapter(transport).search(EntitySearchRequest("X", EntityType.SONG))
    assert result.state == ResultState.PARTIAL
    assert result.records[0].url is None


def test_base_url_must_be_allowed_https_host():
    try:
        DeadnetConfig(base_url="https://example.com")
    except ValueError as error:
        assert "allowed Dead.net host" in str(error)
    else:
        raise AssertionError("unapproved host should be rejected")


def test_deadcast_read_uses_only_allowlisted_metadata_path():
    transport = FakeTransport(
        HttpResponse(200, {"results": [{"id": "episode-1", "title": "Deadcast: Veneta", "description": "A" * 1000}]}),
        [],
    )
    config = DeadnetConfig(allowed_paths=("/deadcast",), search_path="/deadcast", max_results=1)
    result = DeadnetResearchAdapter(transport, config).read(
        EntityReadRequest(EntityType.DEADCAST, "episode-1")
    )
    assert result.state == ResultState.OK
    assert transport.calls[0][0] == "https://www.dead.net/deadcast/episode-1"
    assert len(result.records[0].description) == 280


def test_read_rejects_encoded_or_embedded_url_identifiers():
    transport = FakeTransport(HttpResponse(200, {}), [])
    adapter = DeadnetResearchAdapter(transport)
    for identifier in ("episode%2Fsecret", "https://evil.example/x", "episode#fragment"):
        result = adapter.read(EntityReadRequest(EntityType.DEADCAST, identifier))
        assert result.state == ResultState.INVALID
    assert transport.calls == []
