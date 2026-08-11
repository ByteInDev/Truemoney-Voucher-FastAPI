"""Application entrypoint (mirrors cmd/api/main.go + internal/server)."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import load as load_config
from .middleware import CorsMiddleware, LatencyMiddleware, LoggingMiddleware, RawPathMiddleware
from .models import AppError, ErrNotFound, ErrRecovered, error_response
from .routes import router
from .truemoney import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("truemoney-voucher")


async def _warm_loop(app: FastAPI, interval: float) -> None:
    """Keep the client's pooled connection and cf_clearance warm.

    One probe per interval, off the event loop (to_thread). Mirrors
    Go's StartWarmer: without it the first redeem after an idle gap pays
    the connection setup cost, and a cold cf_clearance risks a challenge.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(app.state.tm.probe)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - probe() already swallows; belt and suspenders
            logger.debug("warm probe unexpected error", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The client (and its curl_cffi session) is created eagerly so the
    # connection warmer can run; redeems share the same session.
    app.state.tm = Client()

    warm_task = None
    if app.state.cfg.warm_interval > 0:
        warm_task = asyncio.create_task(_warm_loop(app, app.state.cfg.warm_interval))
        logger.info("connection warmer interval_s=%s", app.state.cfg.warm_interval)

    logger.info("server starting addr=%s", app.state.cfg.addr)
    yield

    if warm_task is not None:
        warm_task.cancel()
        try:
            await warm_task
        except asyncio.CancelledError:
            pass
    app.state.tm.close()
    logger.info("server stopped")


def create_app() -> FastAPI:
    cfg = load_config()

    app = FastAPI(
        title="truemoney-voucher",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.cfg = cfg
    # Per-route latency snapshot (ms), filled by LatencyMiddleware and
    # surfaced on the root endpoint.
    app.state.latency_ms = {}

    # CORS allows any origin so the API can be consumed from scripts and
    # browser clients on other domains (mirrors Go's cors middleware:
    # any origin, GET/POST/OPTIONS, Content-Type, 204 on preflight).
    app.add_middleware(
        CorsMiddleware,
    )
    app.add_middleware(LoggingMiddleware)
    # Must wrap the router (added last => innermost) so routing sees the
    # raw path as Go's mux does.
    app.add_middleware(RawPathMiddleware)
    # Outermost: measures the full request (including CORS and routing).
    app.add_middleware(LatencyMiddleware)

    app.include_router(router)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Unknown routes and unknown methods both answer the JSON 404
        # envelope, matching the Go mux fallback ("/" handler).
        if exc.status_code in (404, 405):
            return error_response(ErrNotFound)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Recover-equivalent: a single bad request must not crash the process.
        logger.error(
            "panic recovered path=%s method=%s",
            request.url.path,
            request.method,
            exc_info=exc,
        )
        return error_response(ErrRecovered)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=app.state.cfg.port, log_level="info")