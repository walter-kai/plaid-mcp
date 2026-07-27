# Python
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /usr/local/bin/uv

# Dependencies first (better layer caching)
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

# Non-root
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Cloud Run sets PORT; PLAID_APP_MODE selects api|link|all
ENV PLAID_APP_MODE=all
CMD ["sh", "-c", "uvicorn plaid_mcp.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
