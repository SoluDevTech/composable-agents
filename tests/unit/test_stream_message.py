"""Tests for StreamMessageUseCase.

Uses real PostgresThreadRepository (internal, from conftest).
Uses mock_agent_runner (external LLM boundary, from external.py).
A small real fake registry wraps the mock runner.
"""

from collections.abc import AsyncIterator

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.stream_event import StreamEvent, StreamEventType
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner


class _FakeRegistry(AgentRegistry):
    """Real in-test registry that returns a single runner."""

    def __init__(self, runner: AgentRunner) -> None:
        self._runner = runner

    async def get_runner(self, agent_name: str) -> AgentRunner:  # noqa: ARG002
        return self._runner

    async def list_agents(self) -> list[str]:
        return ["test-agent"]

    async def invalidate(self, agent_name: str) -> None:
        pass

    async def close(self) -> None:
        pass


class TestStreamMessageUseCase:
    def _build_runner(self, mock_agent_runner) -> AgentRunner:
        async def _stream_with_message(
            _thread_id: str, _message: str
        ) -> AsyncIterator[StreamEvent]:
            yield StreamEvent(type=StreamEventType.CONTENT, data="Hi")
            yield StreamEvent(
                type=StreamEventType.MESSAGE,
                data=Message(
                    role=MessageRole.AI,
                    content="Hi",
                    status=MessageStatus.COMPLETED,
                ).model_dump_json(),
            )

        mock_agent_runner.stream_with_message = _stream_with_message
        return mock_agent_runner

    async def test_execute_streams_events_and_persists_ai_message(self, mock_agent_runner, thread_repo):
        # Arrange
        runner = self._build_runner(mock_agent_runner)
        registry = _FakeRegistry(runner)
        use_case = StreamMessageUseCase(registry, thread_repo)
        thread = await thread_repo.create("test-agent")

        # Act
        events = [event async for event in use_case.execute(thread.id, "Hello")]

        # Assert
        assert len(events) == 2
        assert events[0].type == StreamEventType.CONTENT
        assert events[1].type == StreamEventType.MESSAGE

    async def test_execute_persists_final_ai_message(self, mock_agent_runner, thread_repo):
        # Arrange
        runner = self._build_runner(mock_agent_runner)
        registry = _FakeRegistry(runner)
        use_case = StreamMessageUseCase(registry, thread_repo)
        thread = await thread_repo.create("test-agent")

        # Act
        _ = [event async for event in use_case.execute(thread.id, "Hello")]

        # Assert
        updated = await thread_repo.get(thread.id)
        ai_msgs = [m for m in updated.messages if m.role == MessageRole.AI]
        assert len(ai_msgs) == 1
        assert ai_msgs[0].content == "Hi"

    async def test_execute_persists_human_message_when_not_duplicate(self, mock_agent_runner, thread_repo):
        # Arrange
        runner = self._build_runner(mock_agent_runner)
        registry = _FakeRegistry(runner)
        use_case = StreamMessageUseCase(registry, thread_repo)
        thread = await thread_repo.create("test-agent")

        # Act
        _ = [event async for event in use_case.execute(thread.id, "Hello")]

        # Assert
        updated = await thread_repo.get(thread.id)
        human_msgs = [m for m in updated.messages if m.role == MessageRole.HUMAN]
        assert len(human_msgs) == 1

    async def test_execute_skips_duplicate_human_message(self, mock_agent_runner, thread_repo):
        # Arrange
        runner = self._build_runner(mock_agent_runner)
        registry = _FakeRegistry(runner)
        use_case = StreamMessageUseCase(registry, thread_repo)
        thread = await thread_repo.create("test-agent")
        await thread_repo.add_message(thread.id, Message(role=MessageRole.HUMAN, content="Hello"))

        # Act
        _ = [event async for event in use_case.execute(thread.id, "Hello")]

        # Assert
        updated = await thread_repo.get(thread.id)
        human_msgs = [m for m in updated.messages if m.role == MessageRole.HUMAN]
        assert len(human_msgs) == 1
