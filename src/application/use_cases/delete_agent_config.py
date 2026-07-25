import logging

from src.application.use_cases._subagent_ref_utils import invalidate_dependent_agents
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


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
        await invalidate_dependent_agents(self._config_store, self._agent_registry, name)

        logger.info(LogMessage.AGENT_CONFIG_DELETED_UC, name)
