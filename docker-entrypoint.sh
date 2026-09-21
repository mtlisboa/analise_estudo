#!/bin/sh
set -eu

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Ensuring environment sysadmin..."
python manage.py ensure_sysadmin

if [ "${DEPLOY_MODE:-}" = "MOCK" ]; then
    echo "Loading idempotent mock data..."
    python manage.py seed_mock_data
fi

exec "$@"
