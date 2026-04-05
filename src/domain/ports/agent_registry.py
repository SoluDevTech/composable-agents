from abc import ABC, abstractmethod

from src.domain.ports.agent_runner import AgentRunner


class AgentRegistry(ABC):
    """Registre d'agents permettant de recuperer un runner par nom."""

    @abstractmethod
    async def get_runner(self, agent_name: str) -> AgentRunner:
        """Retourne le runner pour l'agent donne, le creant si necessaire.

        Raises:
            AgentNotFoundError: Si aucun agent avec ce nom n'existe.
        """
        ...

    @abstractmethod
    async def list_agents(self) -> list[str]:
        """Liste les noms des agents disponibles."""
        ...

    @abstractmethod
    async def invalidate(self, agent_name: str) -> None:
        """Invalide le runner cache pour l'agent donne."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Libere les ressources des agents crees."""
        ...
