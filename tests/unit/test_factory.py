import pytest
from unittest.mock import patch, MagicMock
from src.domain.entities.agent_config import AgentConfig, BackendType
from src.infrastructure.deepagent.factory import (
    create_agent_from_config,
    _resolve_tools,
    _resolve_backend,
    _resolve_interrupt_on,
)


class TestFactory:
    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_creates_agent_with_minimal_config(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")
        result = await create_agent_from_config(config)
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["name"] == "test-agent"
        assert kwargs["model"] == "claude-sonnet-4-5-20250929"

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_empty_middleware(self, mock_create):
        """Middleware is always empty — deepagents adds its own internally."""
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", middleware=["todo_list", "filesystem"])
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["middleware"] == []

    @pytest.mark.asyncio
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_hitl_config(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test",
            hitl={"rules": {"write_file": True, "execute": {"allowed_decisions": ["approve"]}}}
        )
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["interrupt_on"]["write_file"] is True
        assert kwargs["interrupt_on"]["execute"]["allowed_decisions"] == ["approve"]

    def test_resolve_tools_invalid_format(self):
        config = AgentConfig(name="test", tools=["invalid_no_colon"])
        with pytest.raises(ValueError, match="Format de tool invalide"):
            _resolve_tools(config)

    def test_resolve_tools_missing_module(self):
        config = AgentConfig(name="test", tools=["nonexistent.module:tool"])
        with pytest.raises(ValueError, match="Module introuvable"):
            _resolve_tools(config)

    def test_resolve_tools_missing_attribute(self):
        config = AgentConfig(
            name="test",
            tools=["src.infrastructure.deepagent.example_tools:nonexistent"]
        )
        with pytest.raises(ValueError, match="introuvable"):
            _resolve_tools(config)

    def test_resolve_tools_loads_existing(self):
        config = AgentConfig(
            name="test",
            tools=["src.infrastructure.deepagent.example_tools:get_user_name"]
        )
        tools = _resolve_tools(config)
        assert tools is not None
        assert len(tools) == 1

    def test_resolve_tools_returns_none_when_empty(self):
        config = AgentConfig(name="test", tools=[])
        assert _resolve_tools(config) is None

    def test_resolve_backend_state(self):
        config = AgentConfig(name="test")
        assert _resolve_backend(config) is None

    def test_resolve_backend_filesystem(self):
        config = AgentConfig(name="test", backend={"type": "filesystem", "root_dir": "/tmp"})
        backend = _resolve_backend(config)
        assert backend is not None

    def test_resolve_interrupt_on_empty(self):
        config = AgentConfig(name="test")
        assert _resolve_interrupt_on(config) is None

    def test_resolve_interrupt_on_bool(self):
        config = AgentConfig(name="test", hitl={"rules": {"write_file": True}})
        result = _resolve_interrupt_on(config)
        assert result == {"write_file": True}
