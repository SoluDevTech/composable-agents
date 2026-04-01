"""Tests for the DeepAgent factory.

Patches create_deep_agent (external LLM factory).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domain.entities.agent_config import AgentConfig
from src.infrastructure.deepagent.factory import (
    _create_response_tool,
    _resolve_backend,
    _resolve_interrupt_on,
    _resolve_subagents,
    _resolve_tools,
    create_agent_from_config,
)

WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "temperature": {"type": "number", "description": "Temperature in Celsius"},
        "condition": {"type": "string", "description": "Weather condition"},
    },
    "required": ["temperature", "condition"],
}


class TestFactory:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_creates_agent_with_minimal_config(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")
        await create_agent_from_config(config)
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["name"] == "test-agent"
        assert kwargs["model"] == "claude-sonnet-4-5-20250929"

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_empty_middleware(self, mock_create):
        """Middleware is always empty - deepagents adds its own internally."""
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", middleware=["todo_list", "filesystem"])
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["middleware"] == []

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_hitl_config(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test",
            hitl={"rules": {"write_file": True, "execute": {"allowed_decisions": ["approve"]}}},
        )
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert kwargs["interrupt_on"]["write_file"] is True
        assert kwargs["interrupt_on"]["execute"]["allowed_decisions"] == ["approve"]

    def test_resolve_tools_invalid_format(self):
        config = AgentConfig(name="test", tools=["invalid"])
        with pytest.raises(ValueError, match="Invalid tool format"):
            _resolve_tools(config)

    def test_resolve_tools_missing_module(self):
        config = AgentConfig(name="test", tools=["nonexistent.module:tool"])
        with pytest.raises(ValueError, match="Module not found"):
            _resolve_tools(config)

    def test_resolve_tools_missing_attribute(self):
        config = AgentConfig(
            name="test",
            tools=["src.infrastructure.deepagent.example_tools:nonexistent"],
        )
        with pytest.raises(ValueError, match="not found"):
            _resolve_tools(config)

    def test_resolve_tools_loads_existing(self):
        config = AgentConfig(
            name="test",
            tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
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


class TestCreateResponseTool:
    def test_returns_structured_tool(self):
        tool = _create_response_tool(WEATHER_SCHEMA)
        assert tool is not None
        assert tool.name == "structured_response"
        assert hasattr(tool, "invoke")

    def test_tool_has_description(self):
        tool = _create_response_tool(WEATHER_SCHEMA)
        assert tool.description

    def test_tool_args_schema_has_properties(self):
        tool = _create_response_tool(WEATHER_SCHEMA)
        schema = tool.args_schema.model_json_schema()
        assert "temperature" in schema["properties"]
        assert "condition" in schema["properties"]


class TestResponseFormatIntegration:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_provider_strategy_when_response_format_set(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", response_format=WEATHER_SCHEMA)
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert "response_format" in kwargs
        from langchain.agents.structured_output import ProviderStrategy

        assert isinstance(kwargs["response_format"], ProviderStrategy)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_omits_response_format_when_none(self, mock_create):
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")
        await create_agent_from_config(config)
        kwargs = mock_create.call_args.kwargs
        assert "response_format" not in kwargs


class TestResolveSubagentsStructuredOutput:
    async def test_injects_tool_when_response_format_set(self):
        config = AgentConfig(
            name="parent",
            subagents=[
                {
                    "name": "auditor",
                    "description": "Security auditor",
                    "instructions": "Analyze code",
                    "response_format": WEATHER_SCHEMA,
                }
            ],
        )
        result = await _resolve_subagents(config)
        assert result is not None
        sa = result[0]
        assert sa["tools"] is not None
        tool_names = [t.name for t in sa["tools"]]
        assert "structured_response" in tool_names
        assert "structured_response" in sa["system_prompt"]

    async def test_unchanged_without_response_format(self):
        config = AgentConfig(
            name="parent",
            subagents=[
                {
                    "name": "helper",
                    "description": "A helper",
                    "instructions": "Help the user",
                }
            ],
        )
        result = await _resolve_subagents(config)
        assert result is not None
        sa = result[0]
        assert sa["tools"] is None
        assert "structured_response" not in (sa["system_prompt"] or "")
