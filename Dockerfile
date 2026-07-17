# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy package metadata and lockfile first for layer caching.
COPY pyproject.toml uv.lock ./
COPY README.md LICENSE ./
COPY src ./src

# Install production + server dependencies.
RUN uv sync --frozen --all-extras --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Data volume for store and SQLite database.
VOLUME ["/data"]

EXPOSE 8080

CMD ["okf-server", "serve", "--host", "0.0.0.0", "--port", "8080", "--store", "/data/store", "--database", "/data/server.db"]
