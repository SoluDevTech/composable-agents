"""Tests for SendMessageUseCase (HITL refactor — TDD red phase).

The use case now depends on TraceEventRepository + the new runner API
``invoke(thread_id, message, turn_id) -> (Message, list[TraceEvent])`` and the
unified HITL resume method
``resume_hitl(thread_id, decisions, turn_id) -> (Message, list[TraceEvent])``.

Internal repositories (PostgresThreadRepository, PostgresTraceEventRepository)
are used for real; only the LLM runner (AgentRunner) is mocked at the port
boundary.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.hitl_decision import HitlDecision
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


def _hitl_decision_event(thread_id: str, turn_id: str, name: str, content: str, seq: int) -> TraceEvent:
    """Build a HITL_DECISION trace event emitted by the runner on resume."""
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=TraceEventType.HITL_DECISION,
        name=name,
        content=content,
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

    # ------------------------------------------------------------------ #
    # NEW HITL resume contract (decisions-based)
    # ------------------------------------------------------------------ #

    async def test_resume_hitl_persists_trace(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_message = Message(role=MessageRole.AI, content="Resumed after approval.", status=MessageStatus.COMPLETED)
        decisions = [HitlDecision(tool_call_id="tc-1", action="approve")]

        captured_turn_ids: list[str] = []

        async def _resume(_tid: str, _decisions, turn_id: str):
            captured_turn_ids.append(turn_id)
            hitl_decision_event = _hitl_decision_event(_tid, turn_id, "approve", "tc-1", seq=0)
            ai_event = _ai_event(_tid, turn_id, final_message, seq=1)
            return final_message, [hitl_decision_event, ai_event]

        mock_agent_runner.resume_hitl.side_effect = _resume

        # Act
        result = await use_case.execute(thread.id, decisions=decisions)

        # Assert — resume_hitl awaited once with (thread.id, decisions, turn_id)
        mock_agent_runner.resume_hitl.assert_awaited_once()
        assert mock_agent_runner.resume_hitl.await_args.args[0] == thread.id
        assert mock_agent_runner.resume_hitl.await_args.args[1] == decisions
        # The use case generated a turn_id (non-empty, captured)
        assert len(captured_turn_ids) == 1
        assert captured_turn_ids[0] and isinstance(captured_turn_ids[0], str)
        # And the final message is returned
        assert result == final_message
        # And trace events are now persisted (HITL_DECISION then AI_MESSAGE)
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 2
        assert events[0].type == TraceEventType.HITL_DECISION
        assert events[1].type == TraceEventType.AI_MESSAGE

    async def test_resume_hitl_generates_turn_id(self, use_case, mock_agent_runner, thread_repo, trace_repo):
        # Arrange — two consecutive resume calls must produce two distinct turns
        thread = await thread_repo.create("test-agent")
        msg1 = Message(role=MessageRole.AI, content="first", status=MessageStatus.COMPLETED)
        msg2 = Message(role=MessageRole.AI, content="second", status=MessageStatus.COMPLETED)

        captured_turn_ids: list[str] = []

        async def _resume1(_tid: str, _decisions, turn_id: str):
            captured_turn_ids.append(turn_id)
            return msg1, [
                _hitl_decision_event(_tid, turn_id, "approve", "tc-1", seq=0),
                _ai_event(_tid, turn_id, msg1, seq=1),
            ]

        mock_agent_runner.resume_hitl.side_effect = _resume1
        await use_case.execute(thread.id, decisions=[HitlDecision(tool_call_id="tc-1", action="approve")])

        async def _resume2(_tid: str, _decisions, turn_id: str):
            captured_turn_ids.append(turn_id)
            return msg2, [
                _hitl_decision_event(_tid, turn_id, "approve", "tc-2", seq=0),
                _ai_event(_tid, turn_id, msg2, seq=1),
            ]

        mock_agent_runner.resume_hitl.side_effect = _resume2
        await use_case.execute(thread.id, decisions=[HitlDecision(tool_call_id="tc-2", action="approve")])

        # Assert — two distinct turn_ids generated by the use case
        assert len(captured_turn_ids) == 2
        assert captured_turn_ids[0] != captured_turn_ids[1]
        # And 4 trace events persisted (2 per turn)
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 4

    async def test_legacy_single_approve_converted_to_decisions(
        self, use_case, mock_agent_runner, thread_repo, trace_repo
    ):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_message = Message(role=MessageRole.AI, content="Action approved.", status=MessageStatus.COMPLETED)
        mock_agent_runner.resume_hitl.return_value = (
            final_message,
            [
                _hitl_decision_event(thread.id, "turn-x", "approve", "tc-1", seq=0),
                _ai_event(thread.id, "turn-x", final_message, seq=1),
            ],
        )

        # Act — legacy single-decision shape
        result = await use_case.execute(thread.id, action="approve", tool_call_id="tc-1")

        # Assert — resume_hitl awaited with a 1-element decisions list
        mock_agent_runner.resume_hitl.assert_awaited_once()
        args = mock_agent_runner.resume_hitl.await_args.args
        assert args[0] == thread.id
        decisions = args[1]
        assert isinstance(decisions, list)
        assert len(decisions) == 1
        assert isinstance(decisions[0], HitlDecision)
        assert decisions[0].tool_call_id == "tc-1"
        assert decisions[0].action == "approve"
        # And the final message is returned
        assert result == final_message
        # And trace events are now persisted (HITL_DECISION then AI_MESSAGE)
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 2
        assert events[0].type == TraceEventType.HITL_DECISION
        assert events[1].type == TraceEventType.AI_MESSAGE

    async def test_legacy_single_reject_converted_to_decisions(
        self, use_case, mock_agent_runner, thread_repo, trace_repo
    ):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_message = Message(
            role=MessageRole.AI, content="Action rejected: Too risky", status=MessageStatus.COMPLETED
        )
        mock_agent_runner.resume_hitl.return_value = (
            final_message,
            [
                _hitl_decision_event(thread.id, "turn-y", "reject", "Too risky", seq=0),
                _ai_event(thread.id, "turn-y", final_message, seq=1),
            ],
        )

        # Act — legacy single-decision shape
        result = await use_case.execute(thread.id, action="reject", tool_call_id="tc-1", reason="Too risky")

        # Assert — resume_hitl awaited with a 1-element decisions list
        mock_agent_runner.resume_hitl.assert_awaited_once()
        args = mock_agent_runner.resume_hitl.await_args.args
        assert args[0] == thread.id
        decisions = args[1]
        assert isinstance(decisions, list)
        assert len(decisions) == 1
        assert isinstance(decisions[0], HitlDecision)
        assert decisions[0].tool_call_id == "tc-1"
        assert decisions[0].action == "reject"
        assert decisions[0].reason == "Too risky"
        # And the final message is returned
        assert result == final_message
        # And trace events are now persisted
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 2
        assert events[0].type == TraceEventType.HITL_DECISION
        assert events[1].type == TraceEventType.AI_MESSAGE

    async def test_legacy_single_edit_converted_to_decisions(
        self, use_case, mock_agent_runner, thread_repo, trace_repo
    ):
        # Arrange
        thread = await thread_repo.create("test-agent")
        final_message = Message(
            role=MessageRole.AI, content="Action edited and approved.", status=MessageStatus.COMPLETED
        )
        mock_agent_runner.resume_hitl.return_value = (
            final_message,
            [
                _hitl_decision_event(thread.id, "turn-z", "edit", "edited", seq=0),
                _ai_event(thread.id, "turn-z", final_message, seq=1),
            ],
        )

        # Act — legacy single-decision shape
        result = await use_case.execute(thread.id, action="edit", tool_call_id="tc-1", edits={"param": "value"})

        # Assert — resume_hitl awaited with a 1-element decisions list
        mock_agent_runner.resume_hitl.assert_awaited_once()
        args = mock_agent_runner.resume_hitl.await_args.args
        assert args[0] == thread.id
        decisions = args[1]
        assert isinstance(decisions, list)
        assert len(decisions) == 1
        assert isinstance(decisions[0], HitlDecision)
        assert decisions[0].tool_call_id == "tc-1"
        assert decisions[0].action == "edit"
        assert decisions[0].edits == {"param": "value"}
        # And the final message is returned
        assert result == final_message
        # And trace events are now persisted
        events = await trace_repo.list_by_thread(thread.id)
        assert len(events) == 2
        assert events[0].type == TraceEventType.HITL_DECISION
        assert events[1].type == TraceEventType.AI_MESSAGE

    async def test_resume_hitl_runner_error_propagates(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.resume_hitl.side_effect = AgentError("Backend failed")

        # Act / Assert
        with pytest.raises(AgentError, match="Backend failed"):
            await use_case.execute(thread.id, decisions=[HitlDecision(tool_call_id="tc-1", action="approve")])

    async def test_runner_error_propagates(self, use_case, mock_agent_runner, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")
        mock_agent_runner.invoke.side_effect = AgentError("Backend failed")
        mock_agent_runner.invoke.return_value = None

        # Act / Assert
        with pytest.raises(AgentError, match="Backend failed"):
            await use_case.execute(thread.id, message="Hello")
