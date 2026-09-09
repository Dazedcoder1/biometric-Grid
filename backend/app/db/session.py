import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.url import describe, normalise

logger = logging.getLogger(__name__)

DATABASE_URL, CONNECT_ARGS = normalise(settings.DATABASE_URL)

logger.info("Database: %s", describe(settings.DATABASE_URL))

# Pool sized for a hosted database rather than a local one. Neon's free compute
# allows far fewer concurrent connections than a local Postgres, and every idle
# connection keeps the compute awake and billable.
#
# pool_recycle matters here: Neon suspends compute after ~5 minutes idle, which
# silently kills open sockets. pool_pre_ping catches the dead ones on checkout,
# pool_recycle retires them before they get that far.
engine = create_async_engine(
    DATABASE_URL,
    connect_args=CONNECT_ARGS,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=280,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Provides a transactional scope around a series of operations."""
    async with AsyncSessionLocal() as session:
        yield session
