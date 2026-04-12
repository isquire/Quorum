#!/bin/sh
set -e

# Apply database migrations (idempotent). If migrations/ does not exist
# yet (fresh install), fall back to db.create_all() via a one-shot init.
if [ -d "/app/migrations" ]; then
    flask db upgrade
else
    python -c "from app import create_app; from app.extensions import db; app = create_app(); ctx = app.app_context(); ctx.push(); db.create_all()"
fi

exec "$@"
