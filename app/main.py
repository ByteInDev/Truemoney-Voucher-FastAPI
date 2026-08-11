"""Application entrypoint (mirrors cmd/api/main.go + internal/server)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import load as load_config
from .middleware import CorsMiddleware, LoggingMiddleware, RawPathMiddleware
from .models import AppError, ErrNotFound, ErrRecovered, error_response
from .routes import router
from .truemoney import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("truemoney-voucher")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tm = Client()
    logger.info("server starting addr=%s", app.state.cfg.addr)
    yield
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