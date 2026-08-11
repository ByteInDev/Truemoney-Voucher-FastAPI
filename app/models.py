"""Shared error shapes (mirrors internal/model + pkg/response)."""

from fastapi.responses import JSONResponse


class AppError(Exception):
    """API error response shape shared by every handler.

    The body carries TrueMoney-style code + message; ``status`` is the
    real HTTP status code and is never part of the body.
    """

    def __init__(self, code: int, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# Sentinel errors used across the API. Bad input and upstream failures are
# answered with HTTP 200 + code/message in the body, matching the upstream
# convention the frontend was built against.
ErrBadRequest = AppError(400, "Bad Request", 200)
ErrNotFound = AppError(404, "Not Found", 404)
ErrInternal = AppError(500, "Internal Server Error", 200)
ErrRecovered = AppError(500, "Internal Server Error", 500)


def error_response(err: AppError) -> JSONResponse:
    return JSONResponse(status_code=err.status, content={"code": err.code, "message": err.message})