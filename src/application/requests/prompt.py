from pydantic import BaseModel, Field


class CreatePromptRequest(BaseModel):
    identifier: str = Field(..., min_length=1)
    content: list[dict[str, str]]
    model_name: str
    description: str | None = None
    tags: list[str] | None = None


class UpdatePromptRequest(BaseModel):
    content: list[dict[str, str]] | None = None
    model_name: str | None = None
    description: str | None = None
