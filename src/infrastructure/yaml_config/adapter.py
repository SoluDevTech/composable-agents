import logging
from pathlib import Path

import yaml

from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import ConfigError, ConfigNotFoundError, ConfigValidationError
from src.domain.ports.agent_config_loader import AgentConfigLoader

logger = logging.getLogger("composable-agents")


class YamlAgentConfigLoader(AgentConfigLoader):
    """Charge et valide une configuration d'agent depuis un fichier YAML."""

    def load(self, config_path: str | Path) -> AgentConfig:
        path = Path(config_path)

        if not path.exists():
            logger.error(f"Config file not found: {path}")
            raise ConfigNotFoundError(f"Config file not found: {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            logger.exception(f"Invalid YAML in {path}")
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e

        if not isinstance(raw, dict):
            logger.error(f"Config file {path} must contain a YAML mapping, not {type(raw).__name__}")
            raise ConfigError(f"Config file {path} must contain a YAML mapping, not {type(raw).__name__}")

        if raw.get("system_prompt_file"):
            prompt_path = path.parent / raw["system_prompt_file"]
            if not prompt_path.exists():
                logger.error(f"Prompt file not found: {prompt_path}")
                raise ConfigNotFoundError(f"Prompt file not found: {prompt_path}")
            raw["system_prompt"] = prompt_path.read_text(encoding="utf-8")
            raw.pop("system_prompt_file")

        try:
            return AgentConfig.model_validate(raw)
        except Exception as e:
            if hasattr(e, "errors"):
                logger.exception(f"Validation error in {path}")
                raise ConfigValidationError(e.errors()) from e
            logger.exception(f"Validation error in {path}")
            raise ConfigError(f"Validation error: {e}") from e
