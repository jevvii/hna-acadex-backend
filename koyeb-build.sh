#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

echo "==> Koyeb build started at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "==> Python version: $(python --version 2>&1)"

echo "==> Installing Python dependencies"
python -m pip install -r requirements.txt

# Allow collectstatic to run during build before full runtime env is available.
export SKIP_PRODUCTION_ENV_VALIDATION=1
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-build-only-secret-key}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost}"
export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-http://localhost}"

echo "==> Collecting static files"
python manage.py collectstatic --no-input --verbosity=2

echo "==> Koyeb build completed at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
