"""Use case: resolve the authenticated user's LLM credentials for the agent factory.

Returns ``(base_url, api_key_plaintext)`` or ``None`` when the user has not
configured a provider. Used by the DeepAgent factory to build a per-user
:class:`ChatOpenAI` instance. Wraps :meth:`UserLlmSettingsRepository.get_decrypted`.
"""

import logging

from src.domain.ports.user_llm_settings_repository import UserLlmSettingsRepository

logger = logging.getLogger(__name__)


class ResolveUserLlmCredentialsUseCase:
    """Resolve the authenticated user's LLM credentials for agent building.

    Depends only on the :class:`UserLlmSettingsRepository` port (DIP).
    """

    def __init__(self, repo: UserLlmSettingsRepository) -> None:
        self._repo = repo

    async def execute(self, user_id: str) -> tuple[str, str] | None:
        """Return ``(base_url, api_key_plaintext)`` or ``None`` if not configured.

        Args:
            user_id: Owner identifier.

        Returns:
            A ``(base_url, api_key_plaintext)`` tuple, or ``None``.
        """
        return await self._repo.get_decrypted(user_id)
