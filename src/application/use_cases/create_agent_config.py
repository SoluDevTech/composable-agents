import logging
from datetime import UTC, datetime

from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.exceptions import AgentConfigAlreadyExistsError, ConfigError
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger(__name__)


class CreateAgentConfigUseCase:
    """Create a new agent configuration in persistent storage."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store
        self._config_repository = config_repository

    async def execute(self, name: str, yaml_content: str) -> AgentConfig:
        """Parse YAML, validate, store in MinIO, save metadata in PostgreSQL.

        Args:
            name: Agent name.
            yaml_content: Raw YAML configuration string.

        Returns:
            Validated AgentConfig.

        Raises:
            AgentConfigAlreadyExistsError: If an agent with this name already exists.
            ConfigError: If the YAML is invalid.
        """
        config = self._config_loader.load_from_string(yaml_content)

        if config.name != name:
            raise ConfigError(f"Agent name in YAML '{config.name}' does not match provided name '{name}'")

        if await self._config_repository.exists(name):
            raise AgentConfigAlreadyExistsError(f"Agent config already exists: {name}")

        await self._config_store.put(name, yaml_content)

        now = datetime.now(UTC)
        metadata = AgentConfigMetadata(
            name=name,
            model=config.model,
            minio_path=f"{name}.yaml",
            created_at=now,
            updated_at=now,
        )
        await self._config_repository.save(metadata)

        logger.info("Created agent config '%s'", name)
        return config
