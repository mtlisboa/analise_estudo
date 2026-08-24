#!/bin/sh
set -eu

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Ensuring environment sysadmin..."
python manage.py ensure_sysadmin

echo "Preparing mock deployment data when enabled..."
python manage.py seed_mock_data

exec "$@"
