from abc import ABC, abstractmethod


class AgentConfigStore(ABC):
    """Port for storing and retrieving agent YAML configurations (object storage)."""

    @abstractmethod
    async def put(self, name: str, yaml_content: str) -> None:
        """Upload a YAML configuration for the given agent name."""
        ...

    @abstractmethod
    async def get(self, name: str) -> str:
        """Retrieve the YAML configuration for the given agent name.

        Raises:
            AgentNotFoundError: If no configuration exists for this name.
        """
        ...

    @abstractmethod
    async def delete(self, name: str) -> None:
        """Delete the YAML configuration for the given agent name.

        Raises:
            AgentNotFoundError: If no configuration exists for this name.
        """
        ...

    @abstractmethod
    async def exists(self, name: str) -> bool:
        """Check whether a YAML configuration exists for the given agent name."""
        ...

    @abstractmethod
    async def list_all(self) -> list[str]:
        """List all stored agent names."""
        ...
