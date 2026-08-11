"""HTTP contract tests via FastAPI TestClient with a stubbed client.

Mirrors test/app.e2e-spec.ts from the NestJS port. The real curl_cffi
session is never created; app.state.tm is swapped for a fake so no
network request leaves the machine.
"""

import urllib.parse

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.truemoney import TrueMoneyError, ValidationError

SUCCESS_ENVELOPE = {"status": {"code": "SUCCESS"}, "data": {"amount": 50}}


class FakeClient:
    def __init__(self, *, result=None, exc=None) -> None:
        self.result = result if result is not None else SUCCESS_ENVELOPE
        self.exc = exc
        self.calls: list[tuple[str, str]] = []

    def close(self) -> None:
        pass

    def redeem(self, voucher: str, mobile: str):
        self.calls.append((voucher, mobile))
        if self.exc is not None:
            raise self.exc
        return self.result


@pytest.fixture()
def client():
    app.state.tm = FakeClient()
    # No context manager: lifespan (which would create a real curl_cffi
    # client) is skipped, so tests are offline.
    return TestClient(app)


def test_status_is_a_200_liveness_probe(client: TestClient) -> None:
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.content == b""


def test_post_status_works_too(client: TestClient) -> None:
    resp = client.post("/status")
    assert resp.status_code == 200


def test_root_returns_service_info(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "truemoney-voucher"
    assert any("truemoney" in r for r in body["routes"])


def test_unknown_paths_are_json_404(client: TestClient) -> None:
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.json() == {"code": 404, "message": "Not Found"}


def test_unknown_methods_are_json_404(client: TestClient) -> None:
    resp = client.put("/truemoney/ABCD1234EFGH/0812345678")
    assert resp.status_code == 404
    assert resp.json() == {"code": 404, "message": "Not Found"}


def test_invalid_input_answers_200_with_code_400(client: TestClient) -> None:
    app.state.tm = FakeClient(exc=ValidationError("bad input"))
    resp = client.get("/truemoney/ABCD1234EFGH/123")
    assert resp.status_code == 200
    assert resp.json() == {"code": 400, "message": "Bad Request"}


def test_upstream_failures_answer_200_with_code_500(client: TestClient) -> None:
    app.state.tm = FakeClient(exc=TrueMoneyError("boom"))
    resp = client.get("/truemoney/ABCD1234EFGH/0812345678")
    assert resp.status_code == 200
    assert resp.json() == {"code": 500, "message": "Internal Server Error"}


def test_upstream_envelope_is_passed_through(client: TestClient) -> None:
    app.state.tm = FakeClient(
        result={"status": {"code": "VOUCHER_NOT_FOUND"}, "data": None}
    )
    resp = client.get("/truemoney/ABCD1234EFGH/0812345678")
    assert resp.status_code == 200
    assert resp.json() == {"status": {"code": "VOUCHER_NOT_FOUND"}, "data": None}


def test_redeems_via_get_and_passes_through(client: TestClient) -> None:
    resp = client.get("/truemoney/ABCD1234EFGH/0812345678")
    assert resp.status_code == 200
    assert resp.json() == SUCCESS_ENVELOPE
    assert app.state.tm.calls == [("ABCD1234EFGH", "0812345678")]


def test_redeems_via_post_equivalently(client: TestClient) -> None:
    resp = client.post("/truemoney/ABCD1234EFGH/0812345678")
    assert resp.status_code == 200
    assert app.state.tm.calls == [("ABCD1234EFGH", "0812345678")]


def test_accepts_a_url_encoded_full_campaign_link(client: TestClient) -> None:
    link = urllib.parse.quote("https://gift.truemoney.com/campaign/?v=ABCD1234EFGH", safe="")
    resp = client.get(f"/truemoney/{link}/0812345678")
    assert resp.status_code == 200
    # Normalization (extracting ?v=) happens inside Client.redeem, so the
    # route passes the decoded full link through to the client.
    url = "https://gift.truemoney.com/campaign/?v=ABCD1234EFGH"
    assert app.state.tm.calls == [(url, "0812345678")]


def test_options_preflight_is_answered_with_204_and_cors_headers(client: TestClient) -> None:
    resp = client.options(
        "/truemoney/ABCD1234EFGH/0812345678",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 204
    assert resp.headers["access-control-allow-origin"] == "*"
    assert "GET" in resp.headers["access-control-allow-methods"]
    assert "Content-Type" in resp.headers["access-control-allow-headers"]