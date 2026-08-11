"""Unit tests for the PORT configuration (mirrors src/config/app.config.spec.ts)."""

import importlib
import re

import pytest


class TestConfig:
    def test_defaults_to_3000_when_port_is_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PORT", raising=False)
        cfg = _load()
        assert cfg.port == 3000

    def test_reads_an_explicitly_set_valid_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "8080")
        assert _load().port == 8080

    def test_rejects_non_numeric_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "abc")
        with pytest.raises(ValueError, match=re.escape("invalid PORT")):
            _load()

    def test_rejects_port_out_of_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "70000")
        with pytest.raises(ValueError, match=re.escape("invalid PORT")):
            _load()

    def test_rejects_port_below_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "0")
        with pytest.raises(ValueError, match=re.escape("invalid PORT")):
            _load()

    def test_rejects_port_with_whitespace_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "  ")
        assert _load().port == 3000


def _load():
    # Imported per test so monkeypatching os.environ happens before load().
    from app.config import load

    return load()