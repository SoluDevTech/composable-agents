from src.domain.exceptions import AgentNotFoundError
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.agent_runner import AgentRunner
from tests.doubles.fake_agent_runner import FakeAgentRunner


class FakeAgentRegistry(AgentRegistry):
    def __init__(self) -> None:
        self._runners: dict[str, AgentRunner] = {}

    def register(self, agent_name: str, runner: AgentRunner | None = None) -> AgentRunner:
        if runner is None:
            runner = FakeAgentRunner()
        self._runners[agent_name] = runner
        return runner

    async def get_runner(self, agent_name: str) -> AgentRunner:
        if agent_name not in self._runners:
            raise AgentNotFoundError(f"Agent introuvable: {agent_name}")
        return self._runners[agent_name]

    def list_agents(self) -> list[str]:
        return sorted(self._runners.keys())

    async def close(self) -> None:
        self._runners.clear()
