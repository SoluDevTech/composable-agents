import logging
import os

from phoenix.client import Client
from phoenix.client.resources.prompts import PromptVersion as PhoenixPromptVersion

from src.domain.entities.prompt import Prompt, PromptVersion
from src.domain.ports.prompt_manager import PromptManager

logger = logging.getLogger("composable-agents")


class PhoenixPromptManagerImpl(PromptManager):
    """Phoenix implementation of PromptManager port."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        base_url = base_url or os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
        api_key = api_key or os.getenv("PHOENIX_API_KEY")
        try:
            self._client = Client(
                base_url=base_url,
                api_key=api_key,
            )
            logger.info(f"PhoenixPromptManagerImpl initialized with base_url={base_url}")
        except Exception as e:
            logger.error(f"Failed to initialize Phoenix client: {e}")
            self._client = None

    async def get_prompt(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> Prompt:
        """Retrieve a prompt from Phoenix."""
        if not self._client:
            raise RuntimeError("Phoenix client not initialized")

        try:
            prompt_obj: PhoenixPromptVersion = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )
            if not prompt_obj:
                raise ValueError(f"Prompt not found: {identifier}")
            return self._to_domain_prompt(prompt_obj, identifier=identifier, description=prompt_obj._description)
        except Exception as e:
            logger.error(f"Error getting prompt {identifier}: {e}")
            raise

    async def get_prompt_content(self, identifier: str, version_id: str | None = None, tag: str | None = None) -> dict[str, str]:
        """Get the content of a prompt."""
        if not self._client:
            raise RuntimeError("Phoenix client not initialized")

        try:
            prompt_obj: PhoenixPromptVersion = self._client.prompts.get(
                prompt_identifier=identifier,
                prompt_version_id=version_id,
                tag=tag,
            )
            if not prompt_obj:
                raise ValueError(f"Prompt not found: {identifier}")
            return prompt_obj._template.get("messages", [])[0] if isinstance(prompt_obj._template, dict) else {}
        except Exception as e:
            logger.error(f"Error getting prompt {identifier}: {e}")
            raise

    async def create_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]],
        model_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> PhoenixPromptVersion:
        """Create a new prompt in Phoenix."""
        if not self._client:
            raise RuntimeError("Phoenix client not initialized")

        try:
            prompt_obj = self._client.prompts.create(
                name=identifier,
                version=PhoenixPromptVersion(content, model_name=model_name),
                prompt_description=description,
            )

            if tags:
                for tag in tags:
                    try:
                        self._client.prompts.tag(prompt_identifier=identifier, tag=tag)
                    except Exception as tag_error:
                        logger.warning(f"Failed to add tag {tag}: {tag_error}")

            logger.info(f"Created prompt {identifier}")
            return prompt_obj
        except Exception as e:
            logger.error(f"Error creating prompt {identifier}: {e}")
            raise

    async def update_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
    ) -> PhoenixPromptVersion:
        """Update a prompt (creates new version)."""
        if not self._client:
            raise RuntimeError("Phoenix client not initialized")

        try:
            current = await self.get_prompt(identifier)

            updated = self._client.prompts.create(
                name=identifier,
                version=PhoenixPromptVersion(content, model_name=model_name),
                prompt_description=description or current.description,
            )
            logger.info(f"Updated prompt {identifier}")
            return updated
        except Exception as e:
            logger.error(f"Error updating prompt {identifier}: {e}")
            raise

    async def add_tag(self, identifier: str, tag: str) -> None:
        """Add a tag to a prompt."""
        if not self._client:
            raise RuntimeError("Phoenix client not initialized")

        try:
            self._client.prompts.tag(prompt_identifier=identifier, tag=tag)
            logger.info(f"Added tag {tag} to prompt {identifier}")
        except Exception as e:
            logger.error(f"Error adding tag: {e}")
            raise

    def _to_domain_prompt(self, phoenix_prompt, identifier: str | None = None, description: str | None = None) -> Prompt:
        """Convert Phoenix PromptVersion to domain entity."""
        # Extract messages from the internal template
        template = getattr(phoenix_prompt, "_template", {})
        messages = template.get("messages", []) if isinstance(template, dict) else []

        # Extract model name
        model_name = getattr(phoenix_prompt, "_model_name", "")

        # Extract description
        desc = description or getattr(phoenix_prompt, "_description", None)

        # Extract version id
        version_id = phoenix_prompt.id or "v1"

        domain_version = PromptVersion(
            version_id=version_id,
            content=messages,
            model_name=model_name,
        )

        return Prompt(
            identifier=identifier or "",
            description=desc,
            current_version=domain_version
        )
