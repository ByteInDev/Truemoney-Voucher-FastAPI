"""HTTP middleware (mirrors internal/middleware)."""

import logging
import time

from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("truemoney-voucher")


def mask_code(code: str) -> str:
    """Hide all but the first and last four characters of a voucher code.

    A voucher code is cash-equivalent and must never appear in plaintext
    in logs.
    """
    if len(code) <= 8:
        return "****"
    return code[:4] + "****" + code[-4:]


def mask_path(path: str) -> str:
    """Mask the voucher segment of a /truemoney/... path for logging."""
    parts = path.split("/")
    if len(parts) >= 4 and parts[1] == "truemoney":
        parts[2] = mask_code(parts[2])
    return "/".join(parts)


class RawPathMiddleware:
    """Route on the raw (percent-encoded) path, like Go's ServeMux does.

    ASGI spec servers (uvicorn) percent-decode scope["path"] before
    routing, so an encoded slash (%2F) inside a voucher link becomes a
    real slash and the route can no longer match. scope["raw_path"]
    keeps the request's raw path, so we use it for matching and let the
    handler decode the segment once (mirrors Go's r.PathValue).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("raw_path"):
            scope["path"] = scope["raw_path"].decode("ascii")
        await self.app(scope, receive, send)


class CorsMiddleware:
    """CORS mirroring Go's internal/middleware/cors.go exactly.

    Allows any origin, only GET/POST/OPTIONS, Content-Type headers, and
    answers OPTIONS preflights with 204 (Starlette's own CORSMiddleware
    answers 200, which would break wire parity with the Go version).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope["method"] == "OPTIONS":
            response = Response(
                status_code=204,
                headers={
                    "access-control-allow-origin": "*",
                    "access-control-allow-methods": "GET, POST, OPTIONS",
                    "access-control-allow-headers": "Content-Type",
                },
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(
                    [
                        (b"access-control-allow-origin", b"*"),
                        (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                        (b"access-control-allow-headers", b"Content-Type"),
                    ]
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


class LatencyMiddleware:
    """Records the last latency (ms) of every handled route.

    The snapshot lives on app.state.latency_ms (a plain dict keyed by
    normalized route pattern, e.g. "/truemoney/{code}/{mobile}" ->
    "/truemoney") and is surfaced on the root endpoint as {"ms": {...}}.
    Unknown (unrouted) paths keep their raw path as the key.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        await self.app(scope, receive, send)

        # scope["route"] is set by the router during the inner call; the
        # app object carries the shared state dict.
        state = scope.get("app")
        if state is None:
            return
        snapshot = getattr(state.state, "latency_ms", None)
        if snapshot is None:
            snapshot = {}
            state.state.latency_ms = snapshot
        snapshot[_latency_key(scope)] = round((time.monotonic() - started) * 1000)


def _latency_key(scope: Scope) -> str:
    """Map a route pattern to the stable root key: strip path params."""
    route = scope.get("route")
    path = route.path if route is not None else scope.get("path", "")
    if path == "":
        return "/"
    brace = path.find("{")
    if brace != -1:
        path = path[:brace].rstrip("/")
        if path == "":
            return "/"
    return path


class LoggingMiddleware:
    """Logs one line per request: method, masked path, status, duration."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.monotonic()
        status = {"code": 200}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        logger.info(
            "request method=%s path=%s status=%s duration_ms=%d",
            scope["method"],
            mask_path(scope.get("path", "")),
            status["code"],
            round((time.monotonic() - started) * 1000),
        )