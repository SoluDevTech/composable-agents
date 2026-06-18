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

logger = logging.getLogger(__name__)


def _model_to_metadata(model: AgentConfigModel) -> AgentConfigMetadata:
    return AgentConfigMetadata(
        name=model.name,
        model=model.model,
        minio_path=model.minio_path,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class PostgresAgentConfigRepository(AgentConfigRepository):
    """Adapter that persists agent configuration metadata in PostgreSQL via SQLAlchemy async.

    Each method creates its own AsyncSession from the engine, ensuring thread-safety
    and proper session lifecycle for concurrent operations.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, metadata: AgentConfigMetadata) -> None:
        """Insert or update agent configuration metadata.

        Uses merge for upsert semantics: insert if new, update if exists.

        Args:
            metadata: The agent configuration metadata to persist.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = AgentConfigModel(
                    name=metadata.name,
                    model=metadata.model,
                    minio_path=metadata.minio_path,
                    created_at=metadata.created_at,
                    updated_at=metadata.updated_at,
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

        Args:
            name: The agent name to look up.

        Returns:
            The agent configuration metadata.

        Raises:
            AgentNotFoundError: If no row exists for this name.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(AgentConfigModel, name)
                if model is None:
                    raise AgentNotFoundError(ErrorMessage.AGENT_CONFIG_NOT_FOUND.format(name=name))
                return _model_to_metadata(model)
            except AgentNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(
                    ErrorMessage.STORAGE_FAILED_GET_AGENT_CONFIG.format(name=name, error=e)
                ) from e

    async def list_all(self) -> list[AgentConfigMetadata]:
        """List all agent configuration metadata.

        Returns:
            A list of all stored metadata entries.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                result = await session.execute(select(AgentConfigModel).order_by(AgentConfigModel.name))
                models = result.scalars().all()
                return [_model_to_metadata(m) for m in models]
            except SQLAlchemyError as e:
                raise StorageError(
                    ErrorMessage.STORAGE_FAILED_LIST_AGENT_CONFIG.format(error=e)
                ) from e

    async def delete(self, name: str) -> None:
        """Delete metadata by agent name.

        Args:
            name: The agent name to delete.

        Raises:
            AgentNotFoundError: If no row was deleted.
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(AgentConfigModel, name)
                if model is None:
                    raise AgentNotFoundError(ErrorMessage.AGENT_CONFIG_NOT_FOUND.format(name=name))
                await session.delete(model)
                await session.commit()
                logger.info(LogMessage.AGENT_CONFIG_METADATA_DELETED, name)
            except AgentNotFoundError:
                raise
            except SQLAlchemyError as e:
                raise StorageError(
                    ErrorMessage.STORAGE_FAILED_DELETE_AGENT_CONFIG.format(name=name, error=e)
                ) from e

    async def exists(self, name: str) -> bool:
        """Check whether metadata exists for the given agent name.

        Args:
            name: The agent name to check.

        Returns:
            True if metadata exists, False otherwise.

        Raises:
            StorageError: If the database operation fails.
        """
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            try:
                model = await session.get(AgentConfigModel, name)
                return model is not None
            except SQLAlchemyError as e:
                raise StorageError(
                    ErrorMessage.STORAGE_FAILED_EXISTS_AGENT_CONFIG.format(name=name, error=e)
                ) from e
