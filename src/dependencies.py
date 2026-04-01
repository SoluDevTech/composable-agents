import logging
from pathlib import Path

from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.application.use_cases.send_message import SendMessageUseCase
from src.application.use_cases.stream_message import StreamMessageUseCase
from src.application.use_cases.thread_management import (
    CreateThreadUseCase,
    DeleteThreadUseCase,
    GetThreadUseCase,
    ListThreadsUseCase,
)
from src.config import Settings
from src.infrastructure.deepagent.registry import DeepAgentRegistry
from src.infrastructure.mcp.adapter import LangchainMcpToolLoader
from src.infrastructure.memory_thread.adapter import InMemoryThreadRepository
from src.infrastructure.tracing.noop_adapter import NoopTracingProvider
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


# ============= ADAPTERS =============

thread_repository = InMemoryThreadRepository()
agent_config_loader = YamlAgentConfigLoader()
mcp_tool_loader = LangchainMcpToolLoader()
tracing_provider = _create_tracing_provider(settings)

agent_registry = DeepAgentRegistry(
    agents_dir=Path(settings.agents_dir),
    config_loader=agent_config_loader,
    mcp_tool_loader=mcp_tool_loader,
    tracing_provider=tracing_provider,
)

agents_dir = settings.agents_dir
logger.info("Dependencies initialized (agents_dir=%s)", settings.agents_dir)

# ============= USE CASE PROVIDERS =============


def get_send_message_use_case() -> SendMessageUseCase:
    """Provide a SendMessageUseCase instance."""
    return SendMessageUseCase(agent_registry, thread_repository)


def get_stream_message_use_case() -> StreamMessageUseCase:
    """Provide a StreamMessageUseCase instance."""
    return StreamMessageUseCase(agent_registry, thread_repository)


def get_create_thread_use_case() -> CreateThreadUseCase:
    """Provide a CreateThreadUseCase instance."""
    return CreateThreadUseCase(thread_repository, agent_registry)


def get_get_thread_use_case() -> GetThreadUseCase:
    """Provide a GetThreadUseCase instance."""
    return GetThreadUseCase(thread_repository)


def get_list_threads_use_case() -> ListThreadsUseCase:
    """Provide a ListThreadsUseCase instance."""
    return ListThreadsUseCase(thread_repository)


def get_delete_thread_use_case() -> DeleteThreadUseCase:
    """Provide a DeleteThreadUseCase instance."""
    return DeleteThreadUseCase(thread_repository)


def get_load_agent_config_use_case() -> LoadAgentConfigUseCase:
    """Provide a LoadAgentConfigUseCase instance."""
    return LoadAgentConfigUseCase(agent_config_loader)


def get_agents_dir() -> str:
    """Provide the configured agents directory path."""
    return agents_dir
