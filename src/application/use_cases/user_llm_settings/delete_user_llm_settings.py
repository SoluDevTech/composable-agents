"""Use case: delete the authenticated user's LLM provider settings.

Depends only on the :class:`UserLlmSettingsRepository` port (DIP). Idempotent:
deleting absent settings is a no-op success.
"""

import logging

from src.domain.ports.user_llm_settings_repository import UserLlmSettingsRepository

logger = logging.getLogger(__name__)


class DeleteUserLlmSettingsUseCase:
    """Delete the authenticated user's LLM provider settings (idempotent)."""

    def __init__(self, repo: UserLlmSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> None:
        """Delete the user's settings. No-op when absent.

        Args:
            user_id: Owner identifier.
        """
        await self._repo.delete(user_id)
