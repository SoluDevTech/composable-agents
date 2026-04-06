import logging

from phoenix.client.resources.prompts import PromptVersion

from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")


class UpdatePromptUseCase:
    """Update an existing prompt."""

    def __init__(self, prompt_manager: PromptManager):
        self._prompt_manager = prompt_manager

    async def execute(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
    ) -> PromptVersion:
        """Update a prompt."""
        logger.info(f"Updating prompt: {identifier}")
        prompt = await self._prompt_manager.update_prompt(
            identifier=identifier,
            content=content,
            model_name=model_name,
            description=description,
        )
        logger.info(f"Prompt updated successfully: {identifier}")
        return prompt
