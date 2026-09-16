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

echo "Running database migrations..."

attempt=1
max_attempts=10

until alembic upgrade head; do
    if [ "$attempt" -ge "$max_attempts" ]; then
        echo "Migrations failed after ${max_attempts} attempts. Giving up."
        echo "The error above is the real one — it is not a timeout."
        exit 1
    fi
    echo "Attempt ${attempt}/${max_attempts} failed; retrying in 5s..."
    attempt=$((attempt + 1))
    sleep 5
done

echo "Migrations applied."
echo "Starting API..."

# exec so uvicorn becomes PID 1 and receives SIGTERM directly. Without it the
# shell holds PID 1, swallows the signal, and every `docker compose down`
# waits the full 10s timeout before killing the container.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
