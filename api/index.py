"""Vercel serverless entrypoint (ASGI).

Vercel's Python runtime serves ASGI applications exported as ``app``.
``vercel.json`` rewrites every path into this function and pins the
runtime to python3.12 (curl_cffi publishes manylinux wheels, so the
browser-mimicking transport installs and runs on Lambda).
"""

from app.main import app

handler = app