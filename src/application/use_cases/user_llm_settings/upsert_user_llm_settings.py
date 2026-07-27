"""Use case: upsert the authenticated user's LLM provider settings.

Encrypts the API key via :class:`FernetCrypto` before delegating to the
:class:`UserLlmSettingsRepository` port (DIP). Returns the upserted settings
with a masked API key (never the plaintext).
"""

import logging

from src.domain.entities.user_llm_settings import UserLlmSettings, UserLlmSettingsInput
from src.domain.ports.user_llm_settings_repository import UserLlmSettingsRepository
from src.infrastructure.crypto.fernet_crypto import FernetCrypto

logger = logging.getLogger(__name__)


class UpsertUserLlmSettingsUseCase:
    """Insert or update the authenticated user's LLM provider settings.

    Depends on the :class:`UserLlmSettingsRepository` port and the
    :class:`FernetCrypto` helper (both injected).
    """

    def __init__(self, repo: UserLlmSettingsRepository, crypto: FernetCrypto) -> None:
        self._repo = repo
        self._crypto = crypto

    async def execute(self, user_id: str, inp: UserLlmSettingsInput) -> UserLlmSettings:
        """Encrypt the API key and upsert the user's settings.

        Args:
            user_id: Owner identifier.
            inp: Input DTO carrying the plaintext API key.

        Returns:
            The upserted :class:`UserLlmSettings` (masked key).
        """
        api_key_encrypted = self._crypto.encrypt(inp.api_key)
        return await self._repo.upsert(
            user_id=user_id,
            provider=inp.provider,
            base_url=inp.base_url,
            api_key_encrypted=api_key_encrypted,
        )
