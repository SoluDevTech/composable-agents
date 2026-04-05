"""Tests for PostgresAgentConfigRepository (PostgreSQL adapter).

Mocks asyncpg.Pool at the external boundary.
Tests verify that the adapter correctly translates domain operations
into SQL queries against the pool.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.exceptions import AgentNotFoundError
from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository


class TestPostgresAgentConfigRepository:
    @pytest.fixture
    def mock_pool(self):
        """AsyncMock for the asyncpg connection pool."""
        return AsyncMock()

    @pytest.fixture
    def repository(self, mock_pool):
        """PostgresAgentConfigRepository wired to a mocked pool."""
        return PostgresAgentConfigRepository(pool=mock_pool)

    @pytest.fixture
    def sample_metadata(self):
        """A valid AgentConfigMetadata instance for testing."""
        now = datetime.now(UTC)
        return AgentConfigMetadata(
            name="test-agent",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/test-agent.yaml",
            is_builtin=False,
            created_at=now,
            updated_at=now,
        )

    # -- save --------------------------------------------------------------

    async def test_save_executes_upsert(self, repository, mock_pool, sample_metadata):
        """save should execute an upsert SQL statement with correct parameters."""
        await repository.save(sample_metadata)

        mock_pool.execute.assert_awaited_once()
        call_args = mock_pool.execute.call_args
        sql = call_args[0][0]
        assert "INSERT" in sql.upper() or "UPSERT" in sql.upper() or "ON CONFLICT" in sql.upper()

    # -- get ---------------------------------------------------------------

    async def test_get_returns_metadata(self, repository, mock_pool):
        """get should return AgentConfigMetadata when fetchrow returns data."""
        now = datetime.now(UTC)
        mock_pool.fetchrow.return_value = {
            "name": "test-agent",
            "model": "claude-sonnet-4-5-20250929",
            "minio_path": "agent-configs/test-agent.yaml",
            "is_builtin": False,
            "created_at": now,
            "updated_at": now,
        }

        result = await repository.get("test-agent")

        assert isinstance(result, AgentConfigMetadata)
        assert result.name == "test-agent"
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.minio_path == "agent-configs/test-agent.yaml"
        mock_pool.fetchrow.assert_awaited_once()

    async def test_get_not_found_raises(self, repository, mock_pool):
        """get should raise AgentNotFoundError when fetchrow returns None."""
        mock_pool.fetchrow.return_value = None

        with pytest.raises(AgentNotFoundError):
            await repository.get("nonexistent")

    # -- list_all ----------------------------------------------------------

    async def test_list_all_returns_list(self, repository, mock_pool):
        """list_all should return a list of AgentConfigMetadata from rows."""
        now = datetime.now(UTC)
        mock_pool.fetch.return_value = [
            {
                "name": "agent-a",
                "model": "gpt-4o",
                "minio_path": "agent-configs/agent-a.yaml",
                "is_builtin": False,
                "created_at": now,
                "updated_at": now,
            },
            {
                "name": "agent-b",
                "model": "claude-sonnet-4-5-20250929",
                "minio_path": "agent-configs/agent-b.yaml",
                "is_builtin": True,
                "created_at": now,
                "updated_at": now,
            },
        ]

        result = await repository.list_all()

        assert len(result) == 2
        assert all(isinstance(m, AgentConfigMetadata) for m in result)
        assert result[0].name == "agent-a"
        assert result[1].name == "agent-b"
        assert result[1].is_builtin is True

    # -- delete ------------------------------------------------------------

    async def test_delete_removes_row(self, repository, mock_pool):
        """delete should execute DELETE and succeed when a row is affected."""
        mock_pool.execute.return_value = "DELETE 1"

        await repository.delete("test-agent")

        mock_pool.execute.assert_awaited_once()

    async def test_delete_not_found_raises(self, repository, mock_pool):
        """delete should raise AgentNotFoundError when no rows are affected."""
        mock_pool.execute.return_value = "DELETE 0"

        with pytest.raises(AgentNotFoundError):
            await repository.delete("nonexistent")

    # -- exists ------------------------------------------------------------

    async def test_exists_returns_true(self, repository, mock_pool):
        """exists should return True when fetchval returns True."""
        mock_pool.fetchval.return_value = True

        result = await repository.exists("test-agent")

        assert result is True
        mock_pool.fetchval.assert_awaited_once()

    async def test_exists_returns_false(self, repository, mock_pool):
        """exists should return False when fetchval returns False."""
        mock_pool.fetchval.return_value = False

        result = await repository.exists("nonexistent")

        assert result is False
