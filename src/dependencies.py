import logging
from pathlib import Path

from miniopy_async import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from src.application.use_cases.create_agent_config import CreateAgentConfigUseCase
from src.application.use_cases.delete_agent_config import DeleteAgentConfigUseCase
from src.application.use_cases.get_agent_config import GetAgentConfigUseCase
from src.application.use_cases.list_agent_configs import ListAgentConfigsUseCase
from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.application.use_cases.seed_agents import SeedAgentsUseCase
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
from src.domain.exceptions import StorageError
from src.domain.ports.prompt_manager import PromptManager
from src.domain.ports.thread_repository import ThreadRepository
from src.infrastructure.deepagent.registry import DeepAgentRegistry
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader
from src.infrastructure.minio_store.adapter import MinioAgentConfigStore
from src.infrastructure.persistent_registry.adapter import PersistentAgentRegistry
from src.infrastructure.postgres_repository.adapter import PostgresAgentConfigRepository
from src.infrastructure.postgres_thread.adapter import PostgresThreadRepository
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider
from src.infrastructure.tracing.phoenix_prompt_manager import PhoenixPromptManagerImpl
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

logger = logging.getLogger("composable-agents")

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

        logger.info("Initializing Langfuse tracing provider (host=%s)", tracing.langfuse_host)
        return LangfuseTracingProvider(
            public_key=tracing.langfuse_public_key or "",
            secret_key=tracing.langfuse_secret_key or "",
            host=tracing.langfuse_host,
        )

    if tracing.enabled and tracing.provider == "phoenix":
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        logger.info("Initializing Phoenix tracing provider (endpoint=%s)", tracing.phoenix_collector_endpoint)
        return PhoenixTracingProvider(
            endpoint=tracing.phoenix_collector_endpoint,
            api_key=tracing.phoenix_api_key,
            project_name=tracing.project_name,
        )

    logger.info("Tracing disabled, using NoopTracingProvider")
    return NoopTracingProvider()


def get_prompt_manager() -> PromptManager:
    """Provide PromptManager implementation."""
    tracing = settings.tracing
    return PhoenixPromptManagerImpl(
        base_url=tracing.phoenix_collector_endpoint,
        api_key=tracing.phoenix_api_key,
    )


# ============= ADAPTERS =============

agent_config_loader = YamlAgentConfigLoader()
mcp_tool_loader = LangchainMcpToolLoader()
tracing_provider = _create_tracing_provider(settings)

# Filesystem-based registry (kept for backward compatibility)
agent_registry = DeepAgentRegistry(
    agents_dir=Path(settings.agents_dir),
    config_loader=agent_config_loader,
    mcp_tool_loader=mcp_tool_loader,
    tracing_provider=tracing_provider,
)

agents_dir = settings.agents_dir

# ============= PERSISTENCE (initialized at startup) =============

_async_engine: AsyncEngine | None = None
_minio_store: MinioAgentConfigStore | None = None
_pg_repository: PostgresAgentConfigRepository | None = None
_persistent_registry: PersistentAgentRegistry | None = None
thread_repository: ThreadRepository | None = None


async def init_persistence() -> None:
    """Initialize persistent infrastructure: SQLAlchemy engine, MinIO store, PostgreSQL repositories.

    Must be called during application startup.
    """
    global _async_engine, _minio_store, _pg_repository, _persistent_registry, agent_registry, thread_repository

    logger.info("Initializing persistence layer")

    _async_engine = create_async_engine(
        settings.database_url,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
    )
    logger.info("SQLAlchemy async engine created (pool: AsyncAdaptedQueuePool, size=20, max_overflow=20)")

    _pg_repository = PostgresAgentConfigRepository(engine=_async_engine)
    thread_repository = PostgresThreadRepository(engine=_async_engine)
    logger.info("PostgreSQL repositories initialized")

    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    _minio_store = MinioAgentConfigStore(client=minio_client, bucket=settings.minio_bucket)
    await _minio_store.ensure_bucket()
    logger.info("MinIO store initialized (bucket=%s)", settings.minio_bucket)

    _persistent_registry = PersistentAgentRegistry(
        config_loader=agent_config_loader,
        config_store=_minio_store,
        config_repository=_pg_repository,
        mcp_tool_loader=mcp_tool_loader,
        tracing_provider=tracing_provider,
    )
    agent_registry = _persistent_registry

    logger.info("Persistence layer initialized, agent_registry switched to PersistentAgentRegistry")


async def close_persistence() -> None:
    """Close persistent infrastructure resources.

    Must be called during application shutdown.
    """
    if _persistent_registry:
        await _persistent_registry.close()
        logger.info("Persistent registry closed")

    if _async_engine:
        await _async_engine.dispose()
        logger.info("SQLAlchemy engine disposed")


async def seed_builtin_agents() -> None:
    """Seed built-in agents from the configured agents directory."""
    if _minio_store is None or _pg_repository is None:
        logger.warning("Persistence not initialized, skipping seed")
        return

    seed_use_case = SeedAgentsUseCase(
        config_loader=agent_config_loader,
        config_store=_minio_store,
        config_repository=_pg_repository,
    )
    await seed_use_case.execute(agents_dir=Path(settings.agents_dir))
    logger.info("Built-in agents seeded from %s", settings.agents_dir)


logger.info("Dependencies initialized (agents_dir=%s)", settings.agents_dir)

# ============= USE CASE PROVIDERS =============


def _require_thread_repository() -> ThreadRepository:
    """Return thread repository or raise StorageError if not initialized."""
    if thread_repository is None:
        raise StorageError("Thread repository not initialized. Check PostgreSQL connectivity.")
    return thread_repository


def get_send_message_use_case() -> SendMessageUseCase:
    """Provide a SendMessageUseCase instance."""
    return SendMessageUseCase(agent_registry, _require_thread_repository())


def get_stream_message_use_case() -> StreamMessageUseCase:
    """Provide a StreamMessageUseCase instance."""
    return StreamMessageUseCase(agent_registry, _require_thread_repository())


def get_create_thread_use_case() -> CreateThreadUseCase:
    """Provide a CreateThreadUseCase instance."""
    return CreateThreadUseCase(_require_thread_repository(), agent_registry)


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


def get_agents_dir() -> str:
    """Provide the configured agents directory path."""
    return agents_dir


def _require_persistence() -> tuple[MinioAgentConfigStore, PostgresAgentConfigRepository]:
    """Return persistence adapters or raise StorageError if not initialized."""
    if _minio_store is None or _pg_repository is None:
        raise StorageError("Persistence layer not initialized. Check MinIO/PostgreSQL connectivity.")
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
        agent_registry=agent_registry,
    )


def get_delete_agent_config_use_case() -> DeleteAgentConfigUseCase:
    """Provide a DeleteAgentConfigUseCase instance."""
    store, repo = _require_persistence()
    return DeleteAgentConfigUseCase(
        config_store=store,
        config_repository=repo,
        agent_registry=agent_registry,
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
