import asyncio
import logging

from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.prompt_manager import PromptManager
from src.domain.ports.tracing_provider import TracingProvider
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from src.infrastructure.deepagent.factory import create_agent_from_config

logger = logging.getLogger(__name__)


class PersistentAgentRegistry(AgentRegistry):
    """Registry that loads agent configs from MinIO/PostgreSQL and caches runners."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
        mcp_tool_loader: McpToolLoader,
        tracing_provider: TracingProvider | None = None,
        prompt_manager: PromptManager | None = None,
        stream_idle_timeout: float = 120.0,
        invoke_timeout: float = 120.0,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store
        self._config_repository = config_repository
        self._mcp_tool_loader = mcp_tool_loader
        self._tracing_provider = tracing_provider
        self._prompt_manager = prompt_manager
        self._stream_idle_timeout = stream_idle_timeout
        self._invoke_timeout = invoke_timeout
        self._runners: dict[str, AgentRunner] = {}
        self._lock = asyncio.Lock()

    async def get_runner(self, agent_name: str) -> AgentRunner:
        """Return cached runner or build one from persisted config.

        Args:
            agent_name: Name of the agent.

        Returns:
            AgentRunner ready for invocation.

        Raises:
            AgentNotFoundError: If no config exists for this agent.
        """
        if agent_name in self._runners:
            logger.info(LogMessage.AGENT_CACHE_HIT, agent_name)
            return self._runners[agent_name]

        async with self._lock:
            if agent_name in self._runners:
                return self._runners[agent_name]

            logger.info(LogMessage.AGENT_BUILDING, agent_name)
            yaml_content = await self._config_store.get(agent_name)
            config = self._config_loader.load_from_string(yaml_content)
            graph, response_format_model = await create_agent_from_config(
                config, self._mcp_tool_loader, self._prompt_manager
            )
            runner = DeepAgentRunner(
                graph,
                tracing_provider=self._tracing_provider,
                response_format_model=response_format_model,
                stream_idle_timeout=self._stream_idle_timeout,
                invoke_timeout=self._invoke_timeout,
            )
            self._runners[agent_name] = runner
            logger.info(LogMessage.AGENT_CACHED, agent_name)
            return runner

    async def list_agents(self) -> list[str]:
        """List agent names from the metadata repository."""
        metadata_list = await self._config_repository.list_all()
        return [m.name for m in metadata_list]

    async def invalidate(self, agent_name: str) -> None:
        """Remove cached runner for the given agent, forcing rebuild on next access."""
        async with self._lock:
            self._runners.pop(agent_name, None)
            logger.info(LogMessage.AGENT_CACHE_INVALIDATED, agent_name)

    async def close(self) -> None:
        """Clear all cached runners."""
        logger.info(LogMessage.REGISTRY_CLOSING, len(self._runners))
        self._runners.clear()
