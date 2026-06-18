import logging

from src.domain.entities.prompt import Prompt
from src.domain.logging.messages import LogMessage
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


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
        logger.info(LogMessage.PROMPT_RETRIEVING, identifier)
        prompt = await self._prompt_manager.get_prompt(
            identifier=identifier,
            version_id=version_id,
            tag=tag,
        )
        return prompt

    async def execute_get_prompt_content(self, identifier: str, version_id: str | None = None, tag: str | None = None) -> dict:
        """Get the content of a prompt."""
        logger.info(LogMessage.PROMPT_RETRIEVING_CONTENT, identifier)
        content = await self._prompt_manager.get_prompt_content(
            identifier=identifier,
            version_id=version_id,
            tag=tag,
        )
        return content
