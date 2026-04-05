from abc import ABC, abstractmethod
from pathlib import Path

from src.domain.entities.agent_config import AgentConfig


class AgentConfigLoader(ABC):
    @abstractmethod
    def load(self, config_path: str | Path) -> AgentConfig:
        """Charge et valide une configuration d'agent depuis un fichier."""
        ...

    @abstractmethod
    def load_from_string(self, yaml_content: str, source: str = "<string>") -> AgentConfig:
        """Parse et valide une configuration d'agent depuis une chaine YAML.

        Raises:
            ConfigError: If the YAML is invalid or contains system_prompt_file.
        """
        ...
