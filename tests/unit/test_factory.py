"""Tests for the DeepAgent factory.

Patches ``create_deep_agent`` (external LLM factory) to avoid real LLM calls.
Tests exercise the public ``create_agent_from_config`` API only.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.domain.entities.agent_config import AgentConfig
from src.infrastructure.deepagent.factory import create_agent_from_config

WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "temperature": {"type": "number", "description": "Temperature in Celsius"},
        "condition": {"type": "string", "description": "Weather condition"},
    },
    "required": ["temperature", "condition"],
}

NESTED_SUBAGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "number"},
                },
                "required": ["label"],
            },
        },
    },
    "required": ["summary"],
}


class TestCreateAgentFromConfig:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_creates_agent_with_minimal_config(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["name"] == "test-agent"
        assert kwargs["model"] == "claude-sonnet-4-5-20250929"

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_hitl_config_as_interrupt_on(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test",
            hitl={"rules": {"write_file": True, "execute": {"allowed_decisions": ["approve"]}}},
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["interrupt_on"]["write_file"] is True
        assert kwargs["interrupt_on"]["execute"]["allowed_decisions"] == ["approve"]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_omits_interrupt_on_when_no_rules(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "interrupt_on" not in kwargs

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_loads_local_tools_from_path(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test",
            tools=["src.infrastructure.deepagent.example_tools:get_user_name"],
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["tools"] is not None
        assert len(kwargs["tools"]) == 1

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_invalid_tool_format_raises_value_error(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", tools=["invalid"])

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid tool format"):
            await create_agent_from_config(config)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_missing_tool_module_raises_value_error(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", tools=["nonexistent.module:tool"])

        # Act & Assert
        with pytest.raises(ValueError, match="Module not found"):
            await create_agent_from_config(config)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_store_backend_always_passed_to_create(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert — backend is always StoreBackend now, regardless of config
        kwargs = mock_create.call_args.kwargs
        assert "backend" in kwargs


class TestStoreBackendResolution:
    """Tests for the StoreBackend creation with explicit namespace."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_store_backend_passed_to_create(self, mock_create):
        """When backend.type=store, a StoreBackend should be passed."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", backend={"type": "store"})

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "backend" in kwargs
        # The backend should be a StoreBackend instance (not a lambda)
        from deepagents.backends import StoreBackend

        assert isinstance(kwargs["backend"], StoreBackend)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_store_backend_has_explicit_namespace(self, mock_create):
        """StoreBackend should be created with an explicit namespace."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", backend={"type": "store"})

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        backend = kwargs["backend"]
        from deepagents.backends import StoreBackend

        assert isinstance(backend, StoreBackend)
        # The namespace should be set (not relying on deprecated legacy detection)
        assert backend._namespace is not None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_store_backend_uses_provided_store(self, mock_create):
        """StoreBackend should use the store instance from the factory."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", backend={"type": "store"})

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        backend = kwargs["backend"]
        # The store should be wired (not None — should use the InMemoryStore or PostgresStore)
        assert backend._store is not None or kwargs.get("store") is not None


class TestPostgresStoreCheckpointer:
    """Tests for the checkpoint_backend resolution."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_memory_checkpointer_used_by_default(self, mock_create):
        """When checkpoint_backend=memory (default), MemorySaver should be used."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        from langgraph.checkpoint.memory import MemorySaver

        assert isinstance(kwargs["checkpointer"], MemorySaver)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    @patch("src.infrastructure.deepagent.factory._create_postgres_checkpointer")
    async def test_postgres_checkpointer_used_when_configured(self, mock_pg_cp, mock_create):
        """When checkpoint_backend=postgres, a Postgres checkpointer should be used."""
        # Arrange
        mock_pg_cp.return_value = MagicMock()
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test",
            backend={"type": "store", "checkpoint_backend": "postgres"},
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["checkpointer"] is mock_pg_cp.return_value


class TestMiddlewareRemovedFromFactory:
    """Tests asserting middleware is no longer passed to create_deep_agent."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_middleware_kwarg_not_passed(self, mock_create):
        """Factory should NOT pass middleware kwarg to create_deep_agent."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "middleware" not in kwargs


class TestResponseFormatIntegration:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_passes_response_format_kwarg_when_set(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", response_format=WEATHER_SCHEMA)

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "response_format" in kwargs
        assert kwargs["response_format"] is not None
        assert kwargs["response_format"] == WEATHER_SCHEMA

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_does_not_inject_structured_response_tool_when_set(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", response_format=WEATHER_SCHEMA)

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        if kwargs.get("tools"):
            tool_names = [getattr(t, "name", None) for t in kwargs["tools"]]
            assert "structured_response" not in tool_names

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_does_not_append_structured_output_instruction_when_set(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", response_format=WEATHER_SCHEMA)

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        system_prompt = kwargs.get("system_prompt") or ""
        assert "structured_response" not in system_prompt
        assert "structured format" not in system_prompt.lower()

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_returns_pydantic_basemodel_subclass_when_set(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test", response_format=WEATHER_SCHEMA)

        # Act
        _graph, model = await create_agent_from_config(config)

        # Assert
        assert model is not None
        assert issubclass(model, BaseModel)

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_omits_response_format_kwarg_when_none(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs.get("response_format") is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_omits_structured_response_tool_when_no_response_format(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        if kwargs.get("tools"):
            tool_names = [getattr(t, "name", None) for t in kwargs["tools"]]
            assert "structured_response" not in tool_names

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_returns_none_model_when_no_response_format(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test")

        # Act
        _graph, model = await create_agent_from_config(config)

        # Assert
        assert model is None


class TestSubagentStructuredOutput:
    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_response_format_passes_response_format_in_spec(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
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

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["response_format"] == WEATHER_SCHEMA

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_response_format_does_not_inject_structured_tool(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
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

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        tools = subagents[0].get("tools") or []
        tool_names = [getattr(t, "name", None) for t in tools]
        assert "structured_response" not in tool_names

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_response_format_does_not_append_instruction(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
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

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        system_prompt = subagents[0].get("system_prompt") or ""
        assert "structured_response" not in system_prompt
        assert "structured format" not in system_prompt.lower()

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_without_response_format_has_response_format_none(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
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

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0].get("response_format") is None

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_without_response_format_has_no_structured_tool(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
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

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        tools = subagents[0].get("tools") or []
        tool_names = [getattr(t, "name", None) for t in tools]
        assert "structured_response" not in tool_names

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_subagent_with_nested_response_format_passes_dict_as_is(self, mock_create):
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="parent",
            subagents=[
                {
                    "name": "reporter",
                    "description": "Builds structured reports",
                    "instructions": "Build a report",
                    "response_format": NESTED_SUBAGENT_SCHEMA,
                }
            ],
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        subagents = kwargs["subagents"]
        assert subagents[0]["response_format"] == NESTED_SUBAGENT_SCHEMA


class TestPrepareAgentNamespace:
    """Tests for conditional skill/memory loading via agent namespace."""

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_copies_selected_skills_to_agent_namespace(self, mock_create):
        """Selected skills should be copied to /agents/{name}/skills/."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test-agent",
            backend={"type": "store"},
            skills=["/skills/mcp/", "/skills/rag/"],
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["skills"] == ["/agents/test-agent/skills/"]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_copies_selected_memories_to_agent_namespace(self, mock_create):
        """Selected memories should be copied to /agents/{name}/memories/."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test-agent",
            backend={"type": "store"},
            memory=["/memories/AGENTS.md"],
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["memory"] == ["/agents/test-agent/memories/AGENTS.md"]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_skills_and_memory_copied_together(self, mock_create):
        """Both skills and memories should be copied when both are configured."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(
            name="test-agent",
            backend={"type": "store"},
            skills=["/skills/mcp/"],
            memory=["/memories/AGENTS.md"],
        )

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert kwargs["skills"] == ["/agents/test-agent/skills/"]
        assert kwargs["memory"] == ["/agents/test-agent/memories/AGENTS.md"]

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_skills_means_no_skills_kwarg(self, mock_create):
        """When no skills are configured, skills kwarg should not be set."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "skills" not in kwargs

    @patch("src.infrastructure.deepagent.factory.create_deep_agent")
    async def test_no_memory_means_no_memory_kwarg(self, mock_create):
        """When no memory is configured, memory kwarg should not be set."""
        # Arrange
        mock_create.return_value = MagicMock()
        config = AgentConfig(name="test-agent")

        # Act
        await create_agent_from_config(config)

        # Assert
        kwargs = mock_create.call_args.kwargs
        assert "memory" not in kwargs
