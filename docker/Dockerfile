# ==========================================
# Stage 1: Builder
# ==========================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Configure Poetry to build inside a virtual env in the project root
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install only production dependencies
RUN poetry install --only main --no-interaction --no-ansi --no-root

# ==========================================
# Stage 2: Production Runtime
# ==========================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies (e.g. git is required by git python fetcher)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root system user and group
RUN groupadd -g 10001 runtimeops && \
    useradd -u 10001 -g runtimeops -m -s /bin/bash runtimeops

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source code and config files
COPY src/ ./src/

# Set ownership of the app directory to the non-root user
RUN chown -R runtimeops:runtimeops /app

# Switch to the non-root user
USER runtimeops

# Expose REST and gRPC API ports
EXPOSE 8000 50052

# Configure production health check using REST health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
# Note: we bind to both REST and gRPC on startup inside main.py
CMD ["python", "-m", "uvicorn", "bob.main:app", "--host", "0.0.0.0", "--port", "8000"]
