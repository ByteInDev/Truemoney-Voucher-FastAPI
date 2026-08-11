<br>

<div align="center">

# Truemoney-Voucher (FastAPI)

**REST API for redeeming TrueMoney gift vouchers** — Python FastAPI, no database

![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)
![Python Version](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

**English** - [Thai](README.th.md)

</div>

---

A minimal FastAPI port of the [Go implementation](https://github.com/ByteInDev/Truemoney-Voucher-Go)
that talks to `gift.truemoney.com` through a transport that mimics a real
Firefox browser at the TLS and HTTP/2 wire level, so requests pass
Cloudflare bot detection. One operation only: **redeem** a voucher to a
Thai mobile number.

## Features

| Ability | Details |
| ------- | ------- |
| Redeem | `GET`/`POST /truemoney/{code}/{mobile}` - redeem to a mobile number (both methods are equivalent) |
| Raw code or full link | accepts `gift.truemoney.com/campaign/?v=<code>` URLs too |
| Input validation | code <= 128 chars; Thai mobile: 10 digits starting with `0` |
| Cloudflare bypass | curl_cffi `impersonate="firefox"` (libcurl-impersonate TLS/HTTP2 fingerprint) |
| Safe by design | codes masked in logs, graceful shutdown |

## Quick Start

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
python -m app.main            # listens on :3000
```

```bash
docker build -t truemoney-voucher -f deployments/Dockerfile .
docker run -d -p 3000:3000 truemoney-voucher
```

Check it is alive:

```bash
curl localhost:3000/status           # 200 OK (empty)
curl localhost:3000/                 # service info + routes
```

## API Reference

### Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| `GET` / `POST` | `/truemoney/{code}/{mobile}` | Redeem a voucher |
| `GET` / `POST` | `/status` | Liveness probe |
| `GET` / `POST` | `/` | Service info and route list |

### Path parameters

| Param | Accepted format |
| ----- | --------------- |
| `code` | Raw code (alnum + `-`/`_`, <= 128 chars) or URL-encoded full link `https://gift.truemoney.com/campaign/?v=<code>` |
| `mobile` | Thai mobile: 10 digits starting with `0` (spaces/dashes auto-stripped) |

### Examples

```bash
# Redeem with a raw code - GET and POST are equivalent
curl "localhost:3000/truemoney/ABCD1234EFGH/0812345678"
curl -X POST "localhost:3000/truemoney/ABCD1234EFGH/0812345678"

# Redeem with a URL-encoded full link (use --path-as-is to stop curl
# from normalizing %2F into /)
curl --path-as-is "localhost:3000/truemoney/https%3A%2F%2Fgift.truemoney.com%2Fcampaign%2F%3Fv%3DABCD1234EFGH/0812345678"
```

### Responses

TrueMoney's JSON is passed through unchanged (including its `{"status": {...}}`
error envelope). Own errors are always `code` + `message`:

| HTTP status | Body | When |
| ----------- | ---- | ---- |
| `200` | `{"code": 400, "message": "Bad Request"}` | invalid code / mobile |
| `404` | `{"code": 404, "message": "Not Found"}` | unknown path or method |
| `200` | `{"code": 500, "message": "Internal Server Error"}` | TrueMoney call failed |
| `500` | `{"code": 500, "message": "Internal Server Error"}` | unhandled exception |

### TrueMoney status codes

Inside `status.code` of the envelope:

| Code | Meaning |
| ---- | ------- |
| `SUCCESS` | Money received successfully |
| `TARGET_USER_REDEEMED` | You already redeemed this voucher |
| `VOUCHER_OUT_OF_STOCK` | Someone else already took it |
| `VOUCHER_EXPIRED` | The wallet voucher has expired |
| `VOUCHER_NOT_FOUND` | Voucher not found in the system |
| `CANNOT_GET_OWN_VOUCHER` | Cannot redeem your own voucher |
| `TARGET_USER_NOT_FOUND` | Phone number not found in the system |
| `INTERNAL_ERROR` | Voucher not found, or the URL is wrong |

## Configuration

| Env var | Default | Description |
| ------- | ------- | ----------- |
| `PORT` | `3000` | HTTP listen port (1-65535) |

```bash
PORT=8080 python -m app.main
```

## Build and Deploy

```bash
make run           # python -m app.main
make install       # pip install -r requirements.txt
make quality       # python -m compileall -q app
make docker-build  # docker build -t truemoney-voucher
make deploy-local  # docker run -d -p 3000:3000 truemoney-voucher
make deploy        # scp + venv + uvicorn on a remote server
                   # (host/user hardcoded in the Makefile - edit first!)
make vercel-deploy # vercel --prod (serverless)
```

## Architecture (tl;dr)

- **`app/truemoney.py`** — TrueMoney domain logic: validation, headers,
  redeeming, response handling. One shared session + cookie jar (keeps
  `cf_clearance` warm).
- **`app/main.py`** — FastAPI app factory + lifespan; uvicorn entrypoint.
- **`app/middleware.py`** — request logging (codes masked), raw-path
  routing so `%2F`-encoded links still match (like Go's ServeMux +
  `r.PathValue`).
- **`app/config.py`** — `PORT` env handling.
- **`app/models.py`** — shared error envelope (`code` + `message`).

### Differences from the Go version

| Go | Python |
| -- | ------ |
| uTLS `HelloFirefox_148` + hand-built HTTP/2 framer | curl_cffi `impersonate="firefox"` (FF 147 fingerprint, libcurl-impersonate) |
| manual gzip/deflate/br handling | handled automatically by curl_cffi |
| `net/http` mux + method patterns | FastAPI routes |
| `log/slog` structured logs | stdlib `logging` |

## Testing

```bash
make test            # pytest (validation + HTTP contract via TestClient)
```

The suite runs offline — the real curl_cffi session is stubbed out, so no
request leaves the machine.

## Deploy to Vercel

Vercel's FastAPI preset auto-detects the framework from `requirements.txt`
and loads the `app` instance from `app/main.py` (a supported Python
entrypoint), so **no rewrites are needed** — every path reaches the
FastAPI router untouched. `vercel.json` only tunes the single function
(`maxDuration: 60`). The Python version is pinned via `.python-version`
(3.12, Vercel's default). curl_cffi publishes manylinux wheels, so the
browser-mimicking transport works on Lambda.

```bash
make vercel-deploy           # = vercel --prod
```

**Serverless caveats:**

- the curl_cffi session is created **lazily** — only on the first redeem,
  never at bootstrap, so `/status`, `/` and validation errors stay fast on
  cold instances; it also cannot stay warm between function instances
- Cold Start adds latency (same trade-off as the other ports)

**Performance on the Free (Hobby) plan:** functions run only in `iad1`
(US East) — Thailand→Virginia RTT (~200 ms) is fixed and unavoidable, and
cannot be configured away on a free plan. `maxDuration: 60` is honored.
Measure with a keep-alive client (e.g. `httpx`), not a fresh `curl.exe`
per request, to see actual server time.

## Disclaimer

> **For educational use or where the provider permits it.**
> Redeeming is irreversible and governed by TrueMoney's Terms of Service.
> Voucher codes are cash-equivalent — never expose logs containing full codes.

## Contributing

Contributions are welcome! Please:

1. Open an issue first for significant changes
2. Keep `make quality` green
3. Follow the existing code style

## License

Licensed under the [MIT License](./LICENSE) © 2026 ByteInDev