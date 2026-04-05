from abc import ABC, abstractmethod

from src.domain.entities.agent_config_metadata import AgentConfigMetadata


class AgentConfigRepository(ABC):
    """Port for persisting agent configuration metadata (relational database)."""

    @abstractmethod
    async def save(self, metadata: AgentConfigMetadata) -> None:
        """Save or update agent configuration metadata."""
        ...

    @abstractmethod
    async def get(self, name: str) -> AgentConfigMetadata:
        """Retrieve metadata for the given agent name.

        Raises:
            AgentNotFoundError: If no metadata exists for this name.
        """
        ...

    @abstractmethod
    async def list_all(self) -> list[AgentConfigMetadata]:
        """List all stored agent configuration metadata."""
        ...

    @abstractmethod
    async def delete(self, name: str) -> None:
        """Delete metadata for the given agent name.

        Raises:
            AgentNotFoundError: If no metadata exists for this name.
        """
        ...

    @abstractmethod
    async def exists(self, name: str) -> bool:
        """Check whether metadata exists for the given agent name."""
        ...
