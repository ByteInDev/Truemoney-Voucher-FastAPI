"""Unit tests for TrueMoney domain logic (validation + response rules).

Mirrors src/truemoney/voucher.spec.ts from the NestJS port.
"""

import pytest

from app.truemoney import TrueMoneyError, ValidationError, _mobile_number, _valid_json, _voucher_code


class TestVoucherCode:
    def test_accepts_a_raw_alnum_code(self) -> None:
        assert _voucher_code("ABCD1234EFGH") == "ABCD1234EFGH"

    def test_trims_surrounding_whitespace(self) -> None:
        assert _voucher_code("  ABCD1234EFGH  ") == "ABCD1234EFGH"

    def test_rejects_internal_spaces_in_a_raw_code(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("AB CD-12")

    def test_accepts_dashes_and_underscores(self) -> None:
        assert _voucher_code("AB_CD-12") == "AB_CD-12"

    def test_rejects_internal_spaces_in_a_raw_code(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("AB CD-12")

    def test_accepts_short_alnum_codes(self) -> None:
        assert _voucher_code("AB") == "AB"

    def test_accepts_codes_of_exactly_128_chars(self) -> None:
        code = "A" * 128
        assert _voucher_code(code) == code

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("   ")

    def test_rejects_codes_longer_than_128_chars(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("A" * 129)

    def test_rejects_illegal_characters(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("AB!CD")

    def test_rejects_wrong_lengths(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("A" * 129)

    def test_extracts_the_code_from_a_full_campaign_url(self) -> None:
        assert (
            _voucher_code("https://gift.truemoney.com/campaign/?v=ABCD1234EFGH")
            == "ABCD1234EFGH"
        )

    def test_accepts_a_full_campaign_url_with_extra_query_args(self) -> None:
        assert (
            _voucher_code("https://gift.truemoney.com/campaign/?v=ABCD1234EFGH&x=1")
            == "ABCD1234EFGH"
        )

    def test_rejects_non_https_urls(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("http://gift.truemoney.com/campaign/?v=ABCD1234EFGH")

    def test_rejects_foreign_hosts(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("https://evil.example.com/campaign/?v=ABCD1234EFGH")

    def test_rejects_wrong_paths(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("https://gift.truemoney.com/other/?v=ABCD1234EFGH")

    def test_rejects_a_url_without_a_v_param(self) -> None:
        with pytest.raises(ValidationError):
            _voucher_code("https://gift.truemoney.com/campaign/?x=1")


class TestMobileNumber:
    def test_accepts_a_valid_thai_mobile(self) -> None:
        assert _mobile_number("0812345678") == "0812345678"

    def test_strips_spaces_and_dashes(self) -> None:
        assert _mobile_number(" 081-234-5678 ") == "0812345678"

    def test_rejects_numbers_not_starting_with_0(self) -> None:
        with pytest.raises(ValidationError):
            _mobile_number("1812345678")

    def test_rejects_wrong_lengths(self) -> None:
        with pytest.raises(ValidationError):
            _mobile_number("081234567")
        with pytest.raises(ValidationError):
            _mobile_number("08123456789")

    def test_rejects_non_digit_characters(self) -> None:
        with pytest.raises(ValidationError):
            _mobile_number("081234567a")


class TestValidJson:
    def test_passes_an_empty_2xx_body_through_as_empty_dict(self) -> None:
        assert _valid_json(b"", 200) == {}

    def test_rejects_an_empty_body_on_error_status(self) -> None:
        with pytest.raises(TrueMoneyError):
            _valid_json(b"", 503)

    def test_rejects_a_non_json_body(self) -> None:
        with pytest.raises(TrueMoneyError):
            _valid_json(b"<html>challenge</html>", 200)

    def test_passes_a_status_envelope_through_on_http_400(self) -> None:
        body = b'{"status": {"code": "TARGET_USER_NOT_FOUND"}, "data": null}'
        assert _valid_json(body, 400) == {
            "status": {"code": "TARGET_USER_NOT_FOUND"},
            "data": None,
        }

    def test_rejects_error_status_without_a_status_envelope(self) -> None:
        with pytest.raises(TrueMoneyError):
            _valid_json(b'{"error": "nope"}', 502)

    def test_passes_any_2xx_payload_through(self) -> None:
        body = b'{"status": {"code": "SUCCESS"}, "data": {"amount": 50}}'
        assert _valid_json(body, 200)["status"]["code"] == "SUCCESS"