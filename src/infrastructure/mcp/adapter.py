import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.domain.entities.mcp_server_config import McpServerConfig, McpTransportType
from src.domain.errors.mcp import McpConnectionError, McpToolLoadError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.infrastructure.env_utils import resolve_headers_drop_empty

logger = logging.getLogger(__name__)


class LangchainMcpToolLoader(McpToolLoader):
    """Adapter MCP utilisant langchain-mcp-adapters pour charger des outils."""

    def __init__(self, tool_timeout: float = 60.0) -> None:
        self._clients: list[MultiServerMCPClient] = []
        # Per-call timeout for each MCP tool invocation. A hung tool is converted
        # to a ToolException -> ToolMessage(error) so the agent can recover
        # (retry/skip) instead of stalling or being killed.
        self._tool_timeout = tool_timeout

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
                server_config = {
                    "transport": "streamable_http",
                    "url": config.url,
                    "headers": self._resolve_env_vars(config.headers),
                }
                if config.auth_token:
                    server_config["auth_token"] = config.auth_token
                server_configs[config.name] = server_config

        try:
            client = MultiServerMCPClient(server_configs)
            self._clients.append(client)
            tools = await client.get_tools()
            return self._patch_sync_support(tools)
        except ConnectionError as e:
            logger.exception(LogMessage.MCP_CONNECT_FAILED)
            raise McpConnectionError(ErrorMessage.MCP_CONNECTION_ERROR.format(error=e)) from e
        except Exception as e:
            logger.exception(LogMessage.MCP_TOOLS_LOAD_FAILED)
            raise McpToolLoadError(ErrorMessage.MCP_TOOL_LOAD_ERROR.format(error=e)) from e

    async def close(self) -> None:
        """Ferme toutes les connexions MCP ouvertes.

        MultiServerMCPClient v0.1.0+ is stateless (no close method).
        Guard handles future library versions that may add cleanup.
        """
        for client in self._clients:
            close_fn = getattr(client, "close", None)
            if close_fn and callable(close_fn):
                result = close_fn()
                if hasattr(result, "__await__"):
                    await result
        self._clients.clear()

    def _patch_sync_support(self, tools: list[BaseTool]) -> list[BaseTool]:
        """Patch MCP tools: per-call timeout + sync invocation support.

        langchain-mcp-adapters creates async-only StructuredTools (coroutine only,
        no func). deepagents invokes subagent tools synchronously, which crashes
        with NotImplementedError. We recreate each tool with:
          - a coroutine wrapped in asyncio.wait_for(tool_timeout): a hung tool
            raises ToolException -> ToolMessage(error) so the agent RECOVERS
            (the LLM can retry/skip) instead of stalling or being killed.
          - a sync func that runs the same timed coroutine for deepagents.
        """
        patched = []
        for tool in tools:
            if isinstance(tool, StructuredTool) and tool.coroutine is not None and tool.func is None:
                original_coro = tool.coroutine
                timeout = self._tool_timeout
                tool_name = tool.name

                async def timed_coro(*args, _oc=original_coro, _to=timeout, _name=tool_name, **kwargs):
                    try:
                        return await asyncio.wait_for(_oc(*args, **kwargs), timeout=_to)
                    except TimeoutError as e:
                        logger.warning(LogMessage.MCP_TOOL_TIMEOUT, _name, _to)
                        raise ToolException(ErrorMessage.MCP_TOOL_CALL_TIMEOUT.format(name=_name, timeout=_to)) from e

                def sync_wrapper(*args, _tc=timed_coro, **kwargs):
                    return asyncio.get_event_loop().run_until_complete(_tc(*args, **kwargs))

                patched.append(
                    StructuredTool(
                        name=tool.name,
                        description=tool.description,
                        args_schema=tool.args_schema,
                        func=sync_wrapper,
                        coroutine=timed_coro,
                        response_format=tool.response_format,
                        metadata=tool.metadata,
                    )
                )
            else:
                patched.append(tool)
        return patched

    def _resolve_env_vars(self, mapping: dict[str, str]) -> dict[str, str]:
        """Resolve ${VAR_NAME} placeholders (os.environ + user credentials) in a mapping.

        Delegates to :func:`resolve_headers_drop_empty`, which resolves both
        environment variables (``${OPENROUTER_API_KEY}`` etc.) and the
        user-credential placeholders (``${USER_JWT}``, ``${USER_API_KEY}``)
        from the RLS contextvars, then DROPS entries whose resolved value is
        empty or whose user-credential placeholder resolved to empty. This
        prevents sending a malformed ``Authorization: Bearer `` (with no token)
        or an empty ``X-API-Key`` to a remote MCP server.

        Args:
            mapping: The input header/env mapping.

        Returns:
            A new dict with resolved values; empty/credential-empty entries
            dropped. Non-string values are passed through unchanged.
        """
        return resolve_headers_drop_empty(mapping)
