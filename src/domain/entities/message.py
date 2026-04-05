from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


class MessageStatus(StrEnum):
    COMPLETED = "completed"
    AWAITING_HITL = "awaiting_hitl"


class Message(BaseModel, frozen=True):
    role: MessageRole
    content: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool_calls: list[dict] | None = None
    status: MessageStatus | None = None
    structured_response: dict | None = None
