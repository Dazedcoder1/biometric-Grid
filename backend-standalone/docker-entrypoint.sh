#!/bin/sh
set -e

echo "======================================"
echo " GridSphere IoT Core"
echo " Starting container..."
echo "======================================"

echo "Waiting for PostgreSQL..."

python - <<'PY'
import asyncio
import os
from urllib.parse import urlparse
import asyncpg

async def wait_for_db():
    url = os.environ["DATABASE_URL"]
    url = url.replace("postgresql+asyncpg://", "postgresql://")

    parsed = urlparse(url)

    while True:
        try:
            conn = await asyncpg.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path.lstrip("/")
            )
            await conn.close()

            print("PostgreSQL is ready.")
            break

        except Exception as e:
            print(f"PostgreSQL not ready: {e}")
            await asyncio.sleep(2)

asyncio.run(wait_for_db())
PY

echo "Running database migrations..."

alembic upgrade head

echo "Starting FastAPI..."

exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1