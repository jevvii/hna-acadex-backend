#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

echo "==> Installing Python dependencies"
python -m pip install -r requirements.txt

# Allow build-time management commands to run before runtime env vars are fully configured.
export SKIP_PRODUCTION_ENV_VALIDATION=1
# Build-time fallback values (runtime env vars still required at app start).
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-build-only-secret-key}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost}"
export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-http://localhost}"

echo "==> Collecting static files"
python manage.py collectstatic --no-input

echo "==> Applying database migrations"
python manage.py migrate

echo "==> Ensuring superuser from env"
python manage.py createsu
