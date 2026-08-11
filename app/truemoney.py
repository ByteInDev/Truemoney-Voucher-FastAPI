"""TrueMoney gift voucher API client (mirrors internal/truemoney).

Calls https://gift.truemoney.com (protected by Cloudflare) through
curl_cffi, which impersonates a real Firefox browser at the TLS and
HTTP/2 wire level (libcurl-impersonate). This module only contains
TrueMoney domain logic: endpoints, payloads, headers and validation.
"""

import json
import logging
import re
import threading
import time
import urllib.parse
from collections import OrderedDict
from typing import Any

from curl_cffi import requests

CAMPAIGN_REFERER = "https://gift.truemoney.com/campaign/card"
REDEEM_URL = "https://gift.truemoney.com/campaign/vouchers/%s/redeem"

# Deliberately invalid probe values: TrueMoney answers with a JSON error
# envelope, so a probe refreshes the pooled connection and cf_clearance
# without ever touching the redeem cache.
PROBE_CODE = "PROBE000000"
PROBE_MOBILE = "0000000000"

# Compiled validation patterns (module-level: re caching is per call).
VOUCHER_PATTERN = re.compile(r"[A-Za-z0-9\-_]+")
MOBILE_CLEAN_PATTERN = re.compile(r"[ \-]")
MOBILE_PATTERN = re.compile(r"0\d{9}")

# Browsers headers mirror Firefox's; the UA version must stay in sync
# with the TLS/HTTP2 fingerprint (Firefox 148 in the Go version, curl_cffi
# ships up to Firefox 147 so impersonate="firefox" picks that).
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class TrueMoneyError(Exception):
    """Any failure validating input or talking to TrueMoney."""


class ValidationError(TrueMoneyError):
    """Invalid voucher code or mobile number (answers the 400 envelope)."""


class Client:
    """Performs TrueMoney voucher API calls over a browser-mimicking transport.

    One Client is shared by the whole service, so its cookie jar is common
    across all users. That is intentional — a warm cf_clearance improves
    stability against Cloudflare — but cookies are not isolated per caller.

    Successful redeem answers are cached in-process keyed by (code, mobile)
    for cache_ttl seconds (default 10 minutes, matching the Go version).
    A client that times out and retries replays the real answer of the
    first attempt instead of re-redeeming the voucher; transport failures
    and error envelopes are never cached.
    """

    def __init__(
        self,
        timeout: float = 15.0,
        cache_ttl: float = 600.0,
        cache_size: int = 1024,
    ) -> None:
        self._session = requests.Session(
            impersonate="firefox",
            timeout=timeout,
            headers=BROWSER_HEADERS,
        )
        self._cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._cache_ttl = cache_ttl
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._warm_lock = threading.Lock()  # single-flight: no stacked probes

    def close(self) -> None:
        self._session.close()

    def probe(self) -> None:
        """Fire one deliberately invalid redeem to keep the pooled
        connection and cf_clearance warm (mirrors the Go version's probe,
        which keeps the first real redeem off the ~120 ms connection
        setup path after an idle gap).

        The VOUCHER_NOT_FOUND answer is an error envelope, so it is never
        cached, and failures are swallowed (a probe must never affect
        traffic). Concurrent probes skip if one is already in flight.
        """
        if not self._warm_lock.acquire(blocking=False):
            return
        try:
            self._session.post(
                REDEEM_URL % PROBE_CODE,
                json={"mobile": PROBE_MOBILE},
                headers={"Content-Type": "application/json", "Referer": CAMPAIGN_REFERER},
            )
        except Exception as err:  # noqa: BLE001 - best-effort by design
            logging.getLogger("truemoney-voucher").debug("warm probe failed: %s", err)
        finally:
            self._warm_lock.release()

    def redeem(self, voucher: str, mobile: str) -> dict[str, Any]:
        """Redeem a TrueWallet voucher for the given phone number.

        Returns the TrueMoney JSON payload unchanged (including its
        {"status": ...} error envelope).
        """
        code = _voucher_code(voucher)
        phone = _mobile_number(mobile)

        key = f"{code}|{phone}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        resp = self._session.post(
            REDEEM_URL % code,
            json={"mobile": phone},
            headers={"Content-Type": "application/json", "Referer": CAMPAIGN_REFERER},
        )
        payload = _valid_json(resp.content, resp.status_code)
        if _is_success(payload):
            self._cache_put(key, payload)
        return payload

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, payload = entry
            if now - ts > self._cache_ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)  # LRU touch
            return payload

    def _cache_put(self, key: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = (time.monotonic(), payload)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)  # evict oldest insertion


def _is_success(payload: dict[str, Any]) -> bool:
    """True only for the {"status": {"code": "SUCCESS"}} answer."""
    status = payload.get("status")
    return isinstance(status, dict) and status.get("code") == "SUCCESS"


def _voucher_code(voucher: str) -> str:
    """Normalize a voucher code: a raw code or a full campaign URL."""
    voucher = voucher.strip()
    if not voucher:
        raise ValidationError("voucher code is required")

    if "://" in voucher:
        parsed = urllib.parse.urlsplit(voucher)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() != "gift.truemoney.com"
            or parsed.path != "/campaign/"
        ):
            raise ValidationError("invalid voucher URL")
        values = urllib.parse.parse_qs(parsed.query)
        voucher = values.get("v", [""])[0]

    if len(voucher) > 128:
        raise ValidationError("invalid voucher code")
    if not voucher:
        raise ValidationError("voucher code is required")
    if not VOUCHER_PATTERN.fullmatch(voucher):
        raise ValidationError("invalid voucher code")

    return voucher


def _mobile_number(phone: str) -> str:
    """Validate and normalize a Thai mobile number (10 digits, starts with 0)."""
    phone = MOBILE_CLEAN_PATTERN.sub("", phone.strip())
    if not MOBILE_PATTERN.fullmatch(phone):
        raise ValidationError("mobile number must contain 10 digits and start with 0")
    return phone


def _valid_json(data: bytes, status_code: int) -> dict[str, Any]:
    """Validate the raw response body, mirroring the Go version's rules.

    - an empty 2xx body (TrueMoney sometimes returns one, e.g. for
      already-redeemed vouchers) becomes {}
    - TrueMoney itself answers domain errors (e.g. TARGET_USER_NOT_FOUND)
      with HTTP 400 + a JSON "status" envelope, so non-2xx bodies carrying
      that envelope still pass through
    - anything else on a >=400 status — Cloudflare challenges or upstream
      errors without the envelope — becomes an error.
    """
    if not data:
        if 200 <= status_code < 300:
            return {}
        raise TrueMoneyError(f"TrueMoney returned HTTP {status_code} with an empty body")

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        raise TrueMoneyError(
            f"TrueMoney returned HTTP {status_code} with a non-JSON response: {_preview(data)}"
        )

    if status_code >= 400 and not (
        isinstance(payload, dict) and "status" in payload
    ):
        raise TrueMoneyError(
            f"upstream returned HTTP {status_code} without a TrueMoney "
            f"status envelope: {_preview(data)}"
        )

    return payload


def _preview(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return text[:200] + "..." if len(text) > 200 else text