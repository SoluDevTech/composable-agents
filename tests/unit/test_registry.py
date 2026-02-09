import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import AgentNotFoundError
from src.infrastructure.deepagent.registry import DeepAgentRegistry
from tests.doubles.fake_agent_config_loader import FakeAgentConfigLoader
from tests.doubles.fake_mcp_tool_loader import FakeMcpToolLoader


class TestDeepAgentRegistry:
    """Tests for the DeepAgentRegistry adapter."""

    @pytest.fixture
    def agents_dir(self, tmp_path):
        """Create a temporary agents directory with YAML files."""
        d = tmp_path / "agents"
        d.mkdir()
        (d / "chatbot.yaml").write_text("name: chatbot")
        (d / "coder.yaml").write_text("name: coder")
        return d

    @pytest.fixture
    def config_loader(self, agents_dir) -> FakeAgentConfigLoader:
        loader = FakeAgentConfigLoader()
        loader.add_config(str(agents_dir / "chatbot.yaml"), AgentConfig(name="chatbot"))
        loader.add_config(str(agents_dir / "coder.yaml"), AgentConfig(name="coder"))
        return loader

    @pytest.fixture
    def mcp_tool_loader(self) -> FakeMcpToolLoader:
        return FakeMcpToolLoader()

    @pytest.fixture
    def registry(self, agents_dir, config_loader, mcp_tool_loader) -> DeepAgentRegistry:
        return DeepAgentRegistry(
            agents_dir=agents_dir,
            config_loader=config_loader,
            mcp_tool_loader=mcp_tool_loader,
        )

    # -- get_runner --------------------------------------------------------

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_get_runner_creates_and_returns_runner(
        self, mock_runner_cls, mock_create, registry
    ):
        """get_runner should load config, create the graph, wrap it in a runner."""
        mock_graph = MagicMock()
        mock_create.return_value = mock_graph
        mock_runner_instance = MagicMock()
        mock_runner_cls.return_value = mock_runner_instance

        runner = await registry.get_runner("chatbot")

        assert runner is mock_runner_instance
        mock_create.assert_awaited_once()
        mock_runner_cls.assert_called_once_with(mock_graph, tracing_provider=None)

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_get_runner_caches_on_second_call(
        self, mock_runner_cls, mock_create, registry
    ):
        """get_runner should return the cached runner without recreating."""
        mock_create.return_value = MagicMock()
        mock_runner_cls.return_value = MagicMock()

        first = await registry.get_runner("chatbot")
        second = await registry.get_runner("chatbot")

        assert first is second
        assert mock_create.await_count == 1, "Factory should only be called once"

    @pytest.mark.asyncio
    async def test_get_runner_raises_on_unknown_agent(self, registry):
        """get_runner should raise AgentNotFoundError for missing YAML."""
        with pytest.raises(AgentNotFoundError, match="Agent introuvable: unknown"):
            await registry.get_runner("unknown")

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_get_runner_passes_tracing_provider(
        self, mock_runner_cls, mock_create, agents_dir, config_loader, mcp_tool_loader
    ):
        """get_runner should forward the tracing_provider to DeepAgentRunner."""
        tracing = MagicMock()
        registry = DeepAgentRegistry(
            agents_dir=agents_dir,
            config_loader=config_loader,
            mcp_tool_loader=mcp_tool_loader,
            tracing_provider=tracing,
        )
        mock_create.return_value = MagicMock()
        mock_runner_cls.return_value = MagicMock()

        await registry.get_runner("chatbot")

        mock_runner_cls.assert_called_once_with(
            mock_create.return_value, tracing_provider=tracing
        )

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_get_runner_passes_mcp_tool_loader_to_factory(
        self, mock_runner_cls, mock_create, registry, mcp_tool_loader
    ):
        """create_agent_from_config should receive the mcp_tool_loader."""
        mock_create.return_value = MagicMock()
        mock_runner_cls.return_value = MagicMock()

        await registry.get_runner("chatbot")

        _, kwargs = mock_create.call_args
        assert kwargs.get("mcp_tool_loader") is mcp_tool_loader or (
            mock_create.call_args.args[1] is mcp_tool_loader
        )

    # -- list_agents -------------------------------------------------------

    def test_list_agents_returns_sorted_yaml_stems(self, registry):
        """list_agents should return sorted stem names of .yaml files."""
        result = registry.list_agents()
        assert result == ["chatbot", "coder"]

    def test_list_agents_excludes_non_yaml_files(self, agents_dir, config_loader, mcp_tool_loader):
        """list_agents should ignore files that are not .yaml."""
        (agents_dir / "notes.txt").write_text("not an agent")
        (agents_dir / "readme.md").write_text("docs")
        registry = DeepAgentRegistry(
            agents_dir=agents_dir,
            config_loader=config_loader,
            mcp_tool_loader=mcp_tool_loader,
        )
        result = registry.list_agents()
        assert result == ["chatbot", "coder"]

    def test_list_agents_returns_empty_when_dir_missing(self, tmp_path, config_loader, mcp_tool_loader):
        """list_agents should return [] if agents_dir does not exist."""
        registry = DeepAgentRegistry(
            agents_dir=tmp_path / "nonexistent",
            config_loader=config_loader,
            mcp_tool_loader=mcp_tool_loader,
        )
        result = registry.list_agents()
        assert result == []

    def test_list_agents_returns_empty_when_no_yaml_files(self, tmp_path, config_loader, mcp_tool_loader):
        """list_agents should return [] if the directory has no .yaml files."""
        empty_dir = tmp_path / "empty_agents"
        empty_dir.mkdir()
        registry = DeepAgentRegistry(
            agents_dir=empty_dir,
            config_loader=config_loader,
            mcp_tool_loader=mcp_tool_loader,
        )
        result = registry.list_agents()
        assert result == []

    # -- close -------------------------------------------------------------

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_close_clears_cached_runners(
        self, mock_runner_cls, mock_create, registry
    ):
        """close should clear the internal runner cache."""
        mock_create.return_value = MagicMock()
        mock_runner_cls.return_value = MagicMock()

        await registry.get_runner("chatbot")
        assert registry._runners, "Runner should be cached before close"

        await registry.close()
        assert registry._runners == {}, "Cache should be empty after close"

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.registry.create_agent_from_config", new_callable=AsyncMock)
    @patch("src.infrastructure.deepagent.registry.DeepAgentRunner")
    async def test_close_then_get_runner_recreates(
        self, mock_runner_cls, mock_create, registry
    ):
        """After close, get_runner should create the runner again from scratch."""
        mock_create.return_value = MagicMock()
        runner_a = MagicMock()
        runner_b = MagicMock()
        mock_runner_cls.side_effect = [runner_a, runner_b]

        first = await registry.get_runner("chatbot")
        await registry.close()
        second = await registry.get_runner("chatbot")

        assert first is runner_a
        assert second is runner_b
        assert first is not second
        assert mock_create.await_count == 2
