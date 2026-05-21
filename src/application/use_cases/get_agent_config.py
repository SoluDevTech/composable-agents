import logging

from src.domain.entities.agent_config import AgentConfig
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger(__name__)


class GetAgentConfigUseCase:
    """Retrieve a single agent configuration from persistent storage."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store

    async def execute(self, name: str) -> AgentConfig:
        """Fetch YAML from MinIO and parse into AgentConfig.

        Args:
            name: Agent name.

        Returns:
            Validated AgentConfig.

        Raises:
            AgentNotFoundError: If no YAML exists for this agent.
            ConfigError: If the YAML is invalid.
        """
        yaml_content = await self._config_store.get(name)
        config = self._config_loader.load_from_string(yaml_content)
        logger.info("Loaded agent config '%s' from store", name)
        return config
