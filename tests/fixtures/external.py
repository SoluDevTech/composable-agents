"""Fixtures for external adapter mocks.

Only external adapters (LLM runners, MCP tool loaders, tracing providers,
object stores, metadata repositories, prompt managers) are mocked.
Internal components use their real implementations.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.ports.agent_config_repository import AgentConfigRepository
from src.domain.ports.agent_config_store import AgentConfigStore
from src.domain.ports.agent_runner import AgentRunner
from src.domain.ports.mcp_tool_loader import McpToolLoader
from src.domain.ports.prompt_manager import PromptManager
from src.domain.ports.tracing_provider import TracingProvider


@pytest.fixture
def mock_agent_runner():
    """AsyncMock spec'd to the AgentRunner port (external LLM boundary)."""
    return AsyncMock(spec=AgentRunner)


@pytest.fixture
def mock_mcp_tool_loader():
    """AsyncMock spec'd to the McpToolLoader port (external MCP server boundary)."""
    return AsyncMock(spec=McpToolLoader)


@pytest.fixture
def mock_tracing_provider():
    """MagicMock spec'd to the TracingProvider port (external tracing boundary)."""
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


@pytest.fixture
def mock_prompt_manager():
    """AsyncMock spec'd to the PromptManager port (Phoenix boundary)."""
    return AsyncMock(spec=PromptManager)
