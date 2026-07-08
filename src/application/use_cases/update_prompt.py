import logging

from src.domain.entities.prompt import PromptVersion
from src.domain.logging.messages import LogMessage
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class UpdatePromptUseCase:
    """Update an existing prompt."""

    def __init__(self, prompt_manager: PromptManager) -> None:
        self._prompt_manager = prompt_manager

    async def execute(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> PromptVersion:
        """Update a prompt."""
        logger.info(LogMessage.PROMPT_UPDATING, identifier)
        prompt_version = await self._prompt_manager.update_prompt(
            identifier=identifier,
            content=content,
            model_name=model_name,
            description=description,
            metadata=metadata,
        )
        logger.info(LogMessage.PROMPT_UPDATED_SUCCESS, identifier)
        return prompt_version
