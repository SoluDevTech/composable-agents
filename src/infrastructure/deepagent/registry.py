import asyncio
import logging
from pathlib import Path

from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.tracing_provider import TracingProvider
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from src.infrastructure.deepagent.factory import create_agent_from_config

logger = logging.getLogger("composable-agents")


class DeepAgentRegistry(AgentRegistry):
    """Registre qui cree et cache les agents a la demande depuis un dossier YAML."""

    def __init__(
        self,
        agents_dir: Path,
        config_loader: AgentConfigLoader,
        mcp_tool_loader: McpToolLoader,
        tracing_provider: TracingProvider | None = None,
    ) -> None:
        self._agents_dir = agents_dir
        self._config_loader = config_loader
        self._mcp_tool_loader = mcp_tool_loader
        self._tracing_provider = tracing_provider
        self._runners: dict[str, AgentRunner] = {}
        self._lock = asyncio.Lock()

    async def get_runner(self, agent_name: str) -> AgentRunner:
        if agent_name in self._runners:
            logger.debug("Agent '%s' loaded from cache", agent_name)
            return self._runners[agent_name]

        async with self._lock:
            if agent_name in self._runners:
                return self._runners[agent_name]

            config_path = self._agents_dir / f"{agent_name}.yaml"
            if not config_path.exists():
                logger.error("Agent not found: %s", agent_name)
                raise AgentNotFoundError(f"Agent not found: {agent_name}")

            logger.info("Building agent '%s' from %s", agent_name, config_path)
            config = self._config_loader.load(config_path)
            graph = await create_agent_from_config(config, self._mcp_tool_loader)
            runner = DeepAgentRunner(graph, tracing_provider=self._tracing_provider)
            self._runners[agent_name] = runner
            logger.info("Agent '%s' ready and cached", agent_name)
            return runner

    def list_agents(self) -> list[str]:
        if not self._agents_dir.exists():
            return []
        return sorted(f.stem for f in self._agents_dir.glob("*.yaml"))

    async def close(self) -> None:
        logger.info("Closing registry, clearing %d cached agents", len(self._runners))
        self._runners.clear()
