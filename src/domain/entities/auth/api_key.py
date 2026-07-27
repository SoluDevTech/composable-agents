"""Domain entities for per-user API keys.

``ApiKeyView`` is the safe projection returned by the list endpoint: it never
exposes the hash or the plaintext. ``CreatedApiKey`` is returned once, on
creation, so the caller can display / store the plaintext before it is
discarded (only the SHA-256 hash is persisted).
"""

from datetime import datetime

from pydantic import BaseModel


class ApiKeyView(BaseModel):
    """Safe projection of a stored API key (no hash, no plaintext).

    Attributes:
        id: The key identifier (uuid hex).
        name: Human-readable label given by the owner.
        key_prefix: First 10 chars of the plaintext (``cpk_XXXXX``) used to
            recognize the key without revealing it.
        created_at: Creation timestamp (UTC).
        last_used_at: Last time the key was used to authenticate, or ``None``.
        revoked_at: Revocation timestamp, or ``None`` if the key is still
            active.
    """

    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class CreatedApiKey(BaseModel):
    """Result of creating a new API key.

    The ``plaintext`` is returned exactly once so the caller can display / store
    it; it is never persisted (only its SHA-256 hash is).

    Attributes:
        id: The key identifier (uuid hex).
        name: Human-readable label given by the owner.
        key_prefix: First 10 chars of the plaintext.
        plaintext: The full generated key (``cpk_...``). Shown once.
        created_at: Creation timestamp (UTC).
    """

    id: str
    name: str
    key_prefix: str
    plaintext: str
    created_at: datetime
