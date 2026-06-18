"""Tests for PostgresAgentConfigRepository (SQLAlchemy AsyncEngine adapter).

Mocks AsyncSession at the external boundary by patching AsyncSession
so that each method-local session is a mock. Tests verify that the adapter
correctly translates domain operations into SQLAlchemy ORM calls and maps
results back to domain entities.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentNotFoundError


class TestPostgresAgentConfigRepository:
    @pytest.fixture
    def mock_session(self):
        """AsyncMock for SQLAlchemy AsyncSession used inside the context manager."""
        session = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def mock_engine(self):
        """MagicMock for SQLAlchemy AsyncEngine."""
        return MagicMock()

    @pytest.fixture
    def repository(self, mock_engine, mock_session):
        """PostgresAgentConfigRepository wired to a mocked engine.

        Patches AsyncSession so that `async with AsyncSession(engine)` yields the mock session.
        """
        from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository

        repo = PostgresAgentConfigRepository(engine=mock_engine)
        patcher = patch(
            "src.infrastructure.postgres_repository.adapter.AsyncSession",
            return_value=mock_session,
        )
        patcher.start()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        yield repo
        patcher.stop()

    @pytest.fixture
    def sample_metadata(self):
        """A valid AgentConfigMetadata instance for testing."""
        now = datetime.now(UTC)
        return AgentConfigMetadata(
            name="test-agent",
            model="claude-sonnet-4-5-20250929",
            minio_path="agent-configs/test-agent.yaml",
            created_at=now,
            updated_at=now,
        )

    # -- save --------------------------------------------------------------

    async def test_save_calls_merge_and_commit(self, repository, mock_session, sample_metadata):
        """save should call session.merge() and session.commit() to upsert the config."""
        await repository.save(sample_metadata)

        mock_session.merge.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    # -- get ---------------------------------------------------------------

    async def test_get_returns_metadata(self, repository, mock_session):
        """get should return AgentConfigMetadata when session.get returns a model."""
        from src.infrastructure.postgres_repository.models import AgentConfigModel

        now = datetime.now(UTC)
        model = MagicMock(spec=AgentConfigModel)
        model.name = "test-agent"
        model.model = "claude-sonnet-4-5-20250929"
        model.minio_path = "agent-configs/test-agent.yaml"
        model.created_at = now
        model.updated_at = now

        mock_session.get.return_value = model

        result = await repository.get("test-agent")

        assert isinstance(result, AgentConfigMetadata)
        assert result.name == "test-agent"
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.minio_path == "agent-configs/test-agent.yaml"
        mock_session.get.assert_awaited_once()

    async def test_get_not_found_raises(self, repository, mock_session):
        """get should raise AgentNotFoundError when session.get returns None."""
        mock_session.get.return_value = None

        with pytest.raises(AgentNotFoundError):
            await repository.get("nonexistent")

    # -- list_all ----------------------------------------------------------

    async def test_list_all_returns_list(self, repository, mock_session):
        """list_all should return a list of AgentConfigMetadata from ORM models."""
        from src.infrastructure.postgres_repository.models import AgentConfigModel

        now = datetime.now(UTC)

        model_a = MagicMock(spec=AgentConfigModel)
        model_a.name = "agent-a"
        model_a.model = "gpt-4o"
        model_a.minio_path = "agent-configs/agent-a.yaml"
        model_a.created_at = now
        model_a.updated_at = now

        model_b = MagicMock(spec=AgentConfigModel)
        model_b.name = "agent-b"
        model_b.model = "claude-sonnet-4-5-20250929"
        model_b.minio_path = "agent-configs/agent-b.yaml"
        model_b.created_at = now
        model_b.updated_at = now

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model_a, model_b]
        mock_session.execute.return_value = mock_result

        result = await repository.list_all()

        assert len(result) == 2
        assert all(isinstance(m, AgentConfigMetadata) for m in result)
        assert result[0].name == "agent-a"
        assert result[1].name == "agent-b"

    # -- delete ------------------------------------------------------------

    async def test_delete_removes_row(self, repository, mock_session):
        """delete should fetch the model via session.get and call session.delete + commit."""
        from src.infrastructure.postgres_repository.models import AgentConfigModel

        model = MagicMock(spec=AgentConfigModel)
        model.name = "test-agent"
        mock_session.get.return_value = model

        await repository.delete("test-agent")

        mock_session.delete.assert_awaited_once_with(model)
        mock_session.commit.assert_awaited_once()

    async def test_delete_not_found_raises(self, repository, mock_session):
        """delete should raise AgentNotFoundError when session.get returns None."""
        mock_session.get.return_value = None

        with pytest.raises(AgentNotFoundError):
            await repository.delete("nonexistent")

    # -- exists ------------------------------------------------------------

    async def test_exists_returns_true(self, repository, mock_session):
        """exists should return True when session.get returns a model."""
        from src.infrastructure.postgres_repository.models import AgentConfigModel

        mock_session.get.return_value = MagicMock(spec=AgentConfigModel)

        result = await repository.exists("test-agent")

        assert result is True
        mock_session.get.assert_awaited_once()

    async def test_exists_returns_false(self, repository, mock_session):
        """exists should return False when session.get returns None."""
        mock_session.get.return_value = None

        result = await repository.exists("nonexistent")

        assert result is False
