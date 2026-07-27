"""Use case: create a new per-user API key.

Generates the plaintext, hashes it (SHA-256), persists the hash + prefix via
the :class:`ApiKeyRepository` port, and returns a :class:`CreatedApiKey`
containing the plaintext exactly once (never persisted).
"""

import logging
from datetime import UTC, datetime

from src.domain.entities.auth.api_key import CreatedApiKey
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import ApiKeyError
from src.domain.logging.messages import LogMessage
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.infrastructure.auth.api_key_hasher import ApiKeyHasher

logger = logging.getLogger(__name__)


class CreateApiKeyUseCase:
    """Create a new API key for a user.

    Depends only on the :class:`ApiKeyRepository` port (DIP).
    """

    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, name: str) -> CreatedApiKey:
        """Generate, persist and return a new API key.

        Args:
            user_id: Owner of the new key.
            name: Human-readable label (must be non-empty / non-whitespace).

        Returns:
            A :class:`CreatedApiKey` carrying the plaintext (shown once).

        Raises:
            ApiKeyError: If ``name`` is empty or whitespace-only.
        """
        if not name or not name.strip():
            raise ApiKeyError(ErrorMessage.API_KEY_NAME_REQUIRED)

        plaintext = ApiKeyHasher.generate_key()
        key_hash = ApiKeyHasher.hash_key(plaintext)
        key_prefix = plaintext[:10]
        key_id = await self._repo.create(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
        )
        created_at = datetime.now(UTC)
        logger.info(LogMessage.API_KEY_CREATED, key_id, user_id)
        return CreatedApiKey(
            id=key_id,
            name=name,
            key_prefix=key_prefix,
            plaintext=plaintext,
            created_at=created_at,
        )
