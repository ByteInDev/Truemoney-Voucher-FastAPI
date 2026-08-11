"""TrueMoney gift voucher API client (mirrors internal/truemoney).

Calls https://gift.truemoney.com (protected by Cloudflare) through
curl_cffi, which impersonates a real Firefox browser at the TLS and
HTTP/2 wire level (libcurl-impersonate). This module only contains
TrueMoney domain logic: endpoints, payloads, headers and validation.
"""

import json
import re
import urllib.parse
from typing import Any

from curl_cffi import requests

CAMPAIGN_REFERER = "https://gift.truemoney.com/campaign/card"
REDEEM_URL = "https://gift.truemoney.com/campaign/vouchers/%s/redeem"

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
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._session = requests.Session(
            impersonate="firefox",
            timeout=timeout,
            headers=BROWSER_HEADERS,
        )

    def close(self) -> None:
        self._session.close()

    def redeem(self, voucher: str, mobile: str) -> dict[str, Any]:
        """Redeem a TrueWallet voucher for the given phone number.

        Returns the TrueMoney JSON payload unchanged (including its
        {"status": ...} error envelope).
        """
        code = _voucher_code(voucher)
        phone = _mobile_number(mobile)

        resp = self._session.post(
            REDEEM_URL % code,
            json={"mobile": phone},
            headers={"Content-Type": "application/json", "Referer": CAMPAIGN_REFERER},
        )
        return _valid_json(resp.content, resp.status_code)


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
    if not re.fullmatch(r"[A-Za-z0-9\-_]+", voucher):
        raise ValidationError("invalid voucher code")

    return voucher


def _mobile_number(phone: str) -> str:
    """Validate and normalize a Thai mobile number (10 digits, starts with 0)."""
    phone = re.sub(r"[ \-]", "", phone.strip())
    if not re.fullmatch(r"0\d{9}", phone):
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