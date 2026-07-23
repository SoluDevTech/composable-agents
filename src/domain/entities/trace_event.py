"""TraceEvent domain entity.

A TraceEvent is an immutable record of anything that happened during a conversation
turn inside a thread: a human message, an AI message, a thinking chunk, a content
chunk, a tool call or a tool result. The persistence layer stores every event in a
single ``trace_events`` table; ``Message`` is now a backward-compatible projection
of the HUMAN_MESSAGE + AI_MESSAGE events.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TraceEventType(StrEnum):
    """Type of trace event.

    Values are stored as plain strings in the database.
    """

    HUMAN_MESSAGE = "human_message"
    AI_MESSAGE = "ai_message"
    THINKING = "thinking"
    CONTENT = "content"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class TraceEvent(BaseModel, frozen=True):
    """An immutable trace event belonging to a thread.

    Attributes:
        id: UUID string identifying the event.
        thread_id: Parent thread id.
        turn_id: Identifier grouping events of a single conversation turn.
        type: The :class:`TraceEventType` of this event.
        source: Name of the subagent that produced this event (None = parent).
        name: Tool name for TOOL_CALL / TOOL_RESULT events.
        content: Text content or JSON-serialized payload.
        metadata: Optional structured metadata.
        timestamp: When the event occurred.
        sequence: Monotonic sequence number inside a turn.
    """

    id: str
    thread_id: str
    turn_id: str
    type: TraceEventType
    source: str | None = None
    name: str | None = None
    content: str | None = None
    metadata: dict | None = None
    timestamp: datetime
    sequence: int = Field(ge=0)
