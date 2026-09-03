"""Asynchronous database engine, session factory, and schema initialization."""

import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.models import Base

logger = logging.getLogger("vault.database.session")

DEFAULT_DB_URL = "sqlite+aiosqlite:///vault.db"


def create_database_engine(
    db_url: str = DEFAULT_DB_URL,
    echo: bool = False,
) -> AsyncEngine:
    """Create and configure an asynchronous SQLAlchemy engine.

    Args:
        db_url: Database connection URL.
        echo: If True, logs all generated SQL statements.

    Returns:
        AsyncEngine instance.
    """
    return create_async_engine(
        db_url,
        echo=echo,
        future=True,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async sessionmaker factory bound to the provided engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def init_db(engine: AsyncEngine) -> None:
    """Initialize database tables and schemas asynchronously.

    Args:
        engine: The active AsyncEngine instance.
    """
    logger.info("Initializing database schemas and tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialization complete.")


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide an asynchronous transactional session generator."""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
