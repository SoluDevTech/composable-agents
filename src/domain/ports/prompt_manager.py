from abc import ABC, abstractmethod

from phoenix.client.resources.prompts import PromptVersion

from src.domain.entities.prompt import Prompt


class PromptManager(ABC):
    """Port for managing prompts in external registry (e.g., Phoenix)."""

    @abstractmethod
    async def get_prompt(
        self,
        identifier: str,
        version_id: str | None = None,
        tag: str | None = None,
    ) -> Prompt:
        """Retrieve a prompt by identifier, version, or tag."""
        ...

    @abstractmethod
    async def get_prompt_content(self, identifier: str, version_id: str | None = None, tag: str | None = None) -> dict:
        """Retrieve the content of a prompt by identifier, version, or tag."""
        ...

    @abstractmethod
    async def create_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]],
        model_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> PromptVersion:
        """Create a new prompt."""
        ...

    @abstractmethod
    async def update_prompt(
        self,
        identifier: str,
        content: list[dict[str, str]] | None = None,
        model_name: str | None = None,
        description: str | None = None,
    ) -> PromptVersion:
        """Update an existing prompt (creates new version)."""
        ...

    @abstractmethod
    async def add_tag(self, identifier: str, tag: str) -> None:
        """Add a tag to a prompt."""
        ...
