import sys
import os
import asyncio
from logging.config import fileConfig
import selectors
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Inject app path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.db.url import normalise
from app.models.domain import Base

# Imported for the side effect of registering their tables on Base.metadata.
# Without this, `alembic revision --autogenerate` would see them as missing and
# cheerfully write a migration that DROPS every one of them.
from app.models import credentials as _credentials_models  # noqa: F401
from app.models import security as _security_models  # noqa: F401

config = context.config

# Neon hands out a libpq URL that asyncpg cannot use as-is; normalise() fixes
# the scheme, strips sslmode/channel_binding and disables prepared statements
# on the -pooler endpoint. See app/db/url.py.
DATABASE_URL, CONNECT_ARGS = normalise(settings.DATABASE_URL)

# Only apply the Windows policy if the OS is actually Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# '%' is ConfigParser's interpolation character, so a password containing one
# would blow up here rather than at connect time. Escape it.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    # Built directly rather than from the ini section, so the TLS context and
    # PgBouncer settings in CONNECT_ARGS reach asyncpg. NullPool because a
    # migration run is one connection, used once.
    connectable = create_async_engine(
        DATABASE_URL,
        connect_args=CONNECT_ARGS,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()