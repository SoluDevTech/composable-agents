import asyncio
import logging
from pathlib import Path

import yaml

from src.application.utils import create_agent_metadata
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

        yaml_files = sorted(agents_dir.glob("*.yaml"))
        tasks = [self._seed_agent(yaml_file) for yaml_file in yaml_files]
        await asyncio.gather(*tasks, return_exceptions=False)

    async def _seed_agent(self, yaml_file: Path) -> None:
        """Seed a single agent: load from file, inline prompt, upload, and save metadata.

        Args:
            yaml_file: Path to the agent YAML file.
        """
        agent_name = yaml_file.stem

        if await self._config_repository.exists(agent_name):
            logger.debug("Agent '%s' already seeded, skipping", agent_name)
            return

        config = self._config_loader.load(yaml_file)
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))

        if raw.get("system_prompt_file"):
            raw.pop("system_prompt_file")
            raw["system_prompt"] = config.system_prompt

        yaml_content = yaml.dump(raw, default_flow_style=False, allow_unicode=True)

        await self._config_store.put(f"{agent_name}.yaml", yaml_content)
        metadata = create_agent_metadata(agent_name, config, is_builtin=True)
        await self._config_repository.save(metadata)

        logger.info("Seeded built-in agent '%s'", agent_name)
