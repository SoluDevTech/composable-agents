import logging
from pathlib import Path

import yaml

from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import ConfigError, ConfigNotFoundError, ConfigValidationError
from src.domain.ports.agent_config_loader import AgentConfigLoader

logger = logging.getLogger(__name__)


class YamlAgentConfigLoader(AgentConfigLoader):
    """Charge et valide une configuration d'agent depuis un fichier YAML."""

    @staticmethod
    def _parse_yaml(content: str, source: str) -> dict:
        try:
            raw = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.exception(f"Invalid YAML from {source}")
            raise ConfigError(f"Invalid YAML from {source}: {e}") from e

        if not isinstance(raw, dict):
            logger.error(f"YAML from {source} must contain a YAML mapping, not {type(raw).__name__}")
            raise ConfigError(f"YAML from {source} must contain a YAML mapping, not {type(raw).__name__}")

        return raw

    @staticmethod
    def _validate(raw: dict, source: str) -> AgentConfig:
        try:
            return AgentConfig.model_validate(raw)
        except Exception as e:
            if hasattr(e, "errors"):
                logger.exception(f"Validation error from {source}")
                raise ConfigValidationError(e.errors()) from e
            logger.exception(f"Validation error from {source}")
            raise ConfigError(f"Validation error: {e}") from e

    def load(self, config_path: str | Path) -> AgentConfig:
        path = Path(config_path)

        if not path.exists():
            logger.error(f"Config file not found: {path}")
            raise ConfigNotFoundError(f"Config file not found: {path}")

        raw = self._parse_yaml(path.read_text(encoding="utf-8"), str(path))

        if raw.get("system_prompt_file"):
            prompt_path = path.parent / raw["system_prompt_file"]
            if not prompt_path.exists():
                logger.error(f"Prompt file not found: {prompt_path}")
                raise ConfigNotFoundError(f"Prompt file not found: {prompt_path}")
            raw["system_prompt"] = prompt_path.read_text(encoding="utf-8")
            raw.pop("system_prompt_file")

        return self._validate(raw, str(path))

    def load_from_string(self, yaml_content: str, source: str = "<string>") -> AgentConfig:
        if not yaml_content or not yaml_content.strip():
            logger.error("Empty YAML content from %s", source)
            raise ConfigError(f"Empty YAML content from {source}")

        raw = self._parse_yaml(yaml_content, source)

        if raw.get("system_prompt_file"):
            logger.error("system_prompt_file is not allowed in string-loaded YAML from %s", source)
            raise ConfigError(
                f"system_prompt_file is not allowed in string-loaded YAML from {source}. "
                "Inline the prompt in system_prompt instead."
            )

        return self._validate(raw, source)
