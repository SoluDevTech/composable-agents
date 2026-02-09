from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.mcp_server_config import McpServerConfig


class McpToolLoader(ABC):
    """Port pour charger des outils depuis des serveurs MCP."""

    @abstractmethod
    async def load_tools(self, configs: list[McpServerConfig]) -> list[Any]:
        """Charge les outils depuis les serveurs MCP configures."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Ferme toutes les connexions MCP ouvertes."""
        ...
