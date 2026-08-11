"""Cache semantics of the TrueMoney client (parity with the Go version)."""

from types import SimpleNamespace

import pytest

from app.truemoney import Client, _is_success

SUCCESS_BODY = {
    "status": {"code": "SUCCESS", "message": "success"},
    "data": {"mobile": "0812345678"},
}
ERROR_ENVELOPE = {
    "status": {"code": "TARGET_USER_NOT_FOUND", "message": "not found"}
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    @property
    def content(self):
        import json

        return json.dumps(self._payload).encode()


def make_client(posts):
    client = Client()
    client._session = SimpleNamespace(post=posts)  # stub the network layer
    return client


def test_success_is_cached_and_replayed():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(SUCCESS_BODY)

    client = make_client(posts)

    assert client.redeem("ABC123", "0812345678") == SUCCESS_BODY
    assert client.redeem("ABC123", "0812345678") == SUCCESS_BODY
    assert len(calls) == 1, "second redeem must hit the cache"


def test_different_mobile_is_a_different_key():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(SUCCESS_BODY)

    client = make_client(posts)

    client.redeem("ABC123", "0812345678")
    client.redeem("ABC123", "0899999999")
    assert len(calls) == 2


def test_error_envelope_is_not_cached():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(ERROR_ENVELOPE, status_code=400)

    client = make_client(posts)

    client.redeem("ABC123", "0812345678")
    client.redeem("ABC123", "0812345678")
    assert len(calls) == 2, "error answers must always go upstream"


def test_ttl_expiry_re_probes():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(SUCCESS_BODY)

    client = make_client(posts)
    client._cache_ttl = 0.05  # 50 ms

    client.redeem("ABC123", "0812345678")

    import time

    time.sleep(0.06)
    client.redeem("ABC123", "0812345678")
    assert len(calls) == 2, "expired cache must miss and call upstream"


def test_lru_eviction_at_capacity():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(SUCCESS_BODY)

    client = make_client(posts)
    client._cache_size = 2

    client.redeem("AAAA", "0812345678")
    client.redeem("BBBB", "0812345678")
    client.redeem("CCCC", "0812345678")  # evicts AAAA (oldest insertion)
    assert len(calls) == 3

    client.redeem("AAAA", "0812345678")
    assert len(calls) == 4, "evicted key must go upstream again"


def test_normalization_before_cache_key():
    calls = []

    def posts(url, **kwargs):
        calls.append(url)
        return FakeResponse(SUCCESS_BODY)

    client = make_client(posts)

    # Same normalized value via a URL and a raw code hits the same key.
    client.redeem("  ABC123  ", "081-234-5678")
    client.redeem("ABC123", "0812345678")
    assert len(calls) == 1


def test_is_success():
    assert _is_success(SUCCESS_BODY) is True
    assert _is_success(ERROR_ENVELOPE) is False
    assert _is_success({"status": "SUCCESS"}) is False  # non-dict status
    assert _is_success({"data": {}}) is False