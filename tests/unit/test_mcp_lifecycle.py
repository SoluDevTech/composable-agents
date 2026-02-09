from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import dependencies
from src.dependencies import close_dependencies, init_dependencies


class TestCloseDependencies:
    """Tests for close_dependencies MCP cleanup."""

    @pytest.mark.asyncio
    async def test_close_calls_mcp_tool_loader_close(self):
        """close_dependencies calls close() on the mcp_tool_loader."""
        from tests.doubles.fake_mcp_tool_loader import FakeMcpToolLoader

        fake_loader = FakeMcpToolLoader()
        dependencies._mcp_tool_loader = fake_loader
        dependencies._agent_registry = None

        await close_dependencies()

        assert fake_loader._closed is True

    @pytest.mark.asyncio
    async def test_close_with_no_mcp_tool_loader(self):
        """close_dependencies does not fail when mcp_tool_loader is None."""
        dependencies._mcp_tool_loader = None
        dependencies._agent_registry = None

        await close_dependencies()  # Should not raise


class TestInitDependenciesMcp:
    """Tests for MCP wiring in init_dependencies."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.adapter.LangchainMcpToolLoader")
    @patch("src.infrastructure.deepagent.registry.DeepAgentRegistry")
    @patch("src.infrastructure.yaml_config.adapter.YamlAgentConfigLoader")
    @patch("src.infrastructure.memory_thread.adapter.InMemoryThreadRepository")
    async def test_init_creates_mcp_loader_and_passes_to_registry(
        self,
        mock_thread_repo_cls,
        mock_yaml_loader_cls,
        mock_registry_cls,
        mock_mcp_loader_cls,
    ):
        """init_dependencies creates a LangchainMcpToolLoader and passes it to DeepAgentRegistry."""
        mock_loader_instance = MagicMock()
        mock_mcp_loader_cls.return_value = mock_loader_instance

        mock_yaml_loader = MagicMock()
        mock_yaml_loader_cls.return_value = mock_yaml_loader

        mock_registry_instance = MagicMock()
        mock_registry_cls.return_value = mock_registry_instance
        mock_thread_repo_cls.return_value = MagicMock()

        settings = MagicMock()
        settings.agents_dir = "./agents"

        await init_dependencies(settings)

        mock_mcp_loader_cls.assert_called_once()
        mock_registry_cls.assert_called_once()
        # Verify mcp_tool_loader was passed to DeepAgentRegistry
        call_kwargs = mock_registry_cls.call_args[1]
        assert call_kwargs["mcp_tool_loader"] is mock_loader_instance
        assert dependencies._mcp_tool_loader is mock_loader_instance
