"""Tests for YamlAgentConfigLoader (real internal implementation).

Uses the shared yaml_loader fixture (NOT a local loader).
"""

import pytest

from src.domain.errors.config import (
    ConfigError,
    ConfigNotFoundError,
    ConfigValidationError,
)


class TestYamlAgentConfigLoaderLoad:
    """Tests for YamlAgentConfigLoader.load."""

    def test_loads_minimal_yaml_returns_name(self, yaml_loader, tmp_path):
        """Should parse a minimal YAML and return the agent name."""
        # Arrange
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test-agent\nmodel: "openai:gpt-4o"')

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert
        assert config.name == "test-agent"

    def test_loads_minimal_yaml_returns_model(self, yaml_loader, tmp_path):
        """Should parse a minimal YAML and return the agent model."""
        # Arrange
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test-agent\nmodel: "openai:gpt-4o"')

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert
        assert config.model == "openai:gpt-4o"

    def test_loads_system_prompt_from_file(self, yaml_loader, tmp_path):
        """Should resolve system_prompt_file into system_prompt."""
        # Arrange
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("You are a helpful assistant.")
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test\nsystem_prompt_file: "./prompt.md"')

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert
        assert config.system_prompt == "You are a helpful assistant."

    def test_raises_on_missing_file(self, yaml_loader):
        """Should raise ConfigNotFoundError when the file does not exist."""
        # Arrange
        # Act & Assert
        with pytest.raises(ConfigNotFoundError):
            yaml_loader.load("/nonexistent/path.yaml")

    def test_raises_on_invalid_yaml(self, yaml_loader, tmp_path):
        """Should raise ConfigError on malformed YAML."""
        # Arrange
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(":::invalid yaml{{{}")

        # Act & Assert
        with pytest.raises(ConfigError):
            yaml_loader.load(yaml_file)

    def test_raises_on_schema_violation(self, yaml_loader, tmp_path):
        """Should raise ConfigValidationError (or ConfigError) on empty name."""
        # Arrange
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: ""\nmodel: "openai:gpt-4o"')

        # Act & Assert
        with pytest.raises((ConfigValidationError, ConfigError)):
            yaml_loader.load(yaml_file)

    def test_raises_on_non_dict_yaml(self, yaml_loader, tmp_path):
        """Should raise ConfigError when the YAML is not a mapping."""
        # Arrange
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text("- item1\n- item2")

        # Act & Assert
        with pytest.raises(ConfigError, match="must contain a YAML mapping"):
            yaml_loader.load(yaml_file)

    def test_loads_full_config_returns_debug_flag(self, yaml_loader, tmp_path):
        """Should parse debug flag from a full YAML config."""
        # Arrange
        yaml_content = (
            "name: full-agent\n"
            'model: "openai:gpt-4o"\n'
            'system_prompt: "You are helpful."\n'
            "backend:\n  type: store\n  checkpoint_backend: memory\n"
            "hitl:\n  rules:\n    write_file: true\n"
            'memory:\n  - "./AGENTS.md"\n'
            'skills:\n  - "./skills/"\n'
            'subagents:\n  - name: sub\n    description: "A subagent"\n'
            "debug: true\n"
        )
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert
        assert config.debug is True

    def test_strips_deprecated_middleware_field(self, yaml_loader, tmp_path):
        """Should silently strip the deprecated 'middleware' field from YAML."""
        # Arrange
        yaml_content = "name: full-agent\nmiddleware:\n  - todo_list\ndebug: true\n"
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert — middleware is silently dropped, agent loads successfully
        assert config.name == "full-agent"
        assert config.debug is True
        assert not hasattr(config, "middleware")

    def test_strips_deprecated_root_dir_field(self, yaml_loader, tmp_path):
        """Should silently strip the deprecated 'root_dir' from backend in YAML."""
        # Arrange
        yaml_content = 'name: full-agent\nbackend:\n  type: state\n  root_dir: "/tmp"\n'
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert — root_dir is silently dropped, agent loads successfully
        assert config.name == "full-agent"
        assert config.backend.type.value == "store"

    def test_migrates_state_backend_type_to_store(self, yaml_loader, tmp_path):
        """Should migrate deprecated 'state' backend type to 'store'."""
        # Arrange
        yaml_content = "name: full-agent\nbackend:\n  type: state\n"
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert — state is migrated to store
        assert config.backend.type.value == "store"

    def test_rejects_filesystem_backend_type(self, yaml_loader, tmp_path):
        """Should raise when the YAML uses the removed 'filesystem' backend type."""
        # Arrange
        yaml_content = 'name: full-agent\nbackend:\n  type: filesystem\n  root_dir: "./workspace"\n'
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act & Assert
        with pytest.raises((ConfigValidationError, ConfigError)):
            yaml_loader.load(yaml_file)

    def test_loads_full_config_returns_subagents(self, yaml_loader, tmp_path):
        """Should parse the subagents list from a full YAML config."""
        # Arrange
        yaml_content = 'name: full-agent\nsubagents:\n  - name: sub\n    description: "A subagent"\n'
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        # Act
        config = yaml_loader.load(yaml_file)

        # Assert
        assert len(config.subagents) == 1

    def test_raises_on_missing_prompt_file(self, yaml_loader, tmp_path):
        """Should raise ConfigNotFoundError when system_prompt_file is missing."""
        # Arrange
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text('name: test\nsystem_prompt_file: "./nonexistent.md"')

        # Act & Assert
        with pytest.raises(ConfigNotFoundError, match="Prompt file not found"):
            yaml_loader.load(yaml_file)


class TestYamlAgentConfigLoaderLoadFromString:
    """Tests for YamlAgentConfigLoader.load_from_string."""

    def test_returns_name_for_valid_yaml(self, yaml_loader):
        """Should parse valid YAML string and return the agent name."""
        # Arrange
        yaml_content = (
            "name: test-agent\n"
            "model: claude-sonnet-4-5-20250929\n"
            'system_prompt: "You are a test agent."\n'
            "tools: []\n"
            "debug: false\n"
        )

        # Act
        config = yaml_loader.load_from_string(yaml_content)

        # Assert
        assert config.name == "test-agent"

    def test_returns_model_for_valid_yaml(self, yaml_loader):
        """Should parse valid YAML string and return the agent model."""
        # Arrange
        yaml_content = 'name: test-agent\nmodel: claude-sonnet-4-5-20250929\nsystem_prompt: "You are a test agent."\n'

        # Act
        config = yaml_loader.load_from_string(yaml_content)

        # Assert
        assert config.model == "claude-sonnet-4-5-20250929"

    def test_returns_system_prompt_for_valid_yaml(self, yaml_loader):
        """Should parse valid YAML string and return the system_prompt."""
        # Arrange
        yaml_content = 'name: test-agent\nsystem_prompt: "You are a test agent."\n'

        # Act
        config = yaml_loader.load_from_string(yaml_content)

        # Assert
        assert config.system_prompt == "You are a test agent."

    def test_returns_empty_tools_for_valid_yaml(self, yaml_loader):
        """Should default tools to empty list."""
        # Arrange
        yaml_content = "name: test-agent\ntools: []\n"

        # Act
        config = yaml_loader.load_from_string(yaml_content)

        # Assert
        assert config.tools == []

    def test_returns_false_debug_for_valid_yaml(self, yaml_loader):
        """Should default debug to False."""
        # Arrange
        yaml_content = "name: test-agent\ndebug: false\n"

        # Act
        config = yaml_loader.load_from_string(yaml_content)

        # Assert
        assert config.debug is False

    def test_raises_on_invalid_yaml(self, yaml_loader):
        """Should raise ConfigError on malformed YAML."""
        # Arrange
        # Act & Assert
        with pytest.raises(ConfigError):
            yaml_loader.load_from_string(":::invalid yaml{{{}")

    def test_raises_on_empty_string(self, yaml_loader):
        """Should raise ConfigError on empty string."""
        # Arrange
        # Act & Assert
        with pytest.raises(ConfigError):
            yaml_loader.load_from_string("")

    def test_raises_when_system_prompt_file_referenced(self, yaml_loader):
        """Should raise ConfigError when YAML references system_prompt_file."""
        # Arrange
        yaml_content = 'name: test-agent\nsystem_prompt_file: "./prompt.md"\n'

        # Act & Assert
        with pytest.raises(ConfigError, match="system_prompt_file"):
            yaml_loader.load_from_string(yaml_content)
