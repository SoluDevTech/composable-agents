"""Tests for AgentConfig domain entity."""

import pytest
from pydantic import ValidationError

from src.domain.entities.agent_config import AgentConfig, BackendType


class TestAgentConfig:
    def test_minimal_config(self):
        config = AgentConfig(name="test-agent")
        assert config.name == "test-agent"
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.backend.type == BackendType.STATE
        assert config.middleware == []

    def test_full_config(self):
        data = {
            "name": "my-agent",
            "model": "openai:gpt-4o",
            "system_prompt": "You are helpful.",
            "middleware": ["todo_list", "filesystem"],
            "backend": {"type": "filesystem", "root_dir": "/tmp/workspace"},
            "hitl": {"rules": {"write_file": True}},
            "subagents": [{"name": "sub", "description": "A subagent"}],
        }
        config = AgentConfig(**data)
        assert config.model == "openai:gpt-4o"
        assert len(config.middleware) == 2
        assert config.backend.root_dir == "/tmp/workspace"
        assert len(config.subagents) == 1

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            AgentConfig(name="")

    def test_rejects_invalid_middleware(self):
        with pytest.raises(ValidationError):
            AgentConfig(name="test", middleware=["invalid"])

    def test_rejects_invalid_backend_type(self):
        with pytest.raises(ValidationError):
            AgentConfig(name="test", backend={"type": "unknown"})

    def test_prompt_exclusivity(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            AgentConfig(
                name="test",
                system_prompt="Hello",
                system_prompt_file="./prompt.md",
            )

    def test_frozen_immutability(self):
        config = AgentConfig(name="test")
        with pytest.raises(ValidationError):
            config.name = "other"

    def test_response_format_none_by_default(self):
        config = AgentConfig(name="test")
        assert config.response_format is None

    def test_response_format_dict(self):
        schema = {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
            "required": ["temperature"],
        }
        config = AgentConfig(name="test", response_format=schema)
        assert config.response_format == schema

    def test_response_format_frozen(self):
        schema = {"type": "object", "properties": {}}
        config = AgentConfig(name="test", response_format=schema)
        with pytest.raises(ValidationError):
            config.response_format = {"type": "object"}


class TestSubAgentConfig:
    def test_subagent_response_format_dict(self):
        from src.domain.entities.agent_config import SubAgentConfig

        schema = {
            "type": "object",
            "properties": {"severity": {"type": "string"}},
            "required": ["severity"],
        }
        sa = SubAgentConfig(name="auditor", description="Security auditor", response_format=schema)
        assert sa.response_format == schema

    def test_subagent_response_format_none_by_default(self):
        from src.domain.entities.agent_config import SubAgentConfig

        sa = SubAgentConfig(name="auditor", description="Security auditor")
        assert sa.response_format is None
