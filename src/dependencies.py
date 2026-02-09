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
from src.domain.ports.agent_config_loader import AgentConfigLoader
from src.domain.ports.agent_registry import AgentRegistry
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.thread_repository import ThreadRepository
from src.domain.ports.tracing_provider import TracingProvider

_thread_repository: ThreadRepository | None = None
_agent_registry: AgentRegistry | None = None
_agent_config_loader: AgentConfigLoader | None = None
_mcp_tool_loader: McpToolLoader | None = None
_tracing_provider: TracingProvider | None = None
_agents_dir: str = "./agents"


def _create_tracing_provider(settings: Settings) -> TracingProvider:
    """Create the appropriate TracingProvider based on settings.

    Args:
        settings: Application settings containing tracing configuration.

    Returns:
        A TracingProvider instance matching the configured provider.
    """
    from src.infrastructure.tracing.noop_adapter import NoopTracingProvider

    tracing = settings.tracing

    if tracing.enabled and tracing.provider == "langfuse":
        from src.infrastructure.tracing.langfuse_adapter import LangfuseTracingProvider

        return LangfuseTracingProvider(
            public_key=tracing.langfuse_public_key or "",
            secret_key=tracing.langfuse_secret_key or "",
            host=tracing.langfuse_host,
        )

    if tracing.enabled and tracing.provider == "phoenix":
        from src.infrastructure.tracing.phoenix_adapter import PhoenixTracingProvider

        return PhoenixTracingProvider(
            endpoint=tracing.phoenix_collector_endpoint,
            api_key=tracing.phoenix_api_key,
            project_name=tracing.project_name,
        )

    return NoopTracingProvider()


async def init_dependencies(settings: Settings) -> None:
    """Initialize all adapters and store them as module-level singletons.

    This function is called once during application startup (lifespan).
    It wires the infrastructure adapters based on the provided settings.

    Args:
        settings: Application settings.
    """
    global _thread_repository, _agent_registry, _agent_config_loader, _mcp_tool_loader, _tracing_provider, _agents_dir

    _agents_dir = settings.agents_dir

    from src.infrastructure.memory_thread.adapter import InMemoryThreadRepository
    from src.infrastructure.mcp.adapter import LangchainMcpToolLoader
    from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader

    _thread_repository = InMemoryThreadRepository()
    _agent_config_loader = YamlAgentConfigLoader()
    _mcp_tool_loader = LangchainMcpToolLoader()

    # Initialize tracing provider
    _tracing_provider = _create_tracing_provider(settings)

    # Create agent registry for lazy loading
    from src.infrastructure.deepagent.registry import DeepAgentRegistry

    _agent_registry = DeepAgentRegistry(
        agents_dir=Path(settings.agents_dir),
        config_loader=_agent_config_loader,
        mcp_tool_loader=_mcp_tool_loader,
        tracing_provider=_tracing_provider,
    )


async def close_dependencies() -> None:
    """Close all resources that require cleanup.

    This function is called during application shutdown (lifespan).
    It flushes tracing, closes MCP connections, and shuts down tracing.
    """
    global _mcp_tool_loader, _agent_registry
    await flush_tracing()
    if _agent_registry is not None:
        await _agent_registry.close()
    if _mcp_tool_loader is not None:
        await _mcp_tool_loader.close()
    await shutdown_tracing()


def override_dependencies(
    thread_repository: ThreadRepository | None = None,
    agent_registry: AgentRegistry | None = None,
    agent_config_loader: AgentConfigLoader | None = None,
    mcp_tool_loader: McpToolLoader | None = None,
    tracing_provider: TracingProvider | None = None,
) -> None:
    """Override dependencies for testing purposes.

    Args:
        thread_repository: Optional ThreadRepository override.
        agent_registry: Optional AgentRegistry override.
        agent_config_loader: Optional AgentConfigLoader override.
        mcp_tool_loader: Optional McpToolLoader override.
        tracing_provider: Optional TracingProvider override.
    """
    global _thread_repository, _agent_registry, _agent_config_loader, _mcp_tool_loader, _tracing_provider
    if thread_repository is not None:
        _thread_repository = thread_repository
    if agent_registry is not None:
        _agent_registry = agent_registry
    if agent_config_loader is not None:
        _agent_config_loader = agent_config_loader
    if mcp_tool_loader is not None:
        _mcp_tool_loader = mcp_tool_loader
    if tracing_provider is not None:
        _tracing_provider = tracing_provider


def _get_thread_repository() -> ThreadRepository:
    assert _thread_repository is not None, "Dependencies not initialized"
    return _thread_repository


def _get_agent_registry() -> AgentRegistry:
    assert _agent_registry is not None, "Dependencies not initialized"
    return _agent_registry


def _get_agent_config_loader() -> AgentConfigLoader:
    assert _agent_config_loader is not None, "Dependencies not initialized"
    return _agent_config_loader


def _get_mcp_tool_loader() -> McpToolLoader:
    assert _mcp_tool_loader is not None, "Dependencies not initialized"
    return _mcp_tool_loader


def _get_tracing_provider() -> TracingProvider:
    """Return the tracing provider singleton.

    Returns:
        The configured TracingProvider instance.
    """
    assert _tracing_provider is not None, "Dependencies not initialized"
    return _tracing_provider


async def flush_tracing() -> None:
    """Flush pending traces. Safe to call even if tracing is not initialized."""
    if _tracing_provider is not None:
        await _tracing_provider.flush()


async def shutdown_tracing() -> None:
    """Shutdown the tracing provider. Safe to call even if tracing is not initialized."""
    if _tracing_provider is not None:
        await _tracing_provider.shutdown()


# --- Use case providers (used by FastAPI Depends) ---


def get_send_message_use_case() -> SendMessageUseCase:
    """Provide a SendMessageUseCase instance."""
    return SendMessageUseCase(_get_agent_registry(), _get_thread_repository())


def get_stream_message_use_case() -> StreamMessageUseCase:
    """Provide a StreamMessageUseCase instance."""
    return StreamMessageUseCase(_get_agent_registry(), _get_thread_repository())


def get_create_thread_use_case() -> CreateThreadUseCase:
    """Provide a CreateThreadUseCase instance."""
    return CreateThreadUseCase(_get_thread_repository(), _get_agent_registry())


def get_get_thread_use_case() -> GetThreadUseCase:
    """Provide a GetThreadUseCase instance."""
    return GetThreadUseCase(_get_thread_repository())


def get_list_threads_use_case() -> ListThreadsUseCase:
    """Provide a ListThreadsUseCase instance."""
    return ListThreadsUseCase(_get_thread_repository())


def get_delete_thread_use_case() -> DeleteThreadUseCase:
    """Provide a DeleteThreadUseCase instance."""
    return DeleteThreadUseCase(_get_thread_repository())



def get_load_agent_config_use_case() -> LoadAgentConfigUseCase:
    """Provide a LoadAgentConfigUseCase instance."""
    return LoadAgentConfigUseCase(_get_agent_config_loader())


def get_agents_dir() -> str:
    """Provide the configured agents directory path."""
    return _agents_dir
