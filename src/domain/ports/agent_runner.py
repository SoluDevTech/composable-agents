from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.domain.entities.message import Message
from src.domain.entities.stream_event import StreamEvent


class AgentRunner(ABC):
    @abstractmethod
    async def invoke(self, thread_id: str, message: str) -> Message:
        ...

    @abstractmethod
    async def stream(self, thread_id: str, message: str) -> AsyncIterator[StreamEvent]:
        ...

    @abstractmethod
    async def stream_with_message(self, thread_id: str, message: str) -> AsyncIterator[StreamEvent]:
        ...

    @abstractmethod
    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:
        ...

    @abstractmethod
    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:
        ...

    @abstractmethod
    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        ...
