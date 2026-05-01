import logging
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session

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


# ── After-commit outbox ───────────────────────────────────────────────────────
# Side effects that depend on persisted state (e.g. dispatching a Celery task
# that re-reads a row) must not fire if the caller's transaction rolls back.
# Callbacks queued via `enqueue_after_commit` run only after a successful
# commit; on rollback the queue is dropped.


_OUTBOX_KEY = "_after_commit_callbacks"


def enqueue_after_commit(session: AsyncSession, callback: Callable[[], None]) -> None:
    """Run `callback()` after the session's outermost transaction commits."""
    session.sync_session.info.setdefault(_OUTBOX_KEY, []).append(callback)


@event.listens_for(Session, "after_commit")
def _run_after_commit_callbacks(session: Session) -> None:
    callbacks = session.info.pop(_OUTBOX_KEY, None)
    if not callbacks:
        return
    for cb in callbacks:
        try:
            cb()
        except Exception:
            logger.exception("after_commit callback failed")


@event.listens_for(Session, "after_rollback")
def _drop_after_commit_callbacks(session: Session) -> None:
    session.info.pop(_OUTBOX_KEY, None)
