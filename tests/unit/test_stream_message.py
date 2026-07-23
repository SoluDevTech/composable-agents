"""Tests for StreamMessageUseCase (Ticket 3 rewrite).

The use case now depends on TraceEventRepository + the new runner API
``stream(thread_id, message, turn_id) -> AsyncIterator[TraceEvent]``.
Internal repositories are used for real; only the LLM runner is mocked.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.use_cases.stream_message import StreamMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.agent import AgentError
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

    async def invalidate(self, agent_name: str) -> None:  # noqa: ARG002
        pass

    async def close(self) -> None:
        pass


def _event(thread_id: str, turn_id: str, type_: TraceEventType, content: str, seq: int) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=type_,
        content=content,
        timestamp=datetime.now(UTC),
        sequence=seq,
    )


class TestStreamMessageUseCase:
    @pytest.fixture
    def registry(self, mock_agent_runner):
        return _FakeRegistry(mock_agent_runner)

    @pytest.fixture
    def use_case(self, registry, thread_repo, trace_repo):
        return StreamMessageUseCase(registry, thread_repo, trace_repo)

    async def test_execute_yields_events_and_persists(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_msg = Message(role=MessageRole.AI, content="Hi!", status=MessageStatus.COMPLETED)
        events = [
            _event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, "Hello", seq=0),
            _event(thread.id, "turn-1", TraceEventType.THINKING, "hmm", seq=1),
            _event(thread.id, "turn-1", TraceEventType.CONTENT, "Hi", seq=2),
            _event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, final_msg.model_dump_json(), seq=3),
        ]

        async def _stream(_tid: str, _message: str, _turn_id: str) -> AsyncIterator[TraceEvent]:
            for ev in events:
                yield ev

        mock_agent_runner.stream = _stream

        # Act
        yielded: list[TraceEvent] = [ev async for ev in use_case.execute(thread.id, "Hello")]

        # Assert — all events yielded
        assert len(yielded) == 4
        assert [e.type for e in yielded] == [
            TraceEventType.HUMAN_MESSAGE,
            TraceEventType.THINKING,
            TraceEventType.CONTENT,
            TraceEventType.AI_MESSAGE,
        ]
        # And all events persisted via trace_repo.add
        persisted = await trace_repo.list_by_thread(thread.id)
        assert len(persisted) == 4

    async def test_execute_persists_human_message(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        async def _stream(_tid: str, _message: str, _turn_id: str) -> AsyncIterator[TraceEvent]:
            yield _event(thread.id, _turn_id, TraceEventType.HUMAN_MESSAGE, "Hello", seq=0)
            yield _event(
                thread.id,
                _turn_id,
                TraceEventType.AI_MESSAGE,
                Message(role=MessageRole.AI, content="Hi!", status=MessageStatus.COMPLETED).model_dump_json(),
                seq=1,
            )

        mock_agent_runner.stream = _stream

        # Act
        _ = [ev async for ev in use_case.execute(thread.id, "Hello")]

        # Assert — HUMAN_MESSAGE is persisted
        persisted = await trace_repo.list_by_thread(thread.id)
        human_events = [e for e in persisted if e.type == TraceEventType.HUMAN_MESSAGE]
        assert len(human_events) == 1
        assert human_events[0].content == "Hello"

    async def test_execute_persists_ai_message(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_msg = Message(role=MessageRole.AI, content="Final answer.", status=MessageStatus.COMPLETED)

        async def _stream(_tid: str, _message: str, _turn_id: str) -> AsyncIterator[TraceEvent]:
            yield _event(thread.id, _turn_id, TraceEventType.HUMAN_MESSAGE, "Hello", seq=0)
            yield _event(thread.id, _turn_id, TraceEventType.AI_MESSAGE, final_msg.model_dump_json(), seq=1)

        mock_agent_runner.stream = _stream

        # Act
        _ = [ev async for ev in use_case.execute(thread.id, "Hello")]

        # Assert — AI_MESSAGE is persisted and its content is valid JSON (the Message payload)
        persisted = await trace_repo.list_by_thread(thread.id)
        ai_events = [e for e in persisted if e.type == TraceEventType.AI_MESSAGE]
        assert len(ai_events) == 1
        payload = json.loads(ai_events[0].content)
        assert payload["content"] == "Final answer."

    async def test_execute_propagates_runner_error(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        async def _stream(_tid: str, _message: str, _turn_id: str) -> AsyncIterator[TraceEvent]:
            yield _event(thread.id, _turn_id, TraceEventType.HUMAN_MESSAGE, "Hello", seq=0)
            raise AgentError("graph crashed")

        mock_agent_runner.stream = _stream

        # Act / Assert — runner error propagates out of the async generator
        with pytest.raises(AgentError, match="graph crashed"):
            _ = [ev async for ev in use_case.execute(thread.id, "Hello")]
