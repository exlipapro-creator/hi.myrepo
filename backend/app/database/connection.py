"""
hi.myrepo - Database Connection Management

Provides async and sync database sessions using SQLAlchemy.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self):
        settings = get_settings()
        self._async_engine = None
        self._async_session_factory = None
        self._sync_engine = None
        self._sync_session_factory = None
        self._settings = settings

    def _init_async_engine(self):
        if self._async_engine is None and self._settings.async_database_url:
            connect_args = {}
            if not self._settings.database_ssl:
                connect_args["ssl"] = False

            self._async_engine = create_async_engine(
                self._settings.async_database_url,
                pool_size=self._settings.database_pool_size,
                max_overflow=self._settings.database_max_overflow,
                echo=self._settings.app_debug,
                connect_args=connect_args,
            )
            self._async_session_factory = async_sessionmaker(
                bind=self._async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

    def _init_sync_engine(self):
        if self._sync_engine is None and self._settings.sync_database_url:
            connect_args = {}
            if not self._settings.database_ssl:
                connect_args["ssl"] = False

            self._sync_engine = create_engine(
                self._settings.sync_database_url,
                pool_size=self._settings.database_pool_size,
                max_overflow=self._settings.database_max_overflow,
                echo=self._settings.app_debug,
                connect_args=connect_args,
            )
            self._sync_session_factory = sessionmaker(
                bind=self._sync_engine,
                expire_on_commit=False,
            )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session with automatic commit/rollback."""
        self._init_async_engine()
        if self._async_session_factory is None:
            raise RuntimeError("Database not configured. Set DATABASE_URL.")

        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def get_sync_session(self) -> Session:
        """Get a synchronous database session (for migrations, tests)."""
        self._init_sync_engine()
        if self._sync_session_factory is None:
            raise RuntimeError("Database not configured. Set DATABASE_URL.")
        return self._sync_session_factory()

    async def close(self):
        """Close all database connections."""
        if self._async_engine:
            await self._async_engine.dispose()
            self._async_engine = None
            self._async_session_factory = None

    async def health_check(self) -> bool:
        """Verify database connectivity."""
        try:
            self._init_async_engine()
            if self._async_engine is None:
                return False
            async with self._async_engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )
            return True
        except Exception:
            return False


# Global database manager singleton
db_manager = DatabaseManager()
