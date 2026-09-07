import sqlalchemy.ext.asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Database Connection Pool
engine = create_async_engine(
    settings.DATABASE_URL, 
    pool_size=20, 
    max_overflow=10,
    pool_pre_ping=True
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """Provides a transactional scope around a series of operations."""
    async with AsyncSessionLocal() as session:
        yield session