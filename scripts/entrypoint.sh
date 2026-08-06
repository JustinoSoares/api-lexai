#!/bin/sh
set -e

# Aplica migrations automaticamente apenas se RUN_MIGRATIONS=true.
#if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "run_migrations_enabled"
    until alembic upgrade head > /tmp/migrate.log 2>&1; do
        echo "migrations_failed_retry"
        sleep 3
    done
#else
#    echo "run_migrations_skipped"
#fi

exec "$@"
