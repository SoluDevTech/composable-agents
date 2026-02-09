from typing import Any

from src.domain.entities.mcp_server_config import McpServerConfig
from src.domain.ports.mcp_tool_loader import McpToolLoader


class FakeMcpToolLoader(McpToolLoader):
    def __init__(self, tools: list[Any] | None = None):
        self._tools = tools or []
        self._closed = False

    async def load_tools(self, configs: list[McpServerConfig]) -> list[Any]:
        return self._tools

    async def close(self) -> None:
        self._closed = True
