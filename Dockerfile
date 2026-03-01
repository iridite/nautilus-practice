# Multi-stage Dockerfile for NautilusTrader Practice
# Target image size: < 1GB

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.12-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies using uv
RUN uv pip install --system --no-cache -r pyproject.toml

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.12-slim AS runtime

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 nautilus && \
    mkdir -p /app/data /app/output /app/logs && \
    chown -R nautilus:nautilus /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY strategy/ ./strategy/
COPY backtest/ ./backtest/
COPY core/ ./core/
COPY utils/ ./utils/
COPY config/ ./config/
COPY data/instrument/ ./data/instrument/
COPY main.py ./
COPY pyproject.toml ./

# Copy entrypoint script
COPY docker/entrypoint-standalone.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# Create output directories
RUN mkdir -p /app/output/backtest/result \
    /app/output/backtest/report \
    /app/output/logs

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER nautilus

# Entrypoint
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Default command (can be overridden)
CMD ["backtest", "--type", "high"]
