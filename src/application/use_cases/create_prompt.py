import logging

from src.domain.entities.prompt import PromptVersion
from src.domain.logging.messages import LogMessage
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class CreatePromptUseCase:
    """Create a new prompt in the registry."""

    def __init__(self, prompt_manager: PromptManager):
        self._prompt_manager = prompt_manager

    async def execute(
        self,
        identifier: str,
        content: list[dict[str, str]],
        model_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> PromptVersion:
        """Create a new prompt."""
        logger.info(LogMessage.PROMPT_CREATING, identifier)
        prompt = await self._prompt_manager.create_prompt(
            identifier=identifier,
            content=content,
            model_name=model_name,
            description=description,
            tags=tags,
            metadata=metadata,
        )
        logger.info(LogMessage.PROMPT_CREATED_SUCCESS, identifier)
        return prompt
