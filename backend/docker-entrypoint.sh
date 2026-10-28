#!/bin/sh
# Apply pending database migrations, then start the server (or whatever command was given).
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo ">> Applying database migrations"
    alembic upgrade head
fi

if [ "${LOAD_FIXTURES:-0}" = "1" ]; then
    echo ">> Loading fixtures (${FIXTURES_INVOICES:-20} invoices, seed ${FIXTURES_SEED:-42})"
    python -m app.cli fixtures load --purge --yes \
        --invoices "${FIXTURES_INVOICES:-20}" --seed "${FIXTURES_SEED:-42}"
fi

exec "$@"
