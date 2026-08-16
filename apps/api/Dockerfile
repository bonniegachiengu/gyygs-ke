# Build context is the REPO ROOT (see infra/docker-compose.yml `context: ..`).
FROM python:3.11-slim AS builder
WORKDIR /build
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/app ./app
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# /data holds the quote-ref counter and is a named volume at runtime. It has to be
# chowned BEFORE dropping privileges or the sequence file cannot be written.
RUN adduser --system --group --no-create-home app \
 && mkdir -p /data \
 && chown app:app /data

COPY --from=builder /install /usr/local
WORKDIR /srv
COPY --chown=app:app apps/api/app ./app

USER app
EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8010/api/health')"

# --forwarded-allow-ips is safe here: this container publishes no ports, so only
# `web` (nginx) can reach it, and the rate limiter needs the real client IP.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8010", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--no-server-header"]
