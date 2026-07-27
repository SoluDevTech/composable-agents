"""Use case: get the authenticated user's LLM provider settings (masked).

Depends only on the :class:`UserLlmSettingsRepository` port (DIP).
"""

import logging

from src.domain.entities.user_llm_settings import UserLlmSettings
from src.domain.ports.user_llm_settings_repository import UserLlmSettingsRepository

logger = logging.getLogger(__name__)


class GetUserLlmSettingsUseCase:
    """Get the authenticated user's LLM provider settings (masked API key)."""

    def __init__(self, repo: UserLlmSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> UserLlmSettings | None:
        """Return the user's settings, or ``None`` if not configured.

        Args:
            user_id: Owner identifier.

        Returns:
            A :class:`UserLlmSettings` (masked key) or ``None``.
        """
        return await self._repo.get(user_id)
