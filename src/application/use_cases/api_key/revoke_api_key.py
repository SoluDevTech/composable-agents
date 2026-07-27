"""Use case: revoke an API key owned by a user.

Delegates to the :class:`ApiKeyRepository` port which raises
:class:`ApiKeyNotFoundError` when no key matches ``(user_id, key_id)`` (the
key does not exist or is owned by another user). Revoking an already-revoked
key is an idempotent no-op success.
"""

import logging

from src.domain.logging.messages import LogMessage
from src.domain.ports.auth.api_key_repository import ApiKeyRepository

logger = logging.getLogger(__name__)


class RevokeApiKeyUseCase:
    """Revoke an API key for a user.

    Depends only on the :class:`ApiKeyRepository` port (DIP).
    """

    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str, key_id: str) -> None:
        """Revoke the key ``key_id`` owned by ``user_id``.

        Args:
            user_id: Owner of the key.
            key_id: Id of the key to revoke.

        Raises:
            ApiKeyNotFoundError: If no key matches ``(user_id, key_id)``.
        """
        await self._repo.revoke(user_id=user_id, key_id=key_id)
        logger.info(LogMessage.API_KEY_REVOKED, key_id, user_id)
