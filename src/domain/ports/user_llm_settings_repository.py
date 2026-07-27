"""Outbound port: persist and resolve per-user LLM provider settings.

Implemented by :class:`~src.infrastructure.postgres_user_llm.adapter.PostgresUserLlmSettingsRepository`
against the ``user_llm_settings`` table. The agent factory depends on
:meth:`get_decrypted` to resolve the ``(base_url, api_key)`` tuple needed to
build a per-user ``ChatOpenAI`` instance.
"""

from abc import ABC, abstractmethod

from src.domain.entities.user_llm_settings import UserLlmSettings


class UserLlmSettingsRepository(ABC):
    """Outbound port: persist per-user LLM provider settings."""

    @abstractmethod
    async def get(self, user_id: str) -> UserLlmSettings | None:
        """Return the user's settings (masked key), or ``None`` if not configured.

        Args:
            user_id: Owner identifier.

        Returns:
            A :class:`UserLlmSettings` with ``api_key_masked`` (never the full
            key), or ``None`` when the user has no configured provider.
        """
        ...

    @abstractmethod
    async def upsert(
        self,
        user_id: str,
        provider: str,
        base_url: str,
        api_key_encrypted: str,
    ) -> UserLlmSettings:
        """Insert or update the user's settings (encrypted API key).

        Args:
            user_id: Owner identifier.
            provider: Free-form provider label.
            base_url: OpenAI-compatible base URL.
            api_key_encrypted: Fernet-encrypted API key token.

        Returns:
            The upserted :class:`UserLlmSettings` (masked key).
        """
        ...

    @abstractmethod
    async def delete(self, user_id: str) -> None:
        """Delete the user's settings. No-op when absent.

        Args:
            user_id: Owner identifier.
        """
        ...

    @abstractmethod
    async def get_decrypted(self, user_id: str) -> tuple[str, str] | None:
        """Return ``(base_url, api_key_plaintext)`` for the agent factory.

        The plaintext is decrypted on demand (per-request). Returns ``None``
        when the user has no configured provider.

        Args:
            user_id: Owner identifier.

        Returns:
            A ``(base_url, api_key_plaintext)`` tuple, or ``None``.
        """
        ...
