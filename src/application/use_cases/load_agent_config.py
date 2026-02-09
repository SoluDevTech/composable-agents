from pathlib import Path
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.entities.agent_config import AgentConfig


class LoadAgentConfigUseCase:
    """Charge la configuration d'un agent depuis un fichier."""

    def __init__(self, loader: AgentConfigLoader):
        self._loader = loader

    def execute(self, config_path: str | Path) -> AgentConfig:
        return self._loader.load(config_path)
