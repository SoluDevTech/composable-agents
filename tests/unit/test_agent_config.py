import pytest
from src.domain.entities.agent_config import AgentConfig, BackendType, MiddlewareType


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
        with pytest.raises(Exception):
            AgentConfig(name="")

    def test_rejects_invalid_middleware(self):
        with pytest.raises(Exception):
            AgentConfig(name="test", middleware=["invalid"])

    def test_rejects_invalid_backend_type(self):
        with pytest.raises(Exception):
            AgentConfig(name="test", backend={"type": "unknown"})

    def test_prompt_exclusivity(self):
        with pytest.raises(ValueError, match="mutuellement exclusifs"):
            AgentConfig(
                name="test",
                system_prompt="Hello",
                system_prompt_file="./prompt.md"
            )

    def test_frozen_immutability(self):
        config = AgentConfig(name="test")
        with pytest.raises(Exception):
            config.name = "other"
