import logging
from datetime import UTC, datetime

from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import ConfigError
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_registry import AgentRegistry

logger = logging.getLogger("composable-agents")


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
            ConfigError: If the agent is built-in or the name in YAML does not match.
        """
        metadata = await self._config_repository.get(name)

        if metadata.is_builtin:
            raise ConfigError(f"Cannot update built-in agent: {name}")

        config = self._config_loader.load_from_string(yaml_content)

        if config.name != name:
            raise ConfigError(f"Agent name in YAML '{config.name}' does not match URL name '{name}'")

        await self._config_store.put(metadata.minio_path, yaml_content)

        now = datetime.now(UTC)
        updated_metadata = metadata.model_copy(
            update={"model": config.model, "updated_at": now},
        )
        await self._config_repository.save(updated_metadata)

        await self._agent_registry.invalidate(name)

        logger.info("Updated agent config '%s'", name)
        return config
