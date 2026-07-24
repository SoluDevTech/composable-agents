"""Tests for AgentConfig domain entity."""

import pytest
from pydantic import ValidationError

from src.domain.entities.agent_config import (
    AgentConfig,
    BackendConfig,
    BackendType,
    SubAgentConfig,
)


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_minimal_config_sets_default_model(self):
        """Should default model to claude-sonnet-4-5-20250929."""
        # Arrange
        config = AgentConfig(name="test-agent")

        # Act
        model = config.model

        # Assert
        assert model == "claude-sonnet-4-5-20250929"

    def test_minimal_config_sets_default_backend_to_store(self):
        """Should default backend type to STORE."""
        # Arrange
        config = AgentConfig(name="test-agent")

        # Act
        backend_type = config.backend.type

        # Assert
        assert backend_type == BackendType.STORE

    def test_full_config_sets_model(self):
        """Should store the provided model."""
        # Arrange
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "system_prompt": "You are helpful.",
            "backend": {"type": "store"},
            "hitl": {"rules": {"write_file": True}},
            "subagents": [{"name": "sub", "description": "A subagent"}],
        }

        # Act
        config = AgentConfig(**data)

        # Assert
        assert config.model == "openai:gpt-4o"

    def test_full_config_sets_subagents(self):
        """Should store the provided subagents list."""
        # Arrange
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "subagents": [{"name": "sub", "description": "A subagent"}],
        }

        # Act
        config = AgentConfig(**data)

        # Assert
        assert len(config.subagents) == 1

    def test_rejects_empty_name(self):
        """Should raise ValidationError when name is empty."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="")

    def test_rejects_invalid_backend_type(self):
        """Should raise ValidationError when backend type is unknown."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="test", backend={"type": "unknown"})

    def test_rejects_both_prompts_as_mutually_exclusive(self):
        """Should raise ValueError when both system_prompt and system_prompt_file are set."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValueError, match="mutually exclusive"):
            AgentConfig(
                name="test",
                system_prompt="Hello",
                system_prompt_file="./prompt.md",
            )

    def test_frozen_immutability_blocks_assignment(self):
        """Should raise ValidationError when mutating a frozen field."""
        # Arrange
        config = AgentConfig(name="test")

        # Act & Assert
        with pytest.raises(ValidationError):
            config.name = "other"

    def test_response_format_is_none_by_default(self):
        """Should default response_format to None."""
        # Arrange
        config = AgentConfig(name="test")

        # Act
        response_format = config.response_format

        # Assert
        assert response_format is None

    def test_response_format_stores_dict(self):
        """Should store the provided response_format schema."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
            "required": ["temperature"],
        }

        # Act
        config = AgentConfig(name="test", response_format=schema)

        # Assert
        assert config.response_format == schema

    def test_response_format_is_frozen(self):
        """Should raise ValidationError when mutating response_format."""
        # Arrange
        schema = {"type": "object", "properties": {}}
        config = AgentConfig(name="test", response_format=schema)

        # Act & Assert
        with pytest.raises(ValidationError):
            config.response_format = {"type": "object"}


class TestBackendConfigChanges:
    """Tests for the BackendType / BackendConfig refactor."""

    def test_backend_type_only_store(self):
        """BackendType enum should only have STORE value."""
        # Assert
        assert BackendType.STORE == "store"
        # These should NOT exist anymore:
        assert not hasattr(BackendType, "FILESYSTEM")
        assert not hasattr(BackendType, "COMPOSITE")
        assert not hasattr(BackendType, "STATE")

    def test_backend_config_has_checkpoint_backend_default_memory(self):
        """BackendConfig should default checkpoint_backend to 'memory'."""
        # Arrange
        config = BackendConfig()

        # Act
        checkpoint_backend = config.checkpoint_backend

        # Assert
        assert checkpoint_backend == "memory"

    def test_backend_config_accepts_postgres_checkpoint_backend(self):
        """BackendConfig should accept checkpoint_backend='postgres'."""
        # Arrange
        config = BackendConfig(checkpoint_backend="postgres")

        # Act
        checkpoint_backend = config.checkpoint_backend

        # Assert
        assert checkpoint_backend == "postgres"

    def test_backend_config_rejects_invalid_checkpoint_backend(self):
        """BackendConfig should reject invalid checkpoint_backend."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            BackendConfig(checkpoint_backend="redis")

    def test_backend_config_has_no_root_dir(self):
        """BackendConfig should NOT have root_dir field."""
        # Arrange
        config = BackendConfig()

        # Act & Assert
        assert not hasattr(config, "root_dir")

    def test_rejects_filesystem_backend_type(self):
        """AgentConfig should reject backend type 'filesystem'."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="test", backend={"type": "filesystem"})

    def test_rejects_composite_backend_type(self):
        """AgentConfig should reject backend type 'composite'."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="test", backend={"type": "composite"})


class TestMiddlewareRemoved:
    """Tests asserting the middleware field has been removed from AgentConfig."""

    def test_agent_config_has_no_middleware_field(self):
        """AgentConfig should NOT have a middleware field."""
        # Arrange
        config = AgentConfig(name="test")

        # Act & Assert
        assert not hasattr(config, "middleware")

    def test_agent_config_rejects_middleware_kwarg(self):
        """AgentConfig should reject middleware= kwarg."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="test", middleware=["todo_list"])


class TestSubAgentConfig:
    """Tests for SubAgentConfig."""

    def test_response_format_stores_dict(self):
        """Should store the provided response_format schema."""
        # Arrange
        schema = {
            "type": "object",
            "properties": {"severity": {"type": "string"}},
            "required": ["severity"],
        }

        # Act
        sa = SubAgentConfig(name="auditor", description="Security auditor", response_format=schema)

        # Assert
        assert sa.response_format == schema

    def test_response_format_is_none_by_default(self):
        """Should default response_format to None."""
        # Arrange
        # Act
        sa = SubAgentConfig(name="auditor", description="Security auditor")

        # Assert
        assert sa.response_format is None
