import os


class Config:
    """Runtime configuration for the API server (mirrors internal/config)."""

    def __init__(self, port: int) -> None:
        self.port = port

    @property
    def addr(self) -> str:
        return f"0.0.0.0:{self.port}"


def load() -> Config:
    """Load configuration from the environment with sane defaults.

    Raises only when an explicitly-set value is invalid.
    """
    raw = os.getenv("PORT", "").strip()
    if not raw:
        return Config(3000)

    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"invalid PORT {raw!r}: must be a number between 1 and 65535")
    if not 1 <= port <= 65535:
        raise ValueError(f"invalid PORT {raw!r}: must be a number between 1 and 65535")

    return Config(port)