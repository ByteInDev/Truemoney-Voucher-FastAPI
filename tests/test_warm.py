"""Connection-warmer probe tests.

The probe must behave like the Go version's: a deliberately-invalid
redeem against the upstream, answers never cached, failures swallowed,
and one at a time.
"""

from app.truemoney import PROBE_CODE, PROBE_MOBILE, REDEEM_URL, Client

ERROR_ENVELOPE = (
    b'{"status":{"code":"VOUCHER_NOT_FOUND",'
    b'"message":"invalid voucher"},"data":"VOUCHER_NOT_FOUND"}'
)


class FakeSession:
    def __init__(self, status_code: int, content: bytes, fail: bool = False) -> None:
        self.status_code = status_code
        self.content = content
        self.fail = fail
        self.sent: list[tuple[str, dict, dict]] = []
        self.closed = False

    def post(self, url: str, json: dict, headers: dict):
        if self.fail:
            raise RuntimeError("connection refused")
        self.sent.append((url, json, headers))
        return self

    def close(self) -> None:
        self.closed = True


def make_client(session: FakeSession) -> Client:
    client = Client()
    client._session = session
    return client


def test_probe_targets_the_invalid_code() -> None:
    session = FakeSession(status_code=400, content=ERROR_ENVELOPE)
    client = make_client(session)

    client.probe()

    assert len(session.sent) == 1
    url, payload, headers = session.sent[0]
    assert url == REDEEM_URL % PROBE_CODE
    assert payload == {"mobile": PROBE_MOBILE}
    assert headers["Referer"].startswith("https://gift.truemoney.com")


def test_probe_never_caches_the_error_envelope() -> None:
    session = FakeSession(status_code=400, content=ERROR_ENVELOPE)
    client = make_client(session)

    client.probe()
    client.probe()

    assert len(session.sent) == 2
    assert len(client._cache) == 0


def test_probe_swallows_transport_failures() -> None:
    session = FakeSession(status_code=0, content=b"", fail=True)
    client = make_client(session)

    client.probe()  # must not raise

    assert len(client._cache) == 0


def test_probe_skips_when_already_in_flight() -> None:
    session = FakeSession(status_code=400, content=ERROR_ENVELOPE)
    client = make_client(session)

    client._warm_lock.acquire(blocking=False)  # simulate an in-flight probe
    try:
        client.probe()
    finally:
        client._warm_lock.release()

    assert session.sent == []  # skipped: no stacked probes