# ==========================================
# Stage 1: Builder - install deps
# ==========================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==========================================
# Stage 2: Runtime - minimal image
# ==========================================
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Runtime system dependencies only (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY . .

# Build-time env vars so collectstatic can run without real secrets
ENV SKIP_PRODUCTION_ENV_VALIDATION=1
ENV DJANGO_SECRET_KEY=build-only-secret-key-not-for-runtime
ENV DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
ENV CORS_ALLOWED_ORIGINS=http://localhost
ENV CSRF_TRUSTED_ORIGINS=http://localhost

# Collect static files at build time (whitenoise serves them at runtime)
RUN python manage.py collectstatic --no-input --verbosity=0

# Ensure start.sh is executable
RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["./start.sh"]