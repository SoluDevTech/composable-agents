from pydantic import BaseModel

from src.domain.entities.prompt import Prompt, PromptVersion


class PromptResponse(BaseModel):
    """Response DTO for prompt operations."""

    status: str
    prompt: Prompt


class PromptVersionResponse(BaseModel):
    """Response DTO for prompt version operations (create/update)."""

    status: str
    prompt_version: PromptVersion
