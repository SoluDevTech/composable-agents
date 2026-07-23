"""GetThreadHistoryUseCase — rebuild the full history of a thread grouped by turn.

Loads the Thread and its TraceEvents, then groups events by ``turn_id``
(ordered by sequence) and rebuilds the HUMAN/AI Messages via
:meth:`Message.from_trace_event`. Intermediate events (THINKING, CONTENT,
TOOL_CALL, TOOL_RESULT) are kept in ``Turn.events``.
"""

from collections import defaultdict

from src.application.responses.thread_history import ThreadHistory, Turn
from src.domain.entities.message import Message
from src.domain.entities.trace_event import TraceEventType
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.ports.trace_event_repository import TraceEventRepository


class GetThreadHistoryUseCase:
    """Rebuild the full history of a thread grouped by turn."""

    def __init__(self, threads: ThreadRepository, trace_repo: TraceEventRepository) -> None:
        self._threads = threads
        self._trace_repo = trace_repo

    async def execute(self, thread_id: str) -> ThreadHistory:
        """Return the thread history grouped by turn.

        Args:
            thread_id: The conversation thread identifier.

        Returns:
            A :class:`ThreadHistory` containing the thread and its turns.

        Raises:
            ThreadNotFoundError: If the thread does not exist.
        """
        thread = await self._threads.get(thread_id)
        trace_events = await self._trace_repo.list_by_thread(thread_id)

        # Sort by timestamp first (chronological), then by sequence within a turn.
        # turn_id is a UUID v4 (random), so sorting by turn_id would NOT preserve
        # chronological order. We track turn_ids in first-seen order.
        sorted_events = sorted(trace_events, key=lambda e: (e.timestamp, e.sequence))
        turns_map: dict[str, list] = defaultdict(list)
        turn_order: list[str] = []
        for ev in sorted_events:
            if ev.turn_id not in turns_map:
                turn_order.append(ev.turn_id)
            turns_map[ev.turn_id].append(ev)

        turns: list[Turn] = []
        for turn_id in turn_order:
            events = turns_map[turn_id]
            human_ev = next((e for e in events if e.type == TraceEventType.HUMAN_MESSAGE), None)
            ai_ev = next((e for e in events if e.type == TraceEventType.AI_MESSAGE), None)
            human_msg = Message.from_trace_event(human_ev) if human_ev else None
            ai_msg = Message.from_trace_event(ai_ev) if ai_ev else None
            intermediate = [
                e for e in events if e.type not in (TraceEventType.HUMAN_MESSAGE, TraceEventType.AI_MESSAGE)
            ]
            turns.append(
                Turn(
                    turn_id=turn_id,
                    human_message=human_msg,
                    ai_message=ai_msg,
                    events=intermediate,
                )
            )

        return ThreadHistory(thread=thread, turns=turns)
