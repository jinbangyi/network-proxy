# Use Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Set UV cache directory to a persistent location
    UV_CACHE_DIR=/app/.uv-cache

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create a non-root user (UID/GID 1000) to match the K8s pod securityContext
# in deploy/k8s/base/manager-api.yaml. The uv cache and venv are written to
# /app during build, so /app must be owned by the runtime user.
RUN groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && mkdir -p /app && chown -R app:app /app

# Set working directory
WORKDIR /app

# Copy project files with non-root ownership so uv can write to /app
# (pyproject.toml, uv.lock, etc. remain readable and the .venv / .uv-cache
# created next are owned by app).
COPY --chown=app:app pyproject.toml uv.lock README.md ./
COPY --chown=app:app src/ ./src/
COPY --chown=app:app main.py ./

# Switch to non-root user for install AND runtime
USER app

# Install dependencies using uv (writes to /app/.venv and /app/.uv-cache)
RUN uv sync --frozen --no-dev

# Expose the manager API port
EXPOSE 9001

# Run the application
CMD ["uv", "run", "python", "main.py", "serve"]
