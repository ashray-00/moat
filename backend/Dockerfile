# Slim API image for Render/Railway/etc.
# Prefer RERANK_PROVIDER=cohere|none — local CrossEncoder is optional (see [local-rerank]).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    RERANK_PROVIDER=cohere

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Install deps before copying full tree so code edits don't bust the layer.
COPY pyproject.toml README.md* ./
COPY app ./app
COPY worker ./worker

RUN uv pip install --system -e .

COPY . .

EXPOSE 8000

# Render/Railway set PORT; default 8000 for local docker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
