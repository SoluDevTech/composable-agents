"""Response DTOs for thread history (Ticket 3).

Groups TraceEvents by turn, with the reconstructed HUMAN/AI Messages and
the list of intermediate trace events (THINKING, CONTENT, TOOL_CALL, …).
"""

from pydantic import BaseModel

from src.domain.entities.message import Message
from src.domain.entities.thread import Thread
from src.domain.entities.trace_event import TraceEvent


class Turn(BaseModel):
    """A single conversation turn inside a thread.

    Attributes:
        turn_id: Identifier grouping all events of this turn.
        human_message: Reconstructed human Message (None if missing).
        ai_message: Reconstructed AI Message (None if the turn crashed before
            the AI_MESSAGE event was emitted).
        events: Intermediate TraceEvents (everything except HUMAN_MESSAGE and
            AI_MESSAGE), ordered by sequence.
    """

    turn_id: str
    human_message: Message | None
    ai_message: Message | None
    events: list[TraceEvent]


class ThreadHistory(BaseModel):
    """Full history of a thread grouped by turn.

    Attributes:
        thread: The parent Thread.
        turns: List of Turns, one per turn_id.
    """

    thread: Thread
    turns: list[Turn]
