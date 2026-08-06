#!/bin/sh
set -e

# Aplica migrations automaticamente apenas se RUN_MIGRATIONS=true.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "run_migrations_enabled"
    attempts=0
    max_attempts=10
    until alembic upgrade head; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge "$max_attempts" ]; then
            echo "migrations_failed_after_${attempts}_attempts" >&2
            exit 1
        fi
        echo "migrations_failed_retry (${attempts}/${max_attempts})"
        sleep 3
    done
else
    echo "run_migrations_skipped"
fi

exec "$@"
