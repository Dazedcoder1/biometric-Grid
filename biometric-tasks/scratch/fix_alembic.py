
import sys
import os
import asyncio
from sqlalchemy import text

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add the project root to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.db.session import engine

async def fix_alembic():
    print("Updating alembic_version to 90405d9757e0...")
    try:
        async with engine.begin() as conn:
            # Delete old version and insert current local head
            await conn.execute(text("DELETE FROM alembic_version"))
            await conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('90405d9757e0')"))
            print("Successfully updated alembic_version.")
    except Exception as e:
        print(f"Error updating alembic_version: {e}")

if __name__ == "__main__":
    asyncio.run(fix_alembic())
