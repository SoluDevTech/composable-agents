from pydantic import BaseModel, Field
from datetime import datetime
from enum import StrEnum


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
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_calls: list[dict] | None = None
    status: MessageStatus | None = None
