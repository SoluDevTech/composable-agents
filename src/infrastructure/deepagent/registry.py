import asyncio
from pathlib import Path

from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.tracing_provider import TracingProvider
from src.infrastructure.deepagent.adapter import DeepAgentRunner
from src.infrastructure.deepagent.factory import create_agent_from_config


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
            return self._runners[agent_name]

        async with self._lock:
            if agent_name in self._runners:
                return self._runners[agent_name]

            config_path = self._agents_dir / f"{agent_name}.yaml"
            if not config_path.exists():
                raise AgentNotFoundError(f"Agent introuvable: {agent_name}")

            config = self._config_loader.load(config_path)
            graph = await create_agent_from_config(config, self._mcp_tool_loader)
            runner = DeepAgentRunner(graph, tracing_provider=self._tracing_provider)
            self._runners[agent_name] = runner
            return runner

    def list_agents(self) -> list[str]:
        if not self._agents_dir.exists():
            return []
        return sorted(f.stem for f in self._agents_dir.glob("*.yaml"))

    async def close(self) -> None:
        self._runners.clear()
