import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger("parceltrack.db")

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args={
        "server_settings": {
            # Kill queries that run longer than DB_STATEMENT_TIMEOUT_MS milliseconds.
            # Prevents runaway queries from holding connections indefinitely.
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
        }
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            logger.error("Database session error, rolling back", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()
