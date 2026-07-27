"""Domain entity for per-user LLM provider settings.

A user configures their own OpenAI-compatible LLM provider (provider label,
base URL, API key). The API key is stored encrypted at rest (Fernet) and never
returned in plaintext by any GET endpoint — only a masked preview is exposed.

Attributes:
    user_id: Owner identifier (from the auth context).
    provider: Free-form label, e.g. "openai", "openrouter" (display only).
    base_url: OpenAI-compatible base URL used by the agent factory.
    api_key_masked: Masked preview of the API key (never the full key) —
        ``None`` when no settings exist.
    created_at: Creation timestamp (UTC).
    updated_at: Last update timestamp (UTC).
"""

from datetime import datetime

from pydantic import BaseModel


class UserLlmSettings(BaseModel):
    """Per-user LLM provider settings (safe projection — no plaintext key)."""

    user_id: str
    provider: str
    base_url: str
    api_key_masked: str | None = None
    created_at: datetime
    updated_at: datetime


class UserLlmSettingsInput(BaseModel):
    """Input DTO for an upsert (PUT) operation.

    The ``api_key`` is plaintext on the wire (HTTPS) and stored encrypted at
    rest by the use case before persistence.
    """

    provider: str
    base_url: str
    api_key: str
