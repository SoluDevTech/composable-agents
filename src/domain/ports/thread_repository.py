from abc import ABC, abstractmethod

from src.domain.entities.message import Message
from src.domain.entities.thread import Thread


class ThreadRepository(ABC):
    @abstractmethod
    async def create(self, agent_name: str) -> Thread:
        """Cree un nouveau thread de conversation."""
        ...

    @abstractmethod
    async def get(self, thread_id: str) -> Thread:
        """Recupere un thread par son ID."""
        ...

    @abstractmethod
    async def list_all(self) -> list[Thread]:
        """Liste tous les threads."""
        ...

    @abstractmethod
    async def delete(self, thread_id: str) -> None:
        """Supprime un thread."""
        ...

    @abstractmethod
    async def add_message(self, thread_id: str, message: Message) -> Thread:
        """Ajoute un message a un thread existant."""
        ...
