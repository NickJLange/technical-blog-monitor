# Multi-stage build for Technical Blog Monitor daemon
# Build: podman build -t technical-blog-monitor .
# Run:   podman run -d --name blog-monitor \
#          -e VECTOR_DB__CONNECTION_STRING=postgresql://user@postgres:5432/blogmon \
#          -e CACHE__BACKEND=postgres \
#          -e EMBEDDING__OPENAI_API_KEY=sk-... \
#          technical-blog-monitor

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies with uv
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.12-slim

# Install runtime dependencies
# - libpq-dev for psycopg2
# - libxml2, libxslt1 for lxml (readability)
# - chromium deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libxml2 \
    libxslt1.1 \
    libssl3 \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r blogmon && useradd -r -g blogmon blogmon

# Set working directory
WORKDIR /app

# Copy from builder (source code + dependencies)
COPY --from=builder /app /app

# Debug: Check venv structure (Removed)
# RUN ls -la /app/.venv/bin/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/browsers

# Install Playwright browsers and dependencies (requires root)
RUN /app/.venv/bin/python -m playwright install --with-deps

# Create data directory and fix permissions
RUN mkdir -p /app/data /app/cache && \
    chown -R blogmon:blogmon /app

# Switch to non-root user
USER blogmon

# Health check - verify the daemon is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from monitor.config import load_settings; load_settings()" || exit 1

# Labels for metadata
LABEL org.opencontainers.image.title="Technical Blog Monitor" \
    org.opencontainers.image.description="Daemon that monitors technical blogs, renders posts, and generates embeddings" \
    org.opencontainers.image.version="0.1.0"

# Run daemon (keeps container running)
ENTRYPOINT ["/app/.venv/bin/python", "-m", "monitor.main"]
CMD []
