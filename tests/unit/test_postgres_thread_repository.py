"""Tests for PostgresThreadRepository (SQLAlchemy AsyncEngine adapter).

Mocks AsyncSession at the external boundary (database) by patching AsyncSession
so that each method-local session is a mock. Tests verify that the adapter
correctly translates domain operations into SQLAlchemy ORM calls and maps
results back to domain entities.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.thread import Thread
from src.domain.exceptions import ThreadNotFoundError


class TestPostgresThreadRepository:
    """Tests for PostgresThreadRepository with mocked AsyncSession."""

    @pytest.fixture
    def mock_session(self):
        """AsyncMock for SQLAlchemy AsyncSession used inside the context manager."""
        session = AsyncMock()
        session.add = MagicMock()
        session.expire = MagicMock()
        return session

    @pytest.fixture
    def mock_engine(self):
        """MagicMock for SQLAlchemy AsyncEngine."""
        return MagicMock()

    @pytest.fixture
    def repository(self, mock_engine, mock_session):
        """PostgresThreadRepository wired to a mocked engine.

        Patches AsyncSession so that `async with AsyncSession(engine)` yields the mock session.
        """
        from src.infrastructure.postgres_thread.adapter import PostgresThreadRepository

        repo = PostgresThreadRepository(engine=mock_engine)
        # Patch AsyncSession in the adapter module so method-local sessions use our mock
        patcher = patch(
            "src.infrastructure.postgres_thread.adapter.AsyncSession",
            return_value=mock_session,
        )
        patcher.start()
        # Configure mock_session as an async context manager
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        yield repo
        patcher.stop()

    # -- create ---------------------------------------------------------------

    async def test_create_returns_thread_with_empty_messages(self, repository):
        """create should return a Thread with the given agent_name and no messages."""
        result = await repository.create("test-agent")

        assert isinstance(result, Thread)
        assert result.agent_name == "test-agent"
        assert result.messages == []
        assert result.id is not None

    async def test_create_inserts_thread_model(self, repository, mock_session):
        """create should call session.add() and session.commit() to persist the thread."""
        await repository.create("test-agent")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    # -- get ------------------------------------------------------------------

    async def test_get_returns_thread_with_messages_ordered_by_timestamp(self, repository, mock_session):
        """get should return a Thread with messages ordered by timestamp (oldest first)."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        now = datetime.now(UTC)
        earlier = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        later = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-123"
        thread_model.agent_name = "test-agent"
        thread_model.created_at = now
        thread_model.updated_at = now

        msg1 = MagicMock(spec=MessageModel)
        msg1.role = "human"
        msg1.content = "First message"
        msg1.timestamp = later
        msg1.tool_calls = None
        msg1.status = None
        msg1.structured_response = None

        msg2 = MagicMock(spec=MessageModel)
        msg2.role = "ai"
        msg2.content = "Second message"
        msg2.timestamp = earlier
        msg2.tool_calls = None
        msg2.status = None
        msg2.structured_response = None

        thread_model.messages = [msg1, msg2]

        mock_session.get.return_value = thread_model

        result = await repository.get("thread-123")

        assert isinstance(result, Thread)
        assert result.id == "thread-123"
        assert result.agent_name == "test-agent"
        assert len(result.messages) == 2
        # Messages must be ordered by timestamp (oldest first)
        assert result.messages[0].content == "Second message"
        assert result.messages[1].content == "First message"
        mock_session.get.assert_awaited_once()

    async def test_get_thread_not_found_raises_thread_not_found_error(self, repository, mock_session):
        """get should raise ThreadNotFoundError when session.get returns None."""
        mock_session.get.return_value = None

        with pytest.raises(ThreadNotFoundError):
            await repository.get("nonexistent-id")

    # -- list_all -------------------------------------------------------------

    async def test_list_all_returns_empty_list_when_no_threads(self, repository, mock_session):
        """list_all should return an empty list when no threads exist."""
        # Mock session.execute to return a result with no rows
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await repository.list_all()

        assert result == []
        mock_session.execute.assert_awaited_once()

    async def test_list_all_returns_all_threads_with_messages(self, repository, mock_session):
        """list_all should return all threads, each mapped to a domain Thread with messages."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        now = datetime.now(UTC)

        thread1_model = MagicMock(spec=ThreadModel)
        thread1_model.id = "thread-1"
        thread1_model.agent_name = "agent-a"
        thread1_model.created_at = now
        thread1_model.updated_at = now

        msg1 = MagicMock(spec=MessageModel)
        msg1.role = "human"
        msg1.content = "Hello"
        msg1.timestamp = now
        msg1.tool_calls = None
        msg1.status = None
        msg1.structured_response = None
        thread1_model.messages = [msg1]

        thread2_model = MagicMock(spec=ThreadModel)
        thread2_model.id = "thread-2"
        thread2_model.agent_name = "agent-b"
        thread2_model.created_at = now
        thread2_model.updated_at = now
        thread2_model.messages = []

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [thread1_model, thread2_model]
        mock_session.execute.return_value = mock_result

        result = await repository.list_all()

        assert len(result) == 2
        assert all(isinstance(t, Thread) for t in result)
        assert result[0].id == "thread-1"
        assert result[0].agent_name == "agent-a"
        assert len(result[0].messages) == 1
        assert result[1].id == "thread-2"
        assert result[1].messages == []

    # -- delete ---------------------------------------------------------------

    async def test_delete_removes_thread(self, repository, mock_session):
        """delete should fetch the thread and call session.delete() + commit()."""
        from src.infrastructure.postgres_thread.models import ThreadModel

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-123"
        mock_session.get.return_value = thread_model

        await repository.delete("thread-123")

        mock_session.delete.assert_awaited_once_with(thread_model)
        mock_session.commit.assert_awaited_once()

    async def test_delete_thread_not_found_raises_error(self, repository, mock_session):
        """delete should raise ThreadNotFoundError when the thread does not exist."""
        mock_session.get.return_value = None

        with pytest.raises(ThreadNotFoundError):
            await repository.delete("nonexistent-id")

    # -- add_message ----------------------------------------------------------

    async def test_add_message_inserts_message_and_returns_updated_thread(self, repository, mock_session):
        """add_message should persist a new MessageModel and return the updated Thread."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        now = datetime.now(UTC)
        message = Message(role=MessageRole.HUMAN, content="Hello, world!", timestamp=now)

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-123"
        thread_model.agent_name = "test-agent"
        thread_model.created_at = now
        thread_model.updated_at = now
        thread_model.messages = []

        mock_session.get.return_value = thread_model

        new_msg = MagicMock(spec=MessageModel)
        new_msg.role = "human"
        new_msg.content = "Hello, world!"
        new_msg.timestamp = now
        new_msg.tool_calls = None
        new_msg.status = None
        new_msg.structured_response = None

        # After commit, execute(select(...)) re-fetches with messages loaded
        updated_model = MagicMock(spec=ThreadModel)
        updated_model.id = "thread-123"
        updated_model.agent_name = "test-agent"
        updated_model.created_at = now
        updated_model.updated_at = now
        updated_model.messages = [new_msg]
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = updated_model
        mock_session.execute.return_value = mock_result

        result = await repository.add_message("thread-123", message)

        assert isinstance(result, Thread)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited()
        assert len(result.messages) == 1
        assert result.messages[0].content == "Hello, world!"
        assert result.messages[0].role == MessageRole.HUMAN

    async def test_add_message_thread_not_found_raises_error(self, repository, mock_session):
        """add_message should raise ThreadNotFoundError when the thread does not exist."""
        mock_session.get.return_value = None
        message = Message(role=MessageRole.HUMAN, content="Hello")

        with pytest.raises(ThreadNotFoundError):
            await repository.add_message("nonexistent-id", message)

    async def test_add_message_updates_thread_updated_at(self, repository, mock_session):
        """add_message should update the thread's updated_at timestamp."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        old_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        message = Message(role=MessageRole.AI, content="Response")

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-123"
        thread_model.agent_name = "test-agent"
        thread_model.created_at = old_time
        thread_model.updated_at = old_time
        thread_model.messages = []

        new_msg = MagicMock(spec=MessageModel)
        new_msg.role = "ai"
        new_msg.content = "Response"
        new_msg.timestamp = message.timestamp
        new_msg.tool_calls = None
        new_msg.status = None
        new_msg.structured_response = None

        updated_model = MagicMock(spec=ThreadModel)
        updated_model.id = "thread-123"
        updated_model.agent_name = "test-agent"
        updated_model.created_at = old_time
        updated_model.updated_at = old_time
        updated_model.messages = [new_msg]
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = updated_model
        mock_session.execute.return_value = mock_result

        mock_session.get.return_value = thread_model

        await repository.add_message("thread-123", message)

        # Verify updated_at was changed on the model (it should not stay at old_time)
        assert thread_model.updated_at != old_time

    # -- serialization roundtrips ---------------------------------------------

    async def test_message_serialization_roundtrip_preserves_all_fields(self, repository, mock_session):
        """A message with all fields set should survive the domain -> model -> domain roundtrip."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        now = datetime.now(UTC)
        original_message = Message(
            role=MessageRole.AI,
            content="Analysis complete",
            timestamp=now,
            tool_calls=None,
            status=MessageStatus.COMPLETED,
            structured_response={"score": 95, "label": "pass"},
        )

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-456"
        thread_model.agent_name = "analyzer"
        thread_model.created_at = now
        thread_model.updated_at = now

        msg_model = MagicMock(spec=MessageModel)
        msg_model.role = "ai"
        msg_model.content = "Analysis complete"
        msg_model.timestamp = now
        msg_model.tool_calls = None
        msg_model.status = "completed"
        msg_model.structured_response = {"score": 95, "label": "pass"}

        updated_model = MagicMock(spec=ThreadModel)
        updated_model.id = "thread-456"
        updated_model.agent_name = "analyzer"
        updated_model.created_at = now
        updated_model.updated_at = now
        updated_model.messages = [msg_model]
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = updated_model
        mock_session.execute.return_value = mock_result

        mock_session.get.return_value = thread_model

        result = await repository.add_message("thread-456", original_message)

        roundtripped = result.messages[0]
        assert roundtripped.role == MessageRole.AI
        assert roundtripped.content == "Analysis complete"
        assert roundtripped.timestamp == now
        assert roundtripped.tool_calls is None
        assert roundtripped.status == MessageStatus.COMPLETED
        assert roundtripped.structured_response == {"score": 95, "label": "pass"}

    async def test_message_with_tool_calls_jsonb_survives_roundtrip(self, repository, mock_session):
        """A message with tool_calls (complex JSONB) should survive persistence roundtrip."""
        from src.infrastructure.postgres_thread.models import MessageModel, ThreadModel

        now = datetime.now(UTC)
        tool_calls_data = [
            {
                "name": "search_documents",
                "args": {"query": "python asyncio", "limit": 10},
                "id": "call_abc123",
            },
            {
                "name": "fetch_url",
                "args": {"url": "https://docs.python.org"},
                "id": "call_def456",
            },
        ]

        original_message = Message(
            role=MessageRole.AI,
            content="Let me search for that.",
            timestamp=now,
            tool_calls=tool_calls_data,
            status=None,
            structured_response=None,
        )

        thread_model = MagicMock(spec=ThreadModel)
        thread_model.id = "thread-789"
        thread_model.agent_name = "search-agent"
        thread_model.created_at = now
        thread_model.updated_at = now

        msg_model = MagicMock(spec=MessageModel)
        msg_model.role = "ai"
        msg_model.content = "Let me search for that."
        msg_model.timestamp = now
        msg_model.tool_calls = tool_calls_data
        msg_model.status = None
        msg_model.structured_response = None

        updated_model = MagicMock(spec=ThreadModel)
        updated_model.id = "thread-789"
        updated_model.agent_name = "search-agent"
        updated_model.created_at = now
        updated_model.updated_at = now
        updated_model.messages = [msg_model]
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = updated_model
        mock_session.execute.return_value = mock_result

        mock_session.get.return_value = thread_model

        result = await repository.add_message("thread-789", original_message)

        roundtripped = result.messages[0]
        assert roundtripped.tool_calls == tool_calls_data
        assert len(roundtripped.tool_calls) == 2
        assert roundtripped.tool_calls[0]["name"] == "search_documents"
        assert roundtripped.tool_calls[0]["args"]["query"] == "python asyncio"
        assert roundtripped.tool_calls[1]["id"] == "call_def456"
