"""PostgreSQL adapter for the :class:`AgentConfigRepository` port.

Per-user isolation (RLS plumbing): the repository reads the
``current_user_id`` contextvar and filters / sets ``user_id`` accordingly.
When the contextvar is ``None`` (no auth context) no filter is applied so
existing behaviour is preserved.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domain.entities.agent_config_metadata import AgentConfigMetadata
from src.domain.errors.agent import AgentNotFoundError
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.infrastructure.database.models.agent_config import AgentConfigModel
from src.infrastructure.database.rls_context import current_user_id

logger = logging.getLogger(__name__)


def _model_to_metadata(model: AgentConfigModel) -> AgentConfigMetadata:
    return AgentConfigMetadata(
        name=model.name,
        model=model.model,
        minio_path=model.minio_path,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
        user_id=model.user_id,
    )


class PostgresAgentConfigRepository(AgentConfigRepository):
    """Adapter that persists agent configuration metadata in PostgreSQL via SQLAlchemy async.

    Each method creates its own AsyncSession from the engine, ensuring thread-safety
    and proper session lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @staticmethod
    def _current_user_id() -> str | None:
        """Return the ``current_user_id`` contextvar value or ``None``."""
        return current_user_id.get()

    async def save(self, metadata: AgentConfigMetadata) -> None:
        """Insert or update agent configuration metadata.

        Uses merge for upsert semantics: insert if new, update if exists.
        The row's ``user_id`` is set from the ``current_user_id`` contextvar
        (or ``""`` when unset).

        Args:
            metadata: The agent configuration metadata to persist.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id() or ""
                model = AgentConfigModel(
                    name=metadata.name,
                    model=metadata.model,
                    minio_path=metadata.minio_path,
                    description=metadata.description,
                    created_at=metadata.created_at,
                    updated_at=metadata.updated_at,
                    user_id=uid,
                )
                await session.merge(model)
                await session.commit()
                logger.info(LogMessage.AGENT_CONFIG_METADATA_SAVED, metadata.name)
            except SQLAlchemyError as e:
                raise StorageError(
                    ErrorMessage.STORAGE_FAILED_SAVE_AGENT_CONFIG.format(name=metadata.name, error=e)
                ) from e

    async def get(self, name: str) -> AgentConfigMetadata:
        """Retrieve metadata by agent name.

        When ``current_user_id`` is set, a ``WHERE user_id == <ctx>`` filter
        is applied so a config owned by another user appears as not found.

        Args:
            name: The agent name to look up.

        Returns:
            The agent configuration metadata.

        Raises:
            AgentNotFoundError: If no row exists for this name (or it is
                owned by another user when the contextvar is set).
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                if uid is None:
                    model = await session.get(AgentConfigModel, name)
                else:
                    stmt = select(AgentConfigModel).where(
                        AgentConfigModel.name == name, AgentConfigModel.user_id == uid
                    )
                    model = (await session.execute(stmt)).scalar_one_or_none()
                if model is None:
                    raise AgentNotFoundError(ErrorMessage.AGENT_CONFIG_NOT_FOUND.format(name=name))
                return _model_to_metadata(model)
            except AgentNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_GET_AGENT_CONFIG.format(name=name, error=e)) from e

    async def list_all(self) -> list[AgentConfigMetadata]:
        """List all agent configuration metadata visible to the current user.

        When ``current_user_id`` is set, only configs with
        ``user_id == <ctx>`` are returned. When the contextvar is ``None`` no
        filter is applied (existing behaviour).

        Returns:
            A list of all visible metadata entries.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                stmt = select(AgentConfigModel).order_by(AgentConfigModel.name)
                if uid is not None:
                    stmt = stmt.where(AgentConfigModel.user_id == uid)
                result = await session.execute(stmt)
                models = result.scalars().all()
                return [_model_to_metadata(m) for m in models]
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_LIST_AGENT_CONFIG.format(error=e)) from e

    async def delete(self, name: str) -> None:
        """Delete metadata by agent name.

        When ``current_user_id`` is set, only a config owned by the current
        user can be deleted (otherwise :class:`AgentNotFoundError` is raised).

        Args:
            name: The agent name to delete.

        Raises:
            AgentNotFoundError: If no row was deleted (or the config is owned
                by another user when the contextvar is set).
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                if uid is None:
                    model = await session.get(AgentConfigModel, name)
                else:
                    stmt = select(AgentConfigModel).where(
                        AgentConfigModel.name == name, AgentConfigModel.user_id == uid
                    )
                    model = (await session.execute(stmt)).scalar_one_or_none()
                if model is None:
                    raise AgentNotFoundError(ErrorMessage.AGENT_CONFIG_NOT_FOUND.format(name=name))
                await session.delete(model)
                await session.commit()
                logger.info(LogMessage.AGENT_CONFIG_METADATA_DELETED, name)
            except AgentNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_DELETE_AGENT_CONFIG.format(name=name, error=e)) from e

    async def exists(self, name: str) -> bool:
        """Check whether metadata exists for the given agent name.

        When ``current_user_id`` is set, only configs owned by the current
        user are considered.

        Args:
            name: The agent name to check.

        Returns:
            True if metadata exists (and is owned by the current user when the
            contextvar is set), False otherwise.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                uid = self._current_user_id()
                if uid is None:
                    model = await session.get(AgentConfigModel, name)
                    return model is not None
                stmt = select(AgentConfigModel.name).where(
                    AgentConfigModel.name == name, AgentConfigModel.user_id == uid
                )
                model = (await session.execute(stmt)).scalar_one_or_none()
                return model is not None
            except SQLAlchemyError as e:
                raise StorageError(ErrorMessage.STORAGE_FAILED_EXISTS_AGENT_CONFIG.format(name=name, error=e)) from e
