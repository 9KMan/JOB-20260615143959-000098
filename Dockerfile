# =============================================================================
# Multi-stage Dockerfile for Scraper Worker
# Stage 1: Builder - Install dependencies and Playwright browsers
# Stage 2: Production - Minimal runtime image
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright system dependencies
    wget \
    gnupg \
    curl \
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
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    # Additional dependencies
    git \
    procps \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

# Create app directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-root --no-dev

# Install Playwright browsers
RUN poetry run playwright install chromium && \
    poetry run playwright install-deps chromium

# -----------------------------------------------------------------------------
# Stage 2: Production
# -----------------------------------------------------------------------------
FROM python:3.12-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Xvfb for headless display
    xvfb \
    # Chromium dependencies
    chromium \
    chromium-sandbox \
    libxkbcommon0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libasound2 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Create non-root user for security
RUN groupadd --gid 1000 scraper && \
    useradd --uid 1000 --gid scraper --shell /bin/bash --create-home scraper

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set up working directory
WORKDIR /app

# Copy application code
COPY --chown=scraper:scraper . .

# Switch to non-root user
USER scraper

# Set up environment
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    DISPLAY=:99

# Create Xvfb run directory
RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import pika; print('Worker health check passed')" || exit 1

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "scraper.worker"]
