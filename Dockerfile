# Use Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Set UV cache directory to a persistent location
    UV_CACHE_DIR=/app/.uv-cache

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY main.py ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Expose the application port
EXPOSE 8080

# Run the application
CMD ["uv", "run", "python", "main.py"]
