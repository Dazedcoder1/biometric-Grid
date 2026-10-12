#!/bin/sh
set -e

echo "======================================"
echo " GridSphere IoT Core"
echo "======================================"

# Deliberately no "wait for Postgres" socket poll here.
#
# The legacy entrypoint opened a raw asyncpg connection in a loop until it
# succeeded. Against Neon that loop never exits: Neon requires TLS, and
# asyncpg.connect() without an ssl argument attempts a plaintext connection,
# which the server refuses. The check would fail forever against a database
# that was perfectly healthy.
#
# `alembic upgrade head` is its own readiness check — it has to connect
# anyway, and it goes through app/db/url.py, which attaches TLS and handles
# the -pooler endpoint correctly. So retry that instead. Neon suspends idle
# compute and takes a second or two to wake, hence more than one attempt.

# Which database this container will use, password hidden. When the .env on
# the server points somewhere unexpected — an old Neon endpoint, a branch
# that was deleted — this line says so before anything else happens.
echo "Database: $(python -c 'from app.core.config import settings; from app.db.url import describe; print(describe(settings.DATABASE_URL))' 2>/dev/null || echo '(DATABASE_URL could not be read)')"

echo "Running database migrations..."

attempt=1
max_attempts=10

until alembic upgrade head > /tmp/alembic.log 2>&1; do
    cat /tmp/alembic.log
    # A wrong password does not get better by waiting. Say what to fix and
    # stop, instead of ten identical tracebacks.
    if grep -q "password authentication failed" /tmp/alembic.log; then
        echo ""
        echo "================================================================="
        echo " The database rejected the password in DATABASE_URL."
        echo ""
        echo " Fix: put the current connection string from the Neon console"
        echo " (Connect -> pooled) into DATABASE_URL in the .env next to"
        echo " docker-compose.yml, then run:"
        echo "     docker compose up -d --force-recreate backend"
        echo " (restart is not enough - it keeps the old value.)"
        echo " Also check no DATABASE_URL is exported in your shell: env | grep DATABASE_URL"
        echo "================================================================="
        exit 1
    fi
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Migrations failed after ${max_attempts} attempts. Giving up."
        echo "The error above is the real one — it is not a timeout."
        exit 1
    fi
    echo "Attempt ${attempt}/${max_attempts} failed; retrying in 5s..."
    attempt=$((attempt + 1))
    sleep 5
done

cat /tmp/alembic.log
echo "Migrations applied."
echo "Starting API..."

# exec so uvicorn becomes PID 1 and receives SIGTERM directly. Without it the
# shell holds PID 1, swallows the signal, and every `docker compose down`
# waits the full 10s timeout before killing the container.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
