"""Tests for YamlAgentConfigLoader (real internal implementation)."""

import pytest

from src.domain.exceptions import ConfigError, ConfigNotFoundError, ConfigValidationError
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader


class TestYamlAgentConfigLoader:
    @pytest.fixture
    def loader(self):
        return YamlAgentConfigLoader()

    def test_loads_minimal_yaml(self, loader, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test-agent\nmodel: "openai:gpt-4o"')
        config = loader.load(yaml_file)
        assert config.name == "test-agent"
        assert config.model == "openai:gpt-4o"

    def test_loads_system_prompt_from_file(self, loader, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("You are a helpful assistant.")
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test\nsystem_prompt_file: "./prompt.md"')
        config = loader.load(yaml_file)
        assert config.system_prompt == "You are a helpful assistant."

    def test_raises_on_missing_file(self, loader):
        with pytest.raises(ConfigNotFoundError):
            loader.load("/nonexistent/path.yaml")

    def test_raises_on_invalid_yaml(self, loader, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(":::invalid yaml{{{}")
        with pytest.raises(ConfigError):
            loader.load(yaml_file)

    def test_raises_on_schema_violation(self, loader, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: ""\nmodel: "openai:gpt-4o"')
        with pytest.raises((ConfigValidationError, ConfigError)):
            loader.load(yaml_file)

    def test_raises_on_non_dict_yaml(self, loader, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("- item1\n- item2")
        with pytest.raises(ConfigError, match="must contain a YAML mapping"):
            loader.load(yaml_file)

    def test_loads_full_config(self, loader, tmp_path):
        yaml_content = """
name: full-agent
model: "openai:gpt-4o"
system_prompt: "You are helpful."
middleware:
  - todo_list
  - filesystem
backend:
  type: filesystem
  root_dir: "./workspace"
hitl:
  rules:
    write_file: true
memory:
  - "./AGENTS.md"
skills:
  - "./skills/"
subagents:
  - name: sub
    description: "A subagent"
debug: true
"""
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)
        config = loader.load(yaml_file)
        assert config.debug is True
        assert len(config.middleware) == 2
        assert config.backend.root_dir == "./workspace"
        assert len(config.subagents) == 1

    def test_raises_on_missing_prompt_file(self, loader, tmp_path):
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test\nsystem_prompt_file: "./nonexistent.md"')
        with pytest.raises(ConfigNotFoundError, match="Prompt file not found"):
            loader.load(yaml_file)

    def test_loads_real_estate_extractor(self, loader):
        """Verify real-estate-extractor.yaml loads with subagents, response_format, and MCP servers."""
        config = loader.load("agents/real-estate-extractor.yaml")
        assert config.name == "real-estate-extractor"
        assert len(config.subagents) == 3

        for sa in config.subagents:
            assert sa.response_format is not None
            assert sa.response_format["type"] == "object"
            assert "properties" in sa.response_format
            assert len(sa.mcp_servers) == 1
            assert sa.mcp_servers[0].name == "raganything"
