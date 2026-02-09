from abc import ABC, abstractmethod
from pathlib import Path
from src.domain.entities.agent_config import AgentConfig


class AgentConfigLoader(ABC):
    @abstractmethod
    def load(self, config_path: str | Path) -> AgentConfig:
        """Charge et valide une configuration d'agent depuis un fichier."""
        ...
