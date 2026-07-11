"""Shared pytest fixtures for the composable-agents test suite.

Uses real internal implementations (PostgresThreadRepository backed by in-memory
SQLite, YamlAgentConfigLoader, NoopTracingProvider). External adapters are mocked
via tests/fixtures/external.py.
"""

import os

# Provide a DATABASE_URL so Settings() (instantiated at import time in
# src.dependencies) can validate. Tests that need a real engine use the
# in-memory SQLite db_engine fixture, not this value.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.database.models.base import Base
from src.infrastructure.postgres_thread.adapter import PostgresThreadRepository
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

# Re-export external fixtures so they are available to all tests
pytest_plugins = ["tests.fixtures.external"]


@pytest_asyncio.fixture
async def db_engine():
    """Provide a real in-memory SQLite async engine for each test.

    Yields:
        An AsyncEngine backed by sqlite+aiosqlite:///:memory:.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a real in-memory SQLite session for each test.

    Yields:
        An AsyncSession.
    """
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def thread_repo(db_engine) -> PostgresThreadRepository:
    """Provide a real PostgresThreadRepository backed by in-memory SQLite.

    This replaces the former InMemoryThreadRepository fake. Tests use a real
    internal repository implementation per the test-writer-python conventions.
    """
    return PostgresThreadRepository(engine=db_engine)


@pytest.fixture
def yaml_loader() -> YamlAgentConfigLoader:
    """Provide a real YamlAgentConfigLoader for each test."""
    return YamlAgentConfigLoader()


@pytest.fixture
def noop_tracing() -> NoopTracingProvider:
    """Provide a real NoopTracingProvider for each test."""
    return NoopTracingProvider()
