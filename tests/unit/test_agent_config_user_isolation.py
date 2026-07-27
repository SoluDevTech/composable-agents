"""Tests for per-user isolation in :class:`PostgresAgentConfigRepository`.

Same pattern as ``test_thread_user_isolation.py``: the repository reads
``current_user_id`` and filters / sets ``user_id`` accordingly. When the
contextvar is ``None`` no filter is applied (existing behaviour preserved).
"""

from datetime import UTC, datetime

import pytest

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentNotFoundError
from src.infrastructure.database.rls_context import current_user_id
from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository


def _metadata(name: str = "test-agent") -> AgentConfigMetadata:
    now = datetime.now(UTC)
    return AgentConfigMetadata(
        name=name,
        model="claude-sonnet-4-5",
        minio_path=f"agent-configs/{name}.yaml",
        created_at=now,
        updated_at=now,
    )


class TestAgentConfigUserIsolation:
    """Per-user filtering driven by the ``current_user_id`` contextvar."""

    @pytest.fixture
    def repository(self, db_engine) -> PostgresAgentConfigRepository:
        return PostgresAgentConfigRepository(engine=db_engine)

    async def test_save_sets_user_id_from_contextvar(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok)

        # Act — re-read under uA
        tok2 = current_user_id.set("uA")
        try:
            refetched = await repository.get("agent-a")
        finally:
            current_user_id.reset(tok2)

        # Assert
        assert refetched.user_id == "uA"

    async def test_list_under_uB_excludes_uA_config(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok)

        # Act
        tok_b = current_user_id.set("uB")
        try:
            configs = await repository.list_all()
        finally:
            current_user_id.reset(tok_b)

        # Assert
        assert configs == []

    async def test_get_under_uB_raises_AgentNotFoundError_for_uA_config(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok)

        # Act / Assert
        tok_b = current_user_id.set("uB")
        try:
            with pytest.raises(AgentNotFoundError):
                await repository.get("agent-a")
        finally:
            current_user_id.reset(tok_b)

    async def test_exists_under_uB_returns_false_for_uA_config(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok)

        # Act
        tok_b = current_user_id.set("uB")
        try:
            exists = await repository.exists("agent-a")
        finally:
            current_user_id.reset(tok_b)

        # Assert
        assert exists is False

    async def test_exists_under_uA_returns_true_for_uA_config(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
            exists = await repository.exists("agent-a")
        finally:
            current_user_id.reset(tok)

        # Assert
        assert exists is True

    async def test_delete_under_uB_raises_for_uA_config(self, repository):
        # Arrange
        tok = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok)

        # Act / Assert
        tok_b = current_user_id.set("uB")
        try:
            with pytest.raises(AgentNotFoundError):
                await repository.delete("agent-a")
        finally:
            current_user_id.reset(tok_b)

        # The config is still visible to uA
        tok_a = current_user_id.set("uA")
        try:
            refetched = await repository.get("agent-a")
        finally:
            current_user_id.reset(tok_a)
        assert refetched.name == "agent-a"

    async def test_list_with_no_contextvar_returns_all(self, repository):
        # Arrange — create under uA and uB
        tok_a = current_user_id.set("uA")
        try:
            await repository.save(_metadata("agent-a"))
        finally:
            current_user_id.reset(tok_a)

        tok_b = current_user_id.set("uB")
        try:
            await repository.save(_metadata("agent-b"))
        finally:
            current_user_id.reset(tok_b)

        # Act — no contextvar
        assert current_user_id.get() is None
        configs = await repository.list_all()

        # Assert — all visible (no filter)
        assert len(configs) == 2

    async def test_save_with_no_contextvar_defaults_to_empty_user_id(self, repository):
        # Arrange
        assert current_user_id.get() is None
        # Act
        await repository.save(_metadata("agent-x"))
        # Assert — re-read without contextvar
        refetched = await repository.get("agent-x")
        assert refetched.user_id == ""

    async def test_agent_config_metadata_entity_has_user_id_field(self):
        # Arrange / Act
        m = _metadata("agent-y")
        # Assert
        assert hasattr(m, "user_id")
        assert m.user_id == ""
