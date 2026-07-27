"""PostgreSQL adapter for the :class:`ApiKeyRepository` port.

Each method opens its own :class:`AsyncSession` (session-per-method) so
concurrent requests do not share a session. ``SQLAlchemyError`` is translated
to :class:`StorageError` everywhere, and ``ApiKeyNotFoundError`` is raised by
``revoke`` when no row matches ``(user_id, key_id)``.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domain.entities.auth.api_key import ApiKeyView
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.security import ApiKeyNotFoundError
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.auth.api_key_repository import ApiKeyRepository
from src.infrastructure.database.models.api_key import ApiKeyModel

logger = logging.getLogger(__name__)


def _model_to_view(model: ApiKeyModel) -> ApiKeyView:
    """Project an :class:`ApiKeyModel` row into a safe :class:`ApiKeyView`.

    The hash is deliberately excluded so it can never leak through the list
    endpoint.

    Args:
        model: The ORM row to project.

    Returns:
        A :class:`ApiKeyView` with no hash field.
    """
    return ApiKeyView(
        id=model.id,
        name=model.name,
        key_prefix=model.key_prefix,
        created_at=model.created_at,
        last_used_at=model.last_used_at,
        revoked_at=model.revoked_at,
    )


class PostgresApiKeyRepository(ApiKeyRepository):
    """Adapter that persists per-user API keys in PostgreSQL via SQLAlchemy async.

    Each method creates its own AsyncSession from the engine, ensuring
    thread-safety and proper session lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def find_active_by_hash(self, key_hash: str) -> tuple[str, str] | None:
        """Return ``(user_id, key_id)`` for the active key matching ``key_hash``.

        Args:
            key_hash: The SHA-256 hex digest of the API key plaintext.

        Returns:
            A ``(user_id, key_id)`` tuple if an active (non-revoked) key matches,
            else ``None``.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                stmt = select(ApiKeyModel.user_id, ApiKeyModel.id).where(
                    ApiKeyModel.key_hash == key_hash,
                    ApiKeyModel.revoked_at.is_(None),
                )
                row = (await session.execute(stmt)).first()
                return (row.user_id, row.id) if row is not None else None
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def create(self, user_id: str, name: str, key_hash: str, key_prefix: str) -> str:
        """Persist a new API key and return its generated id.

        Args:
            user_id: Owner of the key.
            name: Human-readable label.
            key_hash: SHA-256 hex digest of the plaintext (never the plaintext).
            key_prefix: First 10 chars of the plaintext.

        Returns:
            The generated key id (uuid hex).

        Raises:
            StorageError: If the database operation fails.
        """
        key_id = uuid4().hex
        now = datetime.now(UTC)
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                session.add(
                    ApiKeyModel(
                        id=key_id,
                        user_id=user_id,
                        name=name,
                        key_hash=key_hash,
                        key_prefix=key_prefix,
                        revoked_at=None,
                        last_used_at=None,
                        created_at=now,
                    )
                )
                await session.commit()
                logger.info(LogMessage.API_KEY_CREATED, key_id, user_id)
                return key_id
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def list_by_user(self, user_id: str) -> list[ApiKeyView]:
        """Return all API keys owned by ``user_id`` ordered by ``created_at`` desc.

        Revoked keys are included. The hash is never part of the returned views.

        Args:
            user_id: Owner whose keys are returned.

        Returns:
            A list of :class:`ApiKeyView` (possibly empty).

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                stmt = select(ApiKeyModel).where(ApiKeyModel.user_id == user_id).order_by(ApiKeyModel.created_at.desc())
                models = (await session.execute(stmt)).scalars().all()
                views = [_model_to_view(m) for m in models]
                logger.info(LogMessage.API_KEY_LISTED, len(views), user_id)
                return views
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def revoke(self, user_id: str, key_id: str) -> None:
        """Revoke the key ``key_id`` owned by ``user_id``.

        Idempotent: revoking an already-revoked key is a no-op success.

        Args:
            user_id: Owner of the key (a key owned by another user is treated
                as not found).
            key_id: Id of the key to revoke.

        Raises:
            ApiKeyNotFoundError: If no key matches ``(user_id, key_id)``.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                stmt = select(ApiKeyModel).where(
                    ApiKeyModel.id == key_id,
                    ApiKeyModel.user_id == user_id,
                )
                model = (await session.execute(stmt)).scalar_one_or_none()
                if model is None:
                    raise ApiKeyNotFoundError(ErrorMessage.API_KEY_NOT_FOUND.format(key_id=key_id))
                if model.revoked_at is not None:
                    # Idempotent: already revoked — no-op success.
                    return
                model.revoked_at = datetime.now(UTC)
                await session.commit()
                logger.info(LogMessage.API_KEY_REVOKED, key_id, user_id)
            except ApiKeyNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e

    async def touch_last_used(self, key_id: str) -> None:
        """Update ``last_used_at`` to now for ``key_id``.

        Silent no-op if the key does not exist (used on the auth hot path where
        a stale/revoked key may still be presented).

        Args:
            key_id: Id of the key that was just used.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                stmt = update(ApiKeyModel).where(ApiKeyModel.id == key_id).values(last_used_at=datetime.now(UTC))
                await session.execute(stmt)
                await session.commit()
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_API_KEY_OP.format(error=e)) from e
