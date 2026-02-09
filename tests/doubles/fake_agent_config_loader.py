from pathlib import Path
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import ConfigNotFoundError


class FakeAgentConfigLoader(AgentConfigLoader):
    """Fake pour les tests unitaires."""

    def __init__(self):
        self._configs: dict[str, AgentConfig] = {}

    def add_config(self, path: str, config: AgentConfig):
        self._configs[path] = config

    def load(self, config_path: str | Path) -> AgentConfig:
        key = str(config_path)
        if key not in self._configs:
            raise ConfigNotFoundError(f"Fichier introuvable: {config_path}")
        return self._configs[key]
