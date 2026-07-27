import logging

from src.domain.entities.agent_config import AgentConfig
from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger(__name__)


class GetAgentConfigUseCase:
    """Retrieve a single agent configuration from persistent storage.

    The YAML body lives in object storage (MinIO) which is a *shared* bucket
    (not user-scoped), so a by-name lookup would otherwise leak another user's
    agent config. To enforce per-user isolation the use case first resolves the
    metadata row from the relational repository — which is RLS-filtered by
    ``current_user_id`` — and only fetches the YAML when the caller actually
    owns the agent. When no metadata row is visible (the agent does not exist
    or belongs to another user) :class:`AgentNotFoundError` is raised before
    MinIO is ever touched.
    """

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
        """Fetch metadata (ownership check) then YAML from MinIO and parse.

        Args:
            name: Agent name.

        Returns:
            Validated AgentConfig.

        Raises:
            AgentNotFoundError: If no metadata is visible to the current user
                (the agent does not exist or is owned by another user), or if
                the YAML is missing from object storage.
            ConfigError: If the YAML is invalid.
        """
        # Ownership check: the repository is RLS-filtered by current_user_id,
        # so this raises AgentNotFoundError when the agent belongs to another
        # user (or does not exist at all) — preventing cross-user leaks via
        # the shared MinIO bucket.
        metadata: AgentConfigMetadata = await self._config_repository.get(name)
        yaml_content = await self._config_store.get(metadata.name)
        config = self._config_loader.load_from_string(yaml_content)
        logger.info(LogMessage.AGENT_CONFIG_LOADED_FROM_STORE, name)
        return config
