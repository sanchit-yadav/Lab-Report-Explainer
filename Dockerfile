# ==============================================================================
# Multi-Stage Production Dockerfile for AI Clinical Lab Report Explainer
# Compatible with Hugging Face Spaces (Docker), Render, Railway, AWS, and Cloud Run
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
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition
COPY pyproject.toml .

# Create virtual environment and install dependencies
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV UV_HTTP_TIMEOUT=180

# Pre-install lightweight CPU-only PyTorch (avoids 4.5GB+ CUDA/Nvidia wheels)
RUN uv pip install --no-cache torch --index https://download.pytorch.org/whl/cpu

# Install application dependencies (includes psycopg2-binary for PostgreSQL)
RUN uv pip install --no-cache -r pyproject.toml

# ------------------------------------------------------------------------------
# Stage 2: Final Runtime
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Set security, Python, and microservice environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Install runtime system libraries required by OpenCV, Camelot, and Ghostscript
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    libgl1 \
    libglib2.0-0 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user (UID 1000 standard for Hugging Face Spaces & security)
RUN useradd -m -u 1000 -s /bin/bash appuser

WORKDIR /app

# Copy pre-built virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application codebase
COPY --chown=appuser:appuser . /app

# Ensure appuser owns /app and all runtime data directories with full read-write permissions
RUN mkdir -p /app/chroma_db /app/data/uploads /app/data && \
    chown -R appuser:appuser /app && \
    chmod -R 775 /app /app/data /app/chroma_db

# Switch to non-root user
USER appuser

# Expose FastAPI (8000), Hugging Face Spaces (7860), and Streamlit (8501) ports
EXPOSE 8000 7860 8501

# Healthcheck probe verifying microservice responsiveness
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || curl -f http://localhost:8000/healthz || curl -f http://localhost:8501/_stcore/health || exit 1

# Default startup command: Launch FastAPI microservice (with integrated React 19 SPA at root)
# Dynamically binds to $PORT (7860 on Hugging Face Spaces, 10000 on Render, 8000 default)
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}"]
