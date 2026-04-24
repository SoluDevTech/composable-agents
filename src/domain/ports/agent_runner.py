from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from src.domain.entities.message import Message


class AgentRunner(ABC):
    @abstractmethod
    async def invoke(self, thread_id: str, message: str) -> Message:
        """Envoie un message et retourne la reponse complete."""
        ...

    @abstractmethod
    async def stream(self, thread_id: str, message: str) -> AsyncIterator[str]:
        """Envoie un message et streame la reponse par chunks."""
        ...

    @abstractmethod
    async def stream_with_message(self, thread_id: str, message: str) -> AsyncIterator[str | Message]:
        """Streame les chunks puis yield le Message final complet."""
        ...

    @abstractmethod
    async def approve_hitl(self, thread_id: str, tool_call_id: str) -> Message:
        """Approuve une action HITL en attente."""
        ...

    @abstractmethod
    async def reject_hitl(self, thread_id: str, tool_call_id: str, reason: str | None = None) -> Message:
        """Rejette une action HITL en attente."""
        ...

    @abstractmethod
    async def edit_hitl(self, thread_id: str, tool_call_id: str, edits: dict) -> Message:
        """Edite et approuve une action HITL en attente."""
        ...
