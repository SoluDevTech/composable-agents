import logging

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.ports.agent_config_repository import AgentConfigRepository

logger = logging.getLogger(__name__)


class ListAgentConfigsUseCase:
    """List all agent configuration metadata from persistent storage."""

    def __init__(self, config_repository: AgentConfigRepository) -> None:
        self._config_repository = config_repository

    async def execute(self) -> list[AgentConfigMetadata]:
        """Return all agent config metadata from the repository.

        Returns:
            List of AgentConfigMetadata.
        """
        result = await self._config_repository.list_all()
        logger.info("Listed %d agent configs from repository", len(result))
        return result
