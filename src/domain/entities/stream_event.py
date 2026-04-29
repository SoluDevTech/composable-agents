from enum import StrEnum

from pydantic import BaseModel


class StreamEventType(StrEnum):
    THINKING = "thinking"
    CONTENT = "content"
    MESSAGE = "message"


class StreamEvent(BaseModel, frozen=True):
    type: StreamEventType
    data: str
