"""Tests for SendMessageUseCase (Ticket 3 rewrite).

The use case now depends on TraceEventRepository + the new runner API
``invoke(thread_id, message, turn_id) -> (Message, list[TraceEvent])``.
Internal repositories (PostgresThreadRepository, PostgresTraceEventRepository)
are used for real; only the LLM runner (AgentRunner) is mocked at the port
boundary.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType
from src.domain.errors.agent import AgentError
from src.domain.errors.hitl import InvalidHitlActionError
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


def _human_event(thread_id: str, turn_id: str, content: str, seq: int = 0) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=TraceEventType.HUMAN_MESSAGE,
        content=content,
        timestamp=datetime.now(UTC),
        sequence=seq,
    )


def _ai_event(thread_id: str, turn_id: str, message: Message, seq: int = 1) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=TraceEventType.AI_MESSAGE,
        content=message.model_dump_json(),
        timestamp=datetime.now(UTC),
        sequence=seq,
    )


class TestSendMessageUseCase:
    @pytest.fixture
    def registry(self, mock_agent_runner):
        return _FakeRegistry(mock_agent_runner)

    @pytest.fixture
    def use_case(self, registry, thread_repo, trace_repo):
        return SendMessageUseCase(registry, thread_repo, trace_repo)

    async def test_unsupported_hitl_action_raises(self, use_case, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        # Act / Assert
        with pytest.raises(InvalidHitlActionError, match="Unsupported HITL action"):
            await use_case.execute(thread.id, action="unknown_action", tool_call_id="tc-1")

    async def test_sends_message_and_persists_trace(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_message = Message(role=MessageRole.AI, content="Hello human!", status=MessageStatus.COMPLETED)
        # Runner.invoke returns (Message, list[TraceEvent]).
        # Provide a minimal trace: HUMAN_MESSAGE + AI_MESSAGE.
        turn_id = "turn-returned-by-runner"  # the use case generates its own; runner just echoes
        trace = [
            _human_event(thread.id, turn_id, "Hello agent!", seq=0),
            _ai_event(thread.id, turn_id, final_message, seq=1),
        ]
        mock_agent_runner.invoke.return_value = (final_message, trace)

        # Act
        result = await use_case.execute(thread.id, message="Hello agent!")

        # Assert — returns the final AI Message
        assert result.role == MessageRole.AI
        assert result.content == "Hello human!"
        assert result.status == MessageStatus.COMPLETED
        # And persists the trace events in a batch
        mock_agent_runner.invoke.assert_awaited_once()
        # Verify trace events are now in the repository
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 2
        assert events[0].type == TraceEventType.HUMAN_MESSAGE
        assert events[1].type == TraceEventType.AI_MESSAGE

    async def test_each_call_generates_new_turn_id(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange — two consecutive calls must produce two distinct turns
        thread = await thread_repo.create("test-agent")
        msg1 = Message(role=MessageRole.AI, content="first", status=MessageStatus.COMPLETED)
        msg2 = Message(role=MessageRole.AI, content="second", status=MessageStatus.COMPLETED)

        # Capture the turn_id passed to the runner across two calls
        captured_turn_ids: list[str] = []

        async def _invoke(_tid: str, _message: str, turn_id: str) -> tuple[Message, list[TraceEvent]]:
            captured_turn_ids.append(turn_id)
            trace = [_human_event(_tid, turn_id, _message, seq=0), _ai_event(_tid, turn_id, msg1, seq=1)]
            return (msg1, trace)

        mock_agent_runner.invoke.side_effect = _invoke
        mock_agent_runner.invoke.return_value = None  # clear the default to use side_effect

        await use_case.execute(thread.id, message="q1")

        # Reset return for second call with msg2
        async def _invoke2(_tid: str, _message: str, turn_id: str) -> tuple[Message, list[TraceEvent]]:
            captured_turn_ids.append(turn_id)
            trace = [_human_event(_tid, turn_id, _message, seq=0), _ai_event(_tid, turn_id, msg2, seq=1)]
            return (msg2, trace)

        mock_agent_runner.invoke.side_effect = _invoke2
        await use_case.execute(thread.id, message="q2")

        # Assert — two distinct turn_ids generated by the use case
        assert len(captured_turn_ids) == 2
        assert captured_turn_ids[0] != captured_turn_ids[1]
        # And 4 trace events persisted (2 per turn)
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 4

    async def test_approve_hitl_returns_message_no_trace(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        approved = Message(role=MessageRole.AI, content="Action approved.", status=MessageStatus.COMPLETED)
        mock_agent_runner.approve_hitl.return_value = approved

        # Act
        result = await use_case.execute(thread.id, action="approve", tool_call_id="tc-1")

        # Assert
        assert result.content == "Action approved."
        mock_agent_runner.approve_hitl.assert_awaited_once_with(thread.id, "tc-1")
        # HITL path does not persist trace events
        events = await trace_repo.list_by_thread(thread.id)
        assert events == []

    async def test_reject_hitl_returns_message(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        rejected = Message(role=MessageRole.AI, content="Action rejected: Too risky", status=MessageStatus.COMPLETED)
        mock_agent_runner.reject_hitl.return_value = rejected

        # Act
        result = await use_case.execute(thread.id, action="reject", tool_call_id="tc-1", reason="Too risky")

        # Assert
        assert result.content == "Action rejected: Too risky"
        mock_agent_runner.reject_hitl.assert_awaited_once_with(thread.id, "tc-1", "Too risky")
        events = await trace_repo.list_by_thread(thread.id)
        assert events == []

    async def test_edit_hitl_returns_message(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        edited = Message(role=MessageRole.AI, content="Action edited and approved.", status=MessageStatus.COMPLETED)
        mock_agent_runner.edit_hitl.return_value = edited

        # Act
        result = await use_case.execute(thread.id, action="edit", tool_call_id="tc-1", edits={"param": "value"})

        # Assert
        assert result.content == "Action edited and approved."
        mock_agent_runner.edit_hitl.assert_awaited_once_with(thread.id, "tc-1", {"param": "value"})
        events = await trace_repo.list_by_thread(thread.id)
        assert events == []

    async def test_runner_error_propagates(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.invoke.side_effect = AgentError("Backend failed")
        mock_agent_runner.invoke.return_value = None

        # Act / Assert
        with pytest.raises(AgentError, match="Backend failed"):
            await use_case.execute(thread.id, message="Hello")
