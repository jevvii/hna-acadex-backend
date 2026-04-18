#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Allow build-time management commands to run before runtime env vars are fully configured.
export SKIP_PRODUCTION_ENV_VALIDATION=1

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createsu
