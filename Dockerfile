# syntax=docker/dockerfile:1
# ─── Builder stage ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# Copy only what pip needs to install the package
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package with web dependencies
RUN pip install --no-cache-dir .[web]

# ─── Runtime stage ─────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy installed packages from builder (avoid pip cache with --no-cache-dir)
COPY --from=builder /usr/local/ /usr/local/

# Install curl for Docker healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create data directory mount point (overridden by docker-compose volume)
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "darth_gain.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
