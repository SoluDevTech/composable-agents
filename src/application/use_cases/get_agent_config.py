import logging

from src.domain.entities.agent_config import AgentConfig
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger("composable-agents")


class GetAgentConfigUseCase:
    """Retrieve a single agent configuration from persistent storage."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store
        self._config_repository = config_repository

    async def execute(self, name: str) -> AgentConfig:
        """Retrieve agent metadata from PostgreSQL, fetch YAML from MinIO, and parse into AgentConfig.

        Args:
            name: Agent name.

        Returns:
            Validated AgentConfig.

        Raises:
            AgentNotFoundError: If agent not found in PostgreSQL or YAML missing in MinIO.
            ConfigError: If the YAML is invalid.
        """
        metadata = await self._config_repository.get(name)
        yaml_content = await self._config_store.get(metadata.minio_path)
        config = self._config_loader.load_from_string(yaml_content)
        logger.debug("Loaded agent config '%s' from store", name)
        return config
