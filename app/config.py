import os


class Config:
    """Runtime configuration for the API server (mirrors internal/config)."""

    def __init__(self, port: int, warm_interval: float) -> None:
        self.port = port
        # Seconds between connection-warmer probes; <= 0 disables the loop.
        self.warm_interval = warm_interval

    @property
    def addr(self) -> str:
        return f"0.0.0.0:{self.port}"


def load() -> Config:
    """Load configuration from the environment with sane defaults.

    Raises only when an explicitly-set value is invalid.
    """
    raw = os.getenv("PORT", "").strip()
    if not raw:
        return Config(3000, _warm_interval())

    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"invalid PORT {raw!r}: must be a number between 1 and 65535")
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid PORT {raw!r}: must be a number between 1 and 65535")

    return Config(port, _warm_interval())


def _warm_interval() -> float:
    """WARM_INTERVAL seconds between warm probes; default 15 (matches the
    Go versions), <= 0 disables warming entirely."""
    raw = os.getenv("WARM_INTERVAL", "").strip()
    if not raw:
        return 15.0
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"invalid WARM_INTERVAL {raw!r}: must be a number")
    return value if value > 0 else 0.0