import logging
from datetime import UTC, datetime

from src.domain.entities.agent_config import AgentConfig
from src.domain.errors.config import ConfigError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class UpdateAgentConfigUseCase:
    """Update an existing agent configuration in persistent storage."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
        agent_registry: AgentRegistry,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store
        self._config_repository = config_repository
        self._agent_registry = agent_registry

    async def execute(self, name: str, yaml_content: str) -> AgentConfig:
        """Validate, update in MinIO and PostgreSQL, invalidate cache.

        Args:
            name: Agent name to update.
            yaml_content: New raw YAML configuration string.

        Returns:
            Validated AgentConfig.

        Raises:
            AgentNotFoundError: If no agent with this name exists.
            ConfigError: If the name in YAML does not match.
        """
        metadata = await self._config_repository.get(name)

        config = self._config_loader.load_from_string(yaml_content)

        if config.name != name:
            raise ConfigError(
                ErrorMessage.AGENT_NAME_MISMATCH_URL.format(yaml_name=config.name, name=name)
            )

        await self._config_store.put(name, yaml_content)

        now = datetime.now(UTC)
        updated_metadata = metadata.model_copy(
            update={"model": config.model, "updated_at": now},
        )
        await self._config_repository.save(updated_metadata)

        await self._agent_registry.invalidate(name)

        logger.info(LogMessage.AGENT_CONFIG_UPDATED_UC, name)
        return config
