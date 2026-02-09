from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.domain.exceptions import McpConnectionError, McpToolLoadError
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.infrastructure.env_utils import resolve_env_vars


class LangchainMcpToolLoader(McpToolLoader):
    """Adapter MCP utilisant langchain-mcp-adapters pour charger des outils."""

    def __init__(self) -> None:
        self._clients: list[MultiServerMCPClient] = []

    async def load_tools(self, configs: list[McpServerConfig]) -> list[Any]:
        """Charge les outils depuis les serveurs MCP configures.

        Args:
            configs: Liste des configurations de serveurs MCP.

        Returns:
            Liste des outils charges depuis les serveurs MCP.

        Raises:
            McpConnectionError: Si la connexion a un serveur MCP echoue.
            McpToolLoadError: Si le chargement des outils echoue.
        """
        server_configs: dict[str, dict[str, Any]] = {}

        for config in configs:
            if config.transport == McpTransportType.STDIO:
                server_configs[config.name] = {
                    "transport": "stdio",
                    "command": config.command,
                    "args": config.args,
                    "env": self._resolve_env_vars(config.env),
                }
            elif config.transport == McpTransportType.HTTP:
                server_configs[config.name] = {
                    "transport": "streamable_http",
                    "url": config.url,
                    "headers": self._resolve_env_vars(config.headers),
                }

        try:
            client = MultiServerMCPClient(server_configs)
            self._clients.append(client)
            return await client.get_tools()
        except ConnectionError as e:
            raise McpConnectionError(f"Failed to connect to MCP servers: {e}") from e
        except Exception as e:
            raise McpToolLoadError(f"Failed to load MCP tools: {e}") from e

    async def close(self) -> None:
        """Ferme toutes les connexions MCP ouvertes."""
        for client in self._clients:
            pass  # MultiServerMCPClient cleanup
        self._clients.clear()

    def _resolve_env_vars(self, mapping: dict[str, str]) -> dict[str, str]:
        """Resout les variables d'environnement dans un mapping.

        Les variables au format ${VAR_NAME} sont remplacees par leur valeur
        depuis os.environ. Si la variable n'existe pas, le placeholder est conserve.
        """
        return {key: resolve_env_vars(value) for key, value in mapping.items()}
