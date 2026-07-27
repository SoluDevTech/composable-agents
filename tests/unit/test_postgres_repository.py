"""Tests for PostgresAgentConfigRepository against a real in-memory SQLite engine."""

from datetime import UTC, datetime

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentNotFoundError
from src.infrastructure.database.models.agent_config import AgentConfigModel
from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository


def _metadata(name: str = "test-agent", description: str | None = None) -> AgentConfigMetadata:
    now = datetime.now(UTC)
    return AgentConfigMetadata(
        name=name,
        model="claude-sonnet-4-5-20250929",
        minio_path=f"agent-configs/{name}.yaml",
        created_at=now,
        updated_at=now,
        description=description,
    )


class TestPostgresAgentConfigRepository:
    @pytest.fixture
    def repository(self, db_engine):
        return PostgresAgentConfigRepository(engine=db_engine)

    async def test_save_then_get_returns_metadata(self, repository):
        # Arrange
        metadata = _metadata("test-agent")

        # Act
        await repository.save(metadata)
        result = await repository.get("test-agent")

        # Assert
        assert isinstance(result, AgentConfigMetadata)
        assert result.name == "test-agent"
        assert result.model == "claude-sonnet-4-5-20250929"
        assert result.minio_path == "agent-configs/test-agent.yaml"

    async def test_get_not_found_raises(self, repository):
        # Arrange
        # (no rows)

        # Act / Assert
        with pytest.raises(AgentNotFoundError):
            await repository.get("nonexistent")

    async def test_list_all_returns_saved_metadata(self, repository):
        # Arrange
        await repository.save(_metadata("agent-a"))
        await repository.save(_metadata("agent-b"))

        # Act
        result = await repository.list_all()

        # Assert
        assert len(result) == 2
        assert all(isinstance(m, AgentConfigMetadata) for m in result)
        assert result[0].name == "agent-a"
        assert result[1].name == "agent-b"

    async def test_list_all_returns_empty_when_no_rows(self, repository):
        # Arrange
        # (no rows)

        # Act
        result = await repository.list_all()

        # Assert
        assert result == []

    async def test_delete_removes_row(self, repository):
        # Arrange
        await repository.save(_metadata("test-agent"))

        # Act
        await repository.delete("test-agent")

        # Assert
        with pytest.raises(AgentNotFoundError):
            await repository.get("test-agent")

    async def test_delete_not_found_raises(self, repository):
        # Arrange
        # (no rows)

        # Act / Assert
        with pytest.raises(AgentNotFoundError):
            await repository.delete("nonexistent")

    async def test_exists_returns_true_after_save(self, repository):
        # Arrange
        await repository.save(_metadata("test-agent"))

        # Act
        result = await repository.exists("test-agent")

        # Assert
        assert result is True

    async def test_exists_returns_false_when_missing(self, repository):
        # Arrange
        # (no rows)

        # Act
        result = await repository.exists("nonexistent")

        # Assert
        assert result is False

    async def test_save_upserts_existing_row(self, repository):
        # Arrange
        await repository.save(_metadata("test-agent"))
        updated = AgentConfigMetadata(
            name="test-agent",
            model="gpt-4o",
            minio_path="agent-configs/test-agent.yaml",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Act
        await repository.save(updated)
        result = await repository.get("test-agent")

        # Assert
        assert result.model == "gpt-4o"

    # ------------------------------------------------------------------
    # New: description column mapping + persistence.
    # ------------------------------------------------------------------

    async def test_maps_description_from_model_to_metadata(self, repository, db_session):
        """Should map the ORM description column into AgentConfigMetadata."""
        # Arrange
        from sqlalchemy import insert

        now = datetime.now(UTC)
        await db_session.execute(
            insert(AgentConfigModel).values(
                name="desc-agent",
                model="claude-sonnet-4-5-20250929",
                minio_path="agent-configs/desc-agent.yaml",
                created_at=now,
                updated_at=now,
                description="A described agent",
            )
        )
        await db_session.commit()

        # Act
        result = await repository.get("desc-agent")

        # Assert
        assert result.description == "A described agent"

    async def test_save_persists_description(self, repository, db_session):
        """Should persist the metadata description into the ORM description column."""
        # Arrange
        from sqlalchemy import select

        metadata = _metadata("desc-agent", description="Persisted description")

        # Act
        await repository.save(metadata)

        # Assert — read the raw ORM row to confirm the column was written
        result = await db_session.execute(select(AgentConfigModel).where(AgentConfigModel.name == "desc-agent"))
        model = result.scalar_one()
        assert model.description == "Persisted description"
