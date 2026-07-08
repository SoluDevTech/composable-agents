"""Tests for PostgresThreadRepository against a real in-memory SQLite engine."""

from datetime import UTC, datetime

import pytest

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.thread import Thread
from src.domain.errors.thread import ThreadNotFoundError


class TestPostgresThreadRepository:
    async def test_create_returns_thread_with_empty_messages(self, thread_repo):
        # Act
        result = await thread_repo.create("test-agent")

        # Assert
        assert isinstance(result, Thread)
        assert result.agent_name == "test-agent"
        assert result.messages == []
        assert result.id is not None

    async def test_get_returns_persisted_thread_with_messages(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        await thread_repo.add_message(created.id, Message(role=MessageRole.HUMAN, content="hello"))

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        assert isinstance(result, Thread)
        assert result.id == created.id
        assert result.agent_name == "test-agent"
        assert len(result.messages) == 1
        assert result.messages[0].content == "hello"

    async def test_get_not_found_raises(self, thread_repo):
        # Arrange
        # (no thread)

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get("nonexistent-id")

    async def test_list_all_returns_all_threads(self, thread_repo):
        # Arrange
        await thread_repo.create("agent-a")
        await thread_repo.create("agent-b")

        # Act
        result = await thread_repo.list_all()

        # Assert
        assert len(result) == 2
        assert all(isinstance(t, Thread) for t in result)
        agent_names = {t.agent_name for t in result}
        assert agent_names == {"agent-a", "agent-b"}

    async def test_list_all_returns_empty_when_no_threads(self, thread_repo):
        # Arrange
        # (no threads)

        # Act
        result = await thread_repo.list_all()

        # Assert
        assert result == []

    async def test_delete_removes_thread(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")

        # Act
        await thread_repo.delete(created.id)

        # Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.get(created.id)

    async def test_delete_not_found_raises(self, thread_repo):
        # Arrange
        # (no thread)

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.delete("nonexistent-id")

    async def test_add_message_returns_updated_thread(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        message = Message(role=MessageRole.HUMAN, content="Hello, world!")

        # Act
        result = await thread_repo.add_message(created.id, message)

        # Assert
        assert isinstance(result, Thread)
        assert len(result.messages) == 1
        assert result.messages[0].content == "Hello, world!"
        assert result.messages[0].role == MessageRole.HUMAN

    async def test_add_message_not_found_raises(self, thread_repo):
        # Arrange
        message = Message(role=MessageRole.HUMAN, content="Hello")

        # Act / Assert
        with pytest.raises(ThreadNotFoundError):
            await thread_repo.add_message("nonexistent-id", message)

    async def test_add_message_orders_messages_by_timestamp(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        earlier = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        later = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        await thread_repo.add_message(created.id, Message(role=MessageRole.AI, content="late", timestamp=later))
        await thread_repo.add_message(created.id, Message(role=MessageRole.HUMAN, content="early", timestamp=earlier))

        # Act
        result = await thread_repo.get(created.id)

        # Assert
        assert [m.content for m in result.messages] == ["early", "late"]

    async def test_add_message_updates_thread_updated_at(self, thread_repo):
        # Arrange
        created = await thread_repo.create("test-agent")
        before = (await thread_repo.get(created.id)).updated_at
        message = Message(role=MessageRole.AI, content="Response")

        # Act
        await thread_repo.add_message(created.id, message)

        # Assert
        after = (await thread_repo.get(created.id)).updated_at
        assert after >= before

    async def test_message_serialization_roundtrip_preserves_all_fields(self, thread_repo):
        # Arrange
        created = await thread_repo.create("analyzer")
        now = datetime.now(UTC)
        original = Message(
            role=MessageRole.AI,
            content="Analysis complete",
            timestamp=now,
            tool_calls=None,
            status=MessageStatus.COMPLETED,
            structured_response={"score": 95, "label": "pass"},
        )

        # Act
        await thread_repo.add_message(created.id, original)
        result = await thread_repo.get(created.id)

        # Assert
        roundtripped = result.messages[0]
        assert roundtripped.role == MessageRole.AI
        assert roundtripped.content == "Analysis complete"
        assert roundtripped.status == MessageStatus.COMPLETED
        assert roundtripped.structured_response == {"score": 95, "label": "pass"}

    async def test_message_with_tool_calls_jsonb_survives_roundtrip(self, thread_repo):
        # Arrange
        created = await thread_repo.create("search-agent")
        tool_calls_data = [
            {"name": "search_documents", "args": {"query": "python asyncio", "limit": 10}, "id": "call_abc123"},
            {"name": "fetch_url", "args": {"url": "https://docs.python.org"}, "id": "call_def456"},
        ]
        original = Message(
            role=MessageRole.AI,
            content="Let me search for that.",
            tool_calls=tool_calls_data,
        )

        # Act
        await thread_repo.add_message(created.id, original)
        result = await thread_repo.get(created.id)

        # Assert
        roundtripped = result.messages[0]
        assert roundtripped.tool_calls == tool_calls_data
        assert roundtripped.tool_calls[0]["args"]["query"] == "python asyncio"
        assert roundtripped.tool_calls[1]["id"] == "call_def456"
