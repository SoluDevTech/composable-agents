"""Use case: list all API keys owned by a user.

Returns safe :class:`ApiKeyView` projections (no hash, no plaintext). Revoked
keys are included.
"""

import logging

from src.domain.entities.auth.api_key import ApiKeyView
from src.domain.logging.messages import LogMessage
from src.domain.ports.auth.api_key_repository import ApiKeyRepository

logger = logging.getLogger(__name__)


class ListApiKeysUseCase:
    """List all API keys for a user.

    Depends only on the :class:`ApiKeyRepository` port (DIP).
    """

    def __init__(self, repo: ApiKeyRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> list[ApiKeyView]:
        """Return all API keys owned by ``user_id`` (newest first).

        Args:
            user_id: Owner whose keys are returned.

        Returns:
            A list of :class:`ApiKeyView` (possibly empty).
        """
        keys = await self._repo.list_by_user(user_id)
        logger.info(LogMessage.API_KEY_LISTED, len(keys), user_id)
        return keys
