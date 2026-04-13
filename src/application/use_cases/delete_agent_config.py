import logging

from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger("composable-agents")


class DeleteAgentConfigUseCase:
    """Delete an agent configuration from persistent storage."""

    def __init__(
        self,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
        agent_registry: AgentRegistry,
    ) -> None:
        self._config_store = config_store
        self._config_repository = config_repository
        self._agent_registry = agent_registry

    async def execute(self, name: str) -> None:
        """Delete from MinIO and PostgreSQL, invalidate cache.

        Args:
            name: Agent name to delete.

        Raises:
            AgentNotFoundError: If no agent with this name exists.
        """
        await self._config_repository.get(name)

        await self._config_store.delete(name)
        await self._config_repository.delete(name)
        await self._agent_registry.invalidate(name)

        logger.info("Deleted agent config '%s'", name)
