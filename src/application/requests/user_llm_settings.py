"""Request DTOs for the LLM-settings management endpoints."""

from pydantic import BaseModel, Field


class UpsertUserLlmSettingsRequest(BaseModel):
    """Request body for upserting per-user LLM provider settings.

    All fields are required and must be non-empty; FastAPI returns 422 when a
    field is missing or empty (Pydantic ``min_length=1``).
    """

    provider: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
