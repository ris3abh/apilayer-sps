# Build stage
FROM python:3.13-slim AS builder

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself first for better caching)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Install the project
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire app including .venv from builder
COPY --from=builder /app /app

# Add .venv/bin to PATH so Python can find installed packages
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app"

EXPOSE 8000

# Run the application
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
