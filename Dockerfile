# Use Python 3.11 slim as base image
FROM python:3.11-slim AS builder

# Set environment variables
ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set working directory
WORKDIR /app

# Copy poetry configuration files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN pip install --upgrade pip && \
    pip install poetry==${POETRY_VERSION} && \
    poetry install --no-dev --no-root

# Copy the project files
COPY . .

# Install the project
RUN poetry install --no-dev

# Second stage: Runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

# Copy from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create a non-root user to run the application
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create directories for cache and data with proper permissions
RUN mkdir -p /app/data /app/cache && \
    chown -R appuser:appuser /app/data /app/cache

# Set working directory
WORKDIR /app

# Install Playwright browsers
RUN playwright install chromium firefox webkit && \
    playwright install-deps

# Switch to non-root user
USER appuser

# Expose Prometheus metrics port
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["python", "-m", "monitor.main"]

# Default command (can be overridden)
CMD ["--log-level", "INFO"]
