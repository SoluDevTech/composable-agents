"""Thread domain entity.

A Thread groups all :class:`~src.domain.entities.trace_event.TraceEvent` records
for a conversation. The legacy ``messages`` field is now a backward-compatible
computed projection rebuilt from HUMAN_MESSAGE + AI_MESSAGE trace events.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from src.domain.entities.message import Message
from src.domain.entities.trace_event import TraceEvent, TraceEventType


class Thread(BaseModel):
    """A conversation thread backed by trace events."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str
    trace_events: list[TraceEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def messages(self) -> list[Message]:
        """Backward-compatible message list, projected from trace_events.

        Filters HUMAN_MESSAGE + AI_MESSAGE events and rebuilds Message objects
        via :meth:`Message.from_trace_event`, ordered by timestamp.
        """
        message_events = sorted(
            (e for e in self.trace_events if e.type in (TraceEventType.HUMAN_MESSAGE, TraceEventType.AI_MESSAGE)),
            key=lambda e: (e.timestamp, e.sequence),
        )
        return [Message.from_trace_event(e) for e in message_events]
