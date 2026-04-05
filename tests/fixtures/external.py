"""Fixtures for external adapter mocks.

Only external adapters (LLM runners, MCP tool loaders, tracing providers,
object stores, metadata repositories) are mocked.
Internal components use their real implementations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.tracing_provider import TracingProvider


@pytest.fixture
def mock_agent_runner():
    """AsyncMock spec'd to the AgentRunner port."""
    return AsyncMock(spec=AgentRunner)


@pytest.fixture
def mock_mcp_tool_loader():
    """AsyncMock spec'd to the McpToolLoader port."""
    mock = AsyncMock(spec=McpToolLoader)
    mock.load_tools.return_value = []
    mock._closed = False

    original_close = mock.close

    async def track_close():
        mock._closed = True
        return await original_close()

    mock.close = track_close
    return mock


@pytest.fixture
def mock_tracing_provider():
    """MagicMock spec'd to the TracingProvider port."""
    mock = MagicMock(spec=TracingProvider)
    mock.get_callbacks.return_value = []
    mock.flush = AsyncMock()
    mock.shutdown = AsyncMock()
    return mock


@pytest.fixture
def mock_agent_config_store():
    """AsyncMock spec'd to the AgentConfigStore port (MinIO boundary)."""
    return AsyncMock(spec=AgentConfigStore)


@pytest.fixture
def mock_agent_config_repository():
    """AsyncMock spec'd to the AgentConfigRepository port (PostgreSQL boundary)."""
    return AsyncMock(spec=AgentConfigRepository)
