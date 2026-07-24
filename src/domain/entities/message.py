"""Message domain entity.

A Message is a backward-compatible projection of HUMAN_MESSAGE and AI_MESSAGE
:class:`~src.domain.entities.trace_event.TraceEvent` records. It is no longer the
primary persistence unit — ``trace_events`` is the single source of truth.
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from src.domain.errors.thread import MessageBuildError

if TYPE_CHECKING:
    from src.domain.entities.trace_event import TraceEvent


class MessageRole(StrEnum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


class MessageStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_HITL = "awaiting_hitl"


class Message(BaseModel, frozen=True):
    """An immutable conversation message (projection of TraceEvent)."""

    role: MessageRole
    content: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool_calls: list[dict] | None = None
    status: MessageStatus | None = None
    structured_response: dict | None = None
    thinking: str | None = None
    turn_id: str | None = None

    @staticmethod
    def from_trace_event(event: "TraceEvent") -> "Message":
        """Reconstruct a Message from a HUMAN_MESSAGE or AI_MESSAGE trace event.

        Args:
            event: A TraceEvent of type HUMAN_MESSAGE or AI_MESSAGE.

        Returns:
            A Message projection of the event.

        Raises:
            ValueError: If the event type is not HUMAN_MESSAGE or AI_MESSAGE, or
                if an AI_MESSAGE event's content is not valid JSON.
        """
        from src.domain.entities.trace_event import TraceEventType

        if event.type == TraceEventType.HUMAN_MESSAGE:
            return Message(
                role=MessageRole.HUMAN,
                content=event.content,
                timestamp=event.timestamp,
                turn_id=event.turn_id,
            )

        if event.type == TraceEventType.AI_MESSAGE:
            payload: dict = {}
            if event.content:
                payload = json.loads(event.content)
            status_value = payload.get("status")
            return Message(
                role=MessageRole.AI,
                content=payload.get("content"),
                timestamp=event.timestamp,
                tool_calls=payload.get("tool_calls"),
                status=MessageStatus(status_value) if status_value else None,
                structured_response=payload.get("structured_response"),
                thinking=payload.get("thinking"),
                turn_id=event.turn_id,
            )

        raise MessageBuildError(f"Cannot build Message from trace event type {event.type!r}")
