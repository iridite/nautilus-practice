FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app

# Install build deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install uv runner
RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install uv

# Copy project metadata first for efficient Docker layer caching
COPY pyproject.toml uv.lock /app/

# Install project dependencies using uv (reads pyproject.toml)
RUN uv sync || true

# Copy the rest of the project
COPY . /app

# Default workdir
WORKDIR /app

# Default command: run the sandbox engine. Users can override with docker run <image> <cmd>
CMD ["uv", "run", "python", "-u", "sandbox/engine.py"]
