#!/bin/sh
set -eu

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Ensuring environment sysadmin..."
python manage.py ensure_sysadmin

exec "$@"
