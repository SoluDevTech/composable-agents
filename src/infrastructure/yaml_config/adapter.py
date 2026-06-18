import logging
from pathlib import Path

import yaml

from src.domain.entities.agent_config import AgentConfig
from src.domain.errors.config import ConfigError, ConfigNotFoundError, ConfigValidationError
from src.domain.errors.messages import ErrorMessage
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_loader import AgentConfigLoader

logger = logging.getLogger(__name__)


class YamlAgentConfigLoader(AgentConfigLoader):
    """Charge et valide une configuration d'agent depuis un fichier YAML."""

    @staticmethod
    def _parse_yaml(content: str, source: str) -> dict:
        try:
            raw = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.exception(LogMessage.YAML_PARSE_FAILED, source)
            raise ConfigError(ErrorMessage.YAML_INVALID.format(source=source, error=e)) from e

        if not isinstance(raw, dict):
            logger.error(LogMessage.YAML_NOT_MAPPING_LOG, source, type(raw).__name__)
            raise ConfigError(ErrorMessage.YAML_NOT_MAPPING.format(source=source, type=type(raw).__name__))

        return raw

    @staticmethod
    def _validate(raw: dict, source: str) -> AgentConfig:
        try:
            return AgentConfig.model_validate(raw)
        except Exception as e:
            if hasattr(e, "errors"):
                logger.exception(LogMessage.YAML_VALIDATION_FAILED, source)
                raise ConfigValidationError(e.errors()) from e
            logger.exception(LogMessage.YAML_VALIDATION_FAILED, source)
            raise ConfigError(ErrorMessage.YAML_VALIDATION_ERROR.format(error=e)) from e

    def load(self, config_path: str | Path) -> AgentConfig:
        path = Path(config_path)

        if not path.exists():
            logger.error(LogMessage.CONFIG_FILE_NOT_FOUND_LOG, path)
            raise ConfigNotFoundError(ErrorMessage.YAML_CONFIG_NOT_FOUND.format(path=path))

        raw = self._parse_yaml(path.read_text(encoding="utf-8"), str(path))

        if raw.get("system_prompt_file"):
            prompt_path = path.parent / raw["system_prompt_file"]
            if not prompt_path.exists():
                logger.error(LogMessage.PROMPT_FILE_NOT_FOUND_LOG, prompt_path)
                raise ConfigNotFoundError(ErrorMessage.YAML_PROMPT_FILE_NOT_FOUND.format(path=prompt_path))
            raw["system_prompt"] = prompt_path.read_text(encoding="utf-8")
            raw.pop("system_prompt_file")

        return self._validate(raw, str(path))

    def load_from_string(self, yaml_content: str, source: str = "<string>") -> AgentConfig:
        if not yaml_content or not yaml_content.strip():
            logger.error(LogMessage.YAML_EMPTY_LOG, source)
            raise ConfigError(ErrorMessage.YAML_EMPTY.format(source=source))

        raw = self._parse_yaml(yaml_content, source)

        if raw.get("system_prompt_file"):
            logger.error(LogMessage.YAML_SYSTEM_PROMPT_FILE_DISALLOWED, source)
            raise ConfigError(
                ErrorMessage.YAML_SYSTEM_PROMPT_FILE_DISALLOWED.format(source=source)
            )

        return self._validate(raw, source)
