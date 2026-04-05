import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore

logger = logging.getLogger("composable-agents")


class SeedAgentsUseCase:
    """Seed built-in agent configurations from a local directory into persistent storage."""

    def __init__(
        self,
        config_loader: AgentConfigLoader,
        config_store: AgentConfigStore,
        config_repository: AgentConfigRepository,
    ) -> None:
        self._config_loader = config_loader
        self._config_store = config_store
        self._config_repository = config_repository

    async def execute(self, agents_dir: Path) -> None:
        """For each YAML file in agents_dir, upload to MinIO and save metadata if not already present.

        If a YAML references system_prompt_file, the prompt is read from disk and inlined
        before uploading so that the stored YAML is self-contained.

        Args:
            agents_dir: Path to the directory containing seed agent YAML files.
        """
        if not agents_dir.exists():
            logger.warning("Agents directory does not exist: %s", agents_dir)
            return

        for yaml_file in sorted(agents_dir.glob("*.yaml")):
            agent_name = yaml_file.stem

            if await self._config_repository.exists(agent_name):
                logger.debug("Agent '%s' already seeded, skipping", agent_name)
                continue

            config = self._config_loader.load(yaml_file)

            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if raw.get("system_prompt_file"):
                raw.pop("system_prompt_file")
                raw["system_prompt"] = config.system_prompt
            yaml_content = yaml.dump(raw, default_flow_style=False, allow_unicode=True)

            await self._config_store.put(agent_name, yaml_content)

            now = datetime.now(UTC)
            metadata = AgentConfigMetadata(
                name=agent_name,
                model=config.model,
                minio_path=f"{agent_name}.yaml",
                is_builtin=True,
                created_at=now,
                updated_at=now,
            )
            await self._config_repository.save(metadata)

            logger.info("Seeded built-in agent '%s'", agent_name)
