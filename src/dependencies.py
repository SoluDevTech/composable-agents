import logging

from miniopy_async import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from src.application.use_cases.create_agent_config import CreateAgentConfigUseCase
from src.application.use_cases.delete_agent_config import DeleteAgentConfigUseCase
from src.application.use_cases.get_agent_config import GetAgentConfigUseCase
from src.application.use_cases.list_agent_configs import ListAgentConfigsUseCase
from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.application.use_cases.send_message import SendMessageUseCase
from src.application.use_cases.stream_message import StreamMessageUseCase
from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.application.use_cases.update_agent_config import UpdateAgentConfigUseCase
from src.config import Settings
from src.domain.errors.messages import ErrorMessage
from src.domain.errors.storage import StorageError
from src.domain.logging.messages import LogMessage
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.prompt_manager import PromptManager
from src.domain.ports.thread_repository import ThreadRepository
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader
from src.infrastructure.minio_store.adapter import MinioAgentConfigStore
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry
from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository
from src.infrastructure.postgres_thread.adapter import PostgresThreadRepository
from src.infrastructure.prompt_management.phoenix_prompt_adapter import PhoenixPromptManagerProvider
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

logger = logging.getLogger(__name__)

# ============= CONFIG =============

settings = Settings()

# ============= TRACING =============


def _create_tracing_provider(settings: Settings):
    """Create the appropriate TracingProvider based on settings.

    Args:
        settings: Application settings containing tracing configuration.

    Returns:
        A TracingProvider instance matching the configured provider.
    """
    tracing = settings.tracing

    if tracing.enabled and tracing.provider == "langfuse":
        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        logger.info(LogMessage.TRACING_LANGFUSE_INIT, tracing.langfuse_host)
        return LangfuseTracingProvider(
            public_key=tracing.langfuse_public_key or "",
            secret_key=tracing.langfuse_secret_key or "",
            host=tracing.langfuse_host,
        )

    if tracing.enabled and tracing.provider == "phoenix":
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        logger.info(LogMessage.TRACING_PHOENIX_INIT, tracing.phoenix_collector_endpoint)
        return PhoenixTracingProvider(
            endpoint=tracing.phoenix_collector_endpoint,
            api_key=tracing.phoenix_api_key,
            project_name=tracing.project_name,
        )

    logger.info(LogMessage.TRACING_DISABLED)
    return NoopTracingProvider()


def get_prompt_manager() -> PromptManager:
    """Provide PromptManager implementation."""
    tracing = settings.tracing
    return PhoenixPromptManagerProvider(
        base_url=tracing.phoenix_collector_endpoint,
        api_key=tracing.phoenix_api_key,
    )


# ============= ADAPTERS =============

agent_config_loader = YamlAgentConfigLoader()
mcp_tool_loader = LangchainMcpToolLoader(tool_timeout=settings.mcp_tool_timeout)
tracing_provider = _create_tracing_provider(settings)

# ============= PERSISTENCE (initialized at startup) =============

_async_engine: AsyncEngine | None = None
_minio_store: MinioAgentConfigStore | None = None
_pg_repository: PostgresAgentConfigRepository | None = None
agent_registry: AgentRegistry | None = None
thread_repository: ThreadRepository | None = None


async def init_persistence() -> None:
    """Initialize persistent infrastructure: SQLAlchemy engine, MinIO store, PostgreSQL repositories.

    Must be called during application startup.
    """
    global _async_engine, _minio_store, _pg_repository, agent_registry, thread_repository

    logger.info(LogMessage.PERSISTENCE_INITIALIZING)

    _async_engine = create_async_engine(
        settings.database_url,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
    )
    logger.info(LogMessage.SQLALCHEMY_ENGINE_CREATED)

    _pg_repository = PostgresAgentConfigRepository(engine=_async_engine)
    thread_repository = PostgresThreadRepository(engine=_async_engine)
    logger.info(LogMessage.POSTGRES_REPOS_INITIALIZED)

    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    _minio_store = MinioAgentConfigStore(client=minio_client, bucket=settings.minio_bucket)
    await _minio_store.ensure_bucket()
    logger.info(LogMessage.MINIO_STORE_INITIALIZED, settings.minio_bucket)

    agent_registry = PersistentAgentRegistry(
        config_loader=agent_config_loader,
        config_store=_minio_store,
        config_repository=_pg_repository,
        mcp_tool_loader=mcp_tool_loader,
        tracing_provider=tracing_provider,
        prompt_manager=get_prompt_manager(),
        stream_idle_timeout=settings.agent_stream_idle_timeout,
        invoke_timeout=settings.agent_invoke_timeout,
    )

    logger.info(LogMessage.PERSISTENCE_REGISTRY_SET)


async def close_persistence() -> None:
    """Close persistent infrastructure resources.

    Must be called during application shutdown.
    """
    if agent_registry and isinstance(agent_registry, PersistentAgentRegistry):
        await agent_registry.close()
        logger.info(LogMessage.PERSISTENT_REGISTRY_CLOSED)

    if _async_engine:
        await _async_engine.dispose()
        logger.info(LogMessage.SQLALCHEMY_ENGINE_DISPOSED)


logger.info(LogMessage.DEPENDENCIES_INITIALIZED)


# ============= USE CASE PROVIDERS =============


def _require_thread_repository() -> ThreadRepository:
    """Return thread repository or raise StorageError if not initialized."""
    if thread_repository is None:
        raise StorageError(ErrorMessage.STORAGE_REPO_NOT_INITIALIZED)
    return thread_repository


def _require_agent_registry() -> AgentRegistry:
    """Return agent registry or raise StorageError if not initialized."""
    if agent_registry is None:
        raise StorageError(ErrorMessage.STORAGE_REGISTRY_NOT_INITIALIZED)
    return agent_registry


def get_send_message_use_case() -> SendMessageUseCase:
    """Provide a SendMessageUseCase instance."""
    return SendMessageUseCase(_require_agent_registry(), _require_thread_repository())


def get_stream_message_use_case() -> StreamMessageUseCase:
    """Provide a StreamMessageUseCase instance."""
    return StreamMessageUseCase(_require_agent_registry(), _require_thread_repository())


def get_create_thread_use_case() -> CreateThreadUseCase:
    """Provide a CreateThreadUseCase instance."""
    return CreateThreadUseCase(_require_thread_repository(), _require_agent_registry())


def get_get_thread_use_case() -> GetThreadUseCase:
    """Provide a GetThreadUseCase instance."""
    return GetThreadUseCase(_require_thread_repository())


def get_list_threads_use_case() -> ListThreadsUseCase:
    """Provide a ListThreadsUseCase instance."""
    return ListThreadsUseCase(_require_thread_repository())


def get_delete_thread_use_case() -> DeleteThreadUseCase:
    """Provide a DeleteThreadUseCase instance."""
    return DeleteThreadUseCase(_require_thread_repository())


def get_load_agent_config_use_case() -> LoadAgentConfigUseCase:
    """Provide a LoadAgentConfigUseCase instance."""
    return LoadAgentConfigUseCase(agent_config_loader)


def _require_persistence() -> tuple[MinioAgentConfigStore, PostgresAgentConfigRepository]:
    """Return persistence adapters or raise StorageError if not initialized."""
    if _minio_store is None or _pg_repository is None:
        raise StorageError(ErrorMessage.STORAGE_PERSISTENCE_NOT_INITIALIZED)
    return _minio_store, _pg_repository


def get_create_agent_config_use_case() -> CreateAgentConfigUseCase:
    """Provide a CreateAgentConfigUseCase instance."""
    store, repo = _require_persistence()
    return CreateAgentConfigUseCase(
        config_loader=agent_config_loader,
        config_store=store,
        config_repository=repo,
    )


def get_update_agent_config_use_case() -> UpdateAgentConfigUseCase:
    """Provide an UpdateAgentConfigUseCase instance."""
    store, repo = _require_persistence()
    return UpdateAgentConfigUseCase(
        config_loader=agent_config_loader,
        config_store=store,
        config_repository=repo,
        agent_registry=_require_agent_registry(),
    )


def get_delete_agent_config_use_case() -> DeleteAgentConfigUseCase:
    """Provide a DeleteAgentConfigUseCase instance."""
    store, repo = _require_persistence()
    return DeleteAgentConfigUseCase(
        config_store=store,
        config_repository=repo,
        agent_registry=_require_agent_registry(),
    )


def get_get_agent_config_use_case() -> GetAgentConfigUseCase:
    """Provide a GetAgentConfigUseCase instance."""
    store, _ = _require_persistence()
    return GetAgentConfigUseCase(
        config_loader=agent_config_loader,
        config_store=store,
    )


def get_list_agent_configs_use_case() -> ListAgentConfigsUseCase:
    """Provide a ListAgentConfigsUseCase instance."""
    _, repo = _require_persistence()
    return ListAgentConfigsUseCase(config_repository=repo)
