"""PostgreSQL adapter for the :class:`UserLlmSettingsRepository` port.

Each method opens its own :class:`AsyncSession` (session-per-method). The
``get`` method decrypts the API key on demand (via the injected
:class:`FernetCrypto`) and returns a masked preview (``api_key_masked``) —
never the full plaintext. ``get_decrypted`` returns the plaintext for the
agent factory (per-request decryption; Fernet is fast).

The repository is RLS-aware: the SQLAlchemy ``before_cursor_execute`` listener
emits ``SET LOCAL app.user_id`` so PostgreSQL Row-Level Security policies
filter rows per user. On SQLite (tests) the contextvar is ignored and
``user_id`` is the primary key, so isolation is inherent.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domain.entities.user_llm_settings import UserLlmSettings
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.user_llm_settings_repository import UserLlmSettingsRepository
from src.infrastructure.crypto.fernet_crypto import FernetCrypto
from src.infrastructure.database.models.user_llm_setting import UserLlmSettingModel

logger = logging.getLogger(__name__)


def _mask(api_key_plaintext: str) -> str:
    """Return a masked preview of an API key (first 3 + ``...`` + last 3).

    For very short keys (<=6 chars) the whole key is masked as ``***``.

    Args:
        api_key_plaintext: The decrypted API key.

    Returns:
        A masked string safe to expose in GET responses.
    """
    if len(api_key_plaintext) <= 6:
        return "***"
    return f"{api_key_plaintext[:3]}...{api_key_plaintext[-3:]}"


class PostgresUserLlmSettingsRepository(UserLlmSettingsRepository):
    """Adapter that persists per-user LLM settings in PostgreSQL via SQLAlchemy async.

    The :class:`FernetCrypto` dependency is injected so the adapter stays
    decoupled from application settings (DIP). Each method creates its own
    AsyncSession from the engine, ensuring thread-safety and proper session
    lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine, crypto: FernetCrypto) -> None:
        self._engine = engine
        self._crypto = crypto

    async def get(self, user_id: str) -> UserLlmSettings | None:
        """Return the user's settings with a masked API key, or ``None``.

        Args:
            user_id: Owner identifier.

        Returns:
            A :class:`UserLlmSettings` with ``api_key_masked`` (decrypted then
            masked on demand — never the full key), or ``None`` if absent.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(UserLlmSettingModel, user_id)
                if model is None:
                    return None
                # Decrypt to mask — the masked preview is derived from the
                # plaintext (more useful than masking the encrypted token). If
                # decryption fails (corrupted / wrong key), fall back to None
                # rather than crashing the GET.
                masked: str | None
                try:
                    plaintext = self._crypto.decrypt(model.api_key_encrypted)
                    masked = _mask(plaintext)
                except Exception:
                    logger.warning(LogMessage.LLM_SETTINGS_DECRYPT_FAILED, user_id)
                    masked = None
                return UserLlmSettings(
                    user_id=model.user_id,
                    provider=model.provider,
                    base_url=model.base_url,
                    api_key_masked=masked,
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

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

        Raises:
            StorageError: If the database operation fails.
        """
        now = datetime.now(UTC)
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(UserLlmSettingModel, user_id)
                if model is None:
                    model = UserLlmSettingModel(
                        user_id=user_id,
                        provider=provider,
                        base_url=base_url,
                        api_key_encrypted=api_key_encrypted,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(model)
                else:
                    model.provider = provider
                    model.base_url = base_url
                    model.api_key_encrypted = api_key_encrypted
                    model.updated_at = now
                await session.commit()
                # Build masked preview by decrypting the just-stored token.
                masked: str | None
                try:
                    masked = _mask(self._crypto.decrypt(api_key_encrypted))
                except Exception:
                    masked = None
                return UserLlmSettings(
                    user_id=model.user_id,
                    provider=model.provider,
                    base_url=model.base_url,
                    api_key_masked=masked,
                    created_at=model.created_at,
                    updated_at=model.updated_at,
                )
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def delete(self, user_id: str) -> None:
        """Delete the user's settings. No-op when absent.

        Args:
            user_id: Owner identifier.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(UserLlmSettingModel, user_id)
                if model is None:
                    return
                await session.delete(model)
                await session.commit()
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def get_decrypted(self, user_id: str) -> tuple[str, str] | None:
        """Return ``(base_url, api_key_plaintext)`` for the agent factory.

        Args:
            user_id: Owner identifier.

        Returns:
            A ``(base_url, api_key_plaintext)`` tuple, or ``None`` if absent.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(UserLlmSettingModel, user_id)
                if model is None:
                    return None
                plaintext = self._crypto.decrypt(model.api_key_encrypted)
                return model.base_url, plaintext
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e
