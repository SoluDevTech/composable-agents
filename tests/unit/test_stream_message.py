"""Tests for StreamMessageUseCase.

Uses real InMemoryThreadRepository (internal).
Uses AsyncMock for AgentRunner (external - calls LLM).
"""

from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.ports.agent_runner import AgentRunner


class TestIsDuplicateHumanMessage:
    def test_true_when_last_is_human_same_content_no_status(self):
        messages = [Message(role=MessageRole.HUMAN, content="Hello")]
        assert StreamMessageUseCase._is_duplicate_human_message(messages, "Hello") is True

    def test_false_when_last_is_human_different_content(self):
        messages = [Message(role=MessageRole.HUMAN, content="Hello")]
        assert StreamMessageUseCase._is_duplicate_human_message(messages, "World") is False

    def test_false_when_last_is_human_with_status(self):
        messages = [Message(role=MessageRole.HUMAN, content="Hello", status=MessageStatus.COMPLETED)]
        assert StreamMessageUseCase._is_duplicate_human_message(messages, "Hello") is False

    def test_false_when_last_is_ai(self):
        messages = [Message(role=MessageRole.AI, content="Hello")]
        assert StreamMessageUseCase._is_duplicate_human_message(messages, "Hello") is False

    def test_false_when_empty_messages(self):
        assert StreamMessageUseCase._is_duplicate_human_message([], "Hello") is False

    def test_false_when_mixed_messages_last_is_ai(self):
        messages = [
            Message(role=MessageRole.HUMAN, content="Hello"),
            Message(role=MessageRole.AI, content="Hi there"),
        ]
        assert StreamMessageUseCase._is_duplicate_human_message(messages, "Hello") is False


class TestStreamMessageUseCase:
    @pytest.fixture
    def runner(self):
        mock = AsyncMock(spec=AgentRunner)

        async def _stream_with_message(_thread_id, _message):
            yield StreamEvent(type=StreamEventType.CONTENT, data="Hi")
            yield StreamEvent(
                type=StreamEventType.MESSAGE,
                data=Message(
                    role=MessageRole.AI,
                    content="Hi",
                    status=MessageStatus.COMPLETED,
                ).model_dump_json(),
            )

        mock.stream_with_message = _stream_with_message
        return mock

    @pytest.fixture
    def registry(self, runner):
        mock = AsyncMock()
        mock.get_runner.return_value = runner
        return mock

    async def test_execute_skips_duplicate_human_message(self, registry, thread_repo):
        thread = await thread_repo.create("test-agent")
        await thread_repo.add_message(thread.id, Message(role=MessageRole.HUMAN, content="Hello"))

        use_case = StreamMessageUseCase(registry, thread_repo)

        events = []
        async for event in use_case.execute(thread.id, "Hello"):
            events.append(event)

        updated = await thread_repo.get(thread.id)
        human_msgs = [m for m in updated.messages if m.role == MessageRole.HUMAN]
        assert len(human_msgs) == 1
