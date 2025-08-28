FROM python:3.11-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Set work directory
WORKDIR /app

# Install build dependencies (only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --no-deps -r requirements.txt -w /wheels

FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install runtime dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy project files
COPY backend/ .
COPY Frontend /app/Frontend/
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.sh

# Create non-root user and group
RUN addgroup --gid 1001 appuser \
 && adduser --uid 1001 --gid 1001 --disabled-password --gecos "" appuser

# Create staticfiles directory with correct ownership
RUN mkdir -p /app/staticfiles && chown -R appuser:appuser /app/staticfiles

# Create data directory with proper owner
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Healthcheck (customize as needed)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Default command
CMD ["/scripts/prod.sh"]
