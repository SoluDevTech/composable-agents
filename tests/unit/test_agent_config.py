"""Tests for AgentConfig domain entity."""

import pytest
from pydantic import ValidationError

from src.domain.entities.agent_config import (
    AgentConfig,
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

    def test_minimal_config_sets_default_backend_to_state(self):
        """Should default backend type to STATE."""
        # Arrange
        config = AgentConfig(name="test-agent")

        # Act
        backend_type = config.backend.type

        # Assert
        assert backend_type == BackendType.STATE

    def test_minimal_config_has_empty_middleware(self):
        """Should default middleware to empty list."""
        # Arrange
        config = AgentConfig(name="test-agent")

        # Act
        middleware = config.middleware

        # Assert
        assert middleware == []

    def test_full_config_sets_model(self):
        """Should store the provided model."""
        # Arrange
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "system_prompt": "You are helpful.",
            "middleware": ["todo_list", "filesystem"],
            "backend": {"type": "filesystem", "root_dir": "/tmp/workspace"},
            "hitl": {"rules": {"write_file": True}},
            "subagents": [{"name": "sub", "description": "A subagent"}],
        }

        # Act
        config = AgentConfig(**data)

        # Assert
        assert config.model == "openai:gpt-4o"

    def test_full_config_sets_middleware(self):
        """Should store the provided middleware list."""
        # Arrange
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "middleware": ["todo_list", "filesystem"],
            "backend": {"type": "filesystem", "root_dir": "/tmp/workspace"},
        }

        # Act
        config = AgentConfig(**data)

        # Assert
        assert len(config.middleware) == 2

    def test_full_config_sets_backend_root_dir(self):
        """Should store the provided backend root_dir."""
        # Arrange
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "backend": {"type": "filesystem", "root_dir": "/tmp/workspace"},
        }

        # Act
        config = AgentConfig(**data)

        # Assert
        assert config.backend.root_dir == "/tmp/workspace"

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

    def test_rejects_invalid_middleware(self):
        """Should raise ValidationError when middleware is unknown."""
        # Arrange
        # Act & Assert
        with pytest.raises(ValidationError):
            AgentConfig(name="test", middleware=["invalid"])

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
        sa = SubAgentConfig(
            name="auditor", description="Security auditor", response_format=schema
        )

        # Assert
        assert sa.response_format == schema

    def test_response_format_is_none_by_default(self):
        """Should default response_format to None."""
        # Arrange
        # Act
        sa = SubAgentConfig(name="auditor", description="Security auditor")

        # Assert
        assert sa.response_format is None
