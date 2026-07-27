"""Request DTOs for the API-key management endpoints."""

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    """Request body for creating a new per-user API key.

    ``name`` is required and must be non-empty; FastAPI returns 422 when the
    field is missing or empty (Pydantic ``min_length=1``).
    """

    name: str = Field(..., min_length=1)
