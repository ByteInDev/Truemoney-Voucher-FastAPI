# syntax=docker/dockerfile:1
FROM python:3.14-slim AS runtime

# curl_cffi wheels bundle libcurl-impersonate, so no extra system deps.
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=3000
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/status')"]

CMD ["python", "-m", "app.main"]