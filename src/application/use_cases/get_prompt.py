import logging

from src.domain.entities.prompt import Prompt
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")


class GetPromptUseCase:
    """Retrieve a prompt from the registry."""

    def __init__(self, prompt_manager: PromptManager):
        self._prompt_manager = prompt_manager

    async def execute(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> Prompt:
        """Get a prompt."""
        logger.info(f"Retrieving prompt: {identifier}")
        prompt = await self._prompt_manager.get_prompt(
            identifier=identifier,
            version_id=version_id,
            tag=tag,
        )
        return prompt
