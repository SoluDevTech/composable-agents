"""Tests for GetThreadHistoryUseCase (Ticket 3).

Groups TraceEvents by turn, reconstructs human/ai Messages and filters
intermediate events.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.application.use_cases.get_thread_history import GetThreadHistoryUseCase
from src.domain.entities.message import Message, MessageRole, MessageStatus
from src.domain.entities.trace_event import TraceEvent, TraceEventType


def _event(
    thread_id: str,
    turn_id: str,
    type_: TraceEventType,
    content: str,
    seq: int,
    *,
    timestamp: datetime | None = None,
) -> TraceEvent:
    return TraceEvent(
        id=str(uuid4()),
        thread_id=thread_id,
        turn_id=turn_id,
        type=type_,
        content=content,
        timestamp=timestamp or datetime.now(UTC),
        sequence=seq,
    )


class TestGetThreadHistoryUseCase:
    @pytest.fixture
    def use_case(self, thread_repo, trace_repo):
        return GetThreadHistoryUseCase(thread_repo, trace_repo)

    async def test_execute_returns_history_grouped_by_turn(self, use_case, thread_repo, trace_repo):
        # Arrange — thread with 2 turns, each with HUMAN + intermediate + AI
        thread = await thread_repo.create("test-agent")
        final1 = Message(role=MessageRole.AI, content="answer1", status=MessageStatus.COMPLETED)
        final2 = Message(role=MessageRole.AI, content="answer2", status=MessageStatus.COMPLETED)
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        # Turn 1
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, "q1", seq=0, timestamp=base),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.THINKING, "hmm", seq=1, timestamp=base),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, final1.model_dump_json(), seq=2, timestamp=base),
        )
        # Turn 2
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-2", TraceEventType.HUMAN_MESSAGE, "q2", seq=0, timestamp=base),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-2", TraceEventType.CONTENT, "chunk", seq=1, timestamp=base),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-2", TraceEventType.AI_MESSAGE, final2.model_dump_json(), seq=2, timestamp=base),
        )

        # Act
        history = await use_case.execute(thread.id)

        # Assert
        assert history.thread.id == thread.id
        assert len(history.turns) == 2
        # Turn ordering is not guaranteed by dict; verify both turn_ids present
        turn_ids = {t.turn_id for t in history.turns}
        assert turn_ids == {"turn-1", "turn-2"}
        for turn in history.turns:
            assert turn.human_message is not None
            assert turn.human_message.role == MessageRole.HUMAN
            assert turn.ai_message is not None
            assert turn.ai_message.role == MessageRole.AI
            # Intermediate events: only THINKING / CONTENT (no HUMAN/AI)
            types = {e.type for e in turn.events}
            assert TraceEventType.HUMAN_MESSAGE not in types
            assert TraceEventType.AI_MESSAGE not in types
            assert len(turn.events) == 1  # one intermediate per turn

    async def test_execute_turn_without_ai_message(self, use_case, thread_repo, trace_repo):
        # Arrange — turn crashed mid-run: only HUMAN + THINKING, no AI
        thread = await thread_repo.create("test-agent")
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, "q1", seq=0),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.THINKING, "hmm", seq=1),
        )

        # Act
        history = await use_case.execute(thread.id)

        # Assert
        assert len(history.turns) == 1
        turn = history.turns[0]
        assert turn.human_message is not None
        assert turn.human_message.content == "q1"
        assert turn.ai_message is None  # crashed before AI_MESSAGE
        # intermediate THINKING is still listed
        assert len(turn.events) == 1
        assert turn.events[0].type == TraceEventType.THINKING

    async def test_execute_empty_thread_returns_no_turns(self, use_case, thread_repo):
        # Arrange
        thread = await thread_repo.create("test-agent")

        # Act
        history = await use_case.execute(thread.id)

        # Assert
        assert history.thread.id == thread.id
        assert history.turns == []

    async def test_execute_orders_turns_chronologically_by_timestamp(self, use_case, thread_repo, trace_repo):
        """Turns must be ordered by timestamp, not by turn_id (which is a random UUID v4)."""
        thread = await thread_repo.create("test-agent")
        final = Message(role=MessageRole.AI, content="ans", status=MessageStatus.COMPLETED)
        # Turn B has a random-looking turn_id that sorts BEFORE turn A alphabetically,
        # but turn B happened LATER in time. The use case must order by timestamp.
        early = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        late = datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC)
        # Turn A (earlier) — turn_id "zzzz" sorts AFTER "aaaa" alphabetically
        await trace_repo.add(
            thread.id,
            _event(thread.id, "zzzz-first-chronologically", TraceEventType.HUMAN_MESSAGE, "early q", seq=0, timestamp=early),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "zzzz-first-chronologically", TraceEventType.AI_MESSAGE, final.model_dump_json(), seq=1, timestamp=early),
        )
        # Turn B (later) — turn_id "aaaa" sorts BEFORE "zzzz" alphabetically
        await trace_repo.add(
            thread.id,
            _event(thread.id, "aaaa-second-chronologically", TraceEventType.HUMAN_MESSAGE, "late q", seq=0, timestamp=late),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "aaaa-second-chronologically", TraceEventType.AI_MESSAGE, final.model_dump_json(), seq=1, timestamp=late),
        )

        history = await use_case.execute(thread.id)

        assert len(history.turns) == 2
        # The first turn must be the one with the earlier timestamp, even if
        # its turn_id sorts alphabetically after the other.
        assert history.turns[0].human_message is not None
        assert history.turns[0].human_message.content == "early q"
        assert history.turns[1].human_message is not None
        assert history.turns[1].human_message.content == "late q"
        # Arrange — insert events out of sequence order; use_case must sort by sequence
        thread = await thread_repo.create("test-agent")
        final = Message(role=MessageRole.AI, content="ans", status=MessageStatus.COMPLETED)
        # Insert AI first (seq=2), then intermediate (seq=1), then HUMAN (seq=0)
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.AI_MESSAGE, final.model_dump_json(), seq=2),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.CONTENT, "chunk", seq=1),
        )
        await trace_repo.add(
            thread.id,
            _event(thread.id, "turn-1", TraceEventType.HUMAN_MESSAGE, "q1", seq=0),
        )

        # Act
        history = await use_case.execute(thread.id)

        # Assert
        assert len(history.turns) == 1
        turn = history.turns[0]
        assert turn.human_message is not None
        assert turn.ai_message is not None
        # Intermediate events sorted by sequence (CONTENT seq=1)
        assert len(turn.events) == 1
        assert turn.events[0].sequence == 1
