# Multi-stage build for composable-agents
# Stage 1: Build dependencies with uv
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Stage 2: Runtime image (Alpine for smaller attack surface and fewer CVEs)
FROM python:3.11-alpine

WORKDIR /app

# Upgrade system packages to fix CVEs
RUN apk update && apk upgrade && rm -rf /var/cache/apk/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application source and agent configs
COPY src/ /app/src/

# Set Python path and venv
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create non-root user for security (Alpine syntax)
RUN adduser -D -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "-m", "src.main"]
