from abc import ABC, abstractmethod


class AgentConfigStore(ABC):
    """Port for storing and retrieving agent YAML configurations (object storage)."""

    @abstractmethod
    async def put(self, path: str, yaml_content: str) -> None:
        """Upload a YAML configuration for the given path."""
        ...

    @abstractmethod
    async def get(self, path: str) -> str:
        """Retrieve the YAML configuration for the given path.

        Raises:
            AgentNotFoundError: If no configuration exists for this path.
        """
        ...

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete the YAML configuration for the given path.

        Raises:
            AgentNotFoundError: If no configuration exists for this path.
        """
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check whether a YAML configuration exists for the given path."""
        ...
