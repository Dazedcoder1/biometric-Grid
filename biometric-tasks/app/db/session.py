from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from app.core.config import settings

# Convert the configured PostgreSQL URL to the asyncpg driver.
database_url = settings.DATABASE_URL

if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
elif database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql+asyncpg://", 1
    )

# asyncpg does not accept libpq parameters such as sslmode/channel_binding.
# Neon requires TLS, so remove those URL parameters and pass ssl=True.
db_url = make_url(database_url)
query = dict(db_url.query)
query.pop("sslmode", None)
query.pop("channel_binding", None)
db_url = db_url.set(query=query)

# Database Connection Pool
engine = create_async_engine(
    db_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": True},
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Provides a transactional scope around a series of operations."""
    async with AsyncSessionLocal() as session:
        yield session
