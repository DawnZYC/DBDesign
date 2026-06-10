# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Stage 1: builder — install Python dependencies into an isolated venv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build deps for psycopg if a binary wheel is unavailable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# INSTALL_ML=true bakes in local-embedding deps (sentence-transformers) using
# the CPU-only torch wheel to keep the image lean. Set to "false" for an even
# smaller image when using cloud embedding providers (OpenAI / DashScope).
ARG INSTALL_ML=true

COPY requirements.txt requirements-ml.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && if [ "$INSTALL_ML" = "true" ]; then \
         /opt/venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu \
         && /opt/venv/bin/pip install -r requirements-ml.txt; \
       fi

# ---------------------------------------------------------------------------
# Stage 2: runtime — slim image, only the venv and app code
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq for psycopg runtime; tini for proper signal handling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
# Seed scripts + domain knowledge so RAG can be seeded inside the container:
#   docker compose exec backend python seed_commodities.py && python seed_rag.py
COPY seed_commodities.py seed_rag.py domain_knowledge.md ./

# Writable ChromaDB persistence dir (mounted as a volume by docker-compose).
RUN mkdir -p /app/chroma_data && chown -R app:app /app/chroma_data
ENV CHROMA_PERSIST_DIR=/app/chroma_data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
