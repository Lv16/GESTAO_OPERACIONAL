#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"

cd "$(dirname "$0")/.."

echo "Starting Django dev server on ${HOST}:${PORT} with setup.settings_dev"
exec python manage.py runserver "${HOST}:${PORT}" --settings=setup.settings_dev
