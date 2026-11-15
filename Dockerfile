# ==============================================================================
# Multi-Stage Production Dockerfile for AI Clinical Lab Report Explainer
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install uv for high-speed deterministic package resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install system compilation dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition
COPY pyproject.toml .

# Create virtual environment and install dependencies
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_HTTP_TIMEOUT=180

# Pre-install lightweight CPU-only PyTorch (avoids 4.5GB+ CUDA/Nvidia wheels and download timeouts)
RUN uv pip install --no-cache torch --index https://download.pytorch.org/whl/cpu

# Install application dependencies
RUN uv pip install --no-cache -r pyproject.toml

# ------------------------------------------------------------------------------
# Stage 2: Final Runtime
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Set security, Python, and Streamlit environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Install runtime system libraries required by OpenCV, Camelot, and Ghostscript
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user (UID 10001) for strict container security
RUN useradd -m -u 10001 -s /bin/bash appuser

WORKDIR /app

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application codebase
COPY --chown=appuser:appuser . /app

# Ensure appuser owns /app and all runtime data directories with read-write permissions
RUN mkdir -p /app/chroma_db /app/data/uploads && \
    chown -R appuser:appuser /app && \
    chmod -R 775 /app

# Switch to non-root user
USER appuser

# Expose Streamlit (8501) and FastAPI (8000) ports
EXPOSE 8501 8000

# Healthcheck probe verifying service responsiveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || curl -f http://localhost:8000/healthz || exit 1

# Default startup command (can be overridden by docker-compose for api/workers)
CMD ["python", "-m", "streamlit", "run", "app.py"]
