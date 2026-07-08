from pathlib import Path

from src.domain.entities.agent_config import AgentConfig
from src.domain.ports.agent_config_loader import AgentConfigLoader


class LoadAgentConfigUseCase:
    """Charge la configuration d'un agent depuis un fichier."""

    def __init__(self, loader: AgentConfigLoader) -> None:
        self._loader = loader

    async def execute(self, config_path: str | Path) -> AgentConfig:
        return self._loader.load(config_path)
