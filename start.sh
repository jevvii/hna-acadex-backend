#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

echo "==> Starting at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "==> Python version: $(python --version 2>&1)"

echo "==> Running database migrations"
python manage.py migrate --no-input --verbosity=1

echo "==> Ensuring superuser from env"
python manage.py createsu

echo "==> Starting Gunicorn"
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"