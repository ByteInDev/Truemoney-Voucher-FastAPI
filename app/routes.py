"""Route registrations and handlers (mirrors internal/server/router.go)."""

import logging
import urllib.parse

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .middleware import mask_code
from .models import ErrBadRequest, ErrInternal
from .truemoney import Client, TrueMoneyError, ValidationError

logger = logging.getLogger("truemoney-voucher")

router = APIRouter()


def get_client(request: Request) -> Client:
    # Lazy: the curl_cffi session is only created on the first redeem, so
    # liveness probes and validation errors never pay session warm-up
    # (important on serverless, where every instance starts cold).
    if request.app.state.tm is None:
        request.app.state.tm = Client()
    return request.app.state.tm


@router.api_route("/truemoney/{code}/{mobile}", methods=["GET", "POST"])
def redeem(code: str, mobile: str, request: Request) -> Response:
    tm = get_client(request)

    # Starlette routes on the raw (still percent-encoded) path; decode
    # exactly once so {code} also accepts a full gift.truemoney.com link
    # like https%3A%2F%2Fgift.truemoney.com%2Fcampaign%2F%3Fv%3D<code>.
    code = urllib.parse.unquote(code)
    mobile = urllib.parse.unquote(mobile)

    try:
        result = tm.redeem(code, mobile)
    except ValidationError:
        raise ErrBadRequest
    except TrueMoneyError as err:
        logger.error("redeem failed err=%s code=%s", err, mask_code(code))
        raise ErrInternal

    return JSONResponse(content=result)


@router.api_route("/status", methods=["GET", "POST"])
def status() -> Response:
    return Response(status_code=200)


@router.api_route("/", methods=["GET", "POST"])
def root(request: Request) -> dict:
    # Minimal info: the last observed latency (ms) of every registered
    # route + a service banner, e.g.
    # {"ms": {"/": 1, "/status": 0, "/truemoney": 342},
    #  "message": "ByteInDev Service"}
    return {
        "ms": request.app.state.latency_ms,
        "message": "ByteInDev Service",
    }
