"""Tests for LoadAgentConfigUseCase.

Uses the real YamlAgentConfigLoader (shared yaml_loader fixture) with tmp_path.
The execute method is async.
"""

import pytest

from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.domain.errors.config import ConfigNotFoundError


class TestLoadAgentConfigUseCase:
    """Tests for LoadAgentConfigUseCase."""

    @pytest.fixture
    def use_case(self, yaml_loader):
        return LoadAgentConfigUseCase(yaml_loader)

    async def test_loads_existing_config_returns_name(self, use_case, tmp_path):
        """Should load an existing YAML file and return the parsed name."""
        # Arrange
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("name: test-agent")

        # Act
        result = await use_case.execute(str(yaml_file))

        # Assert
        assert result.name == "test-agent"

    async def test_raises_config_not_found_when_missing(self, use_case):
        """Should raise ConfigNotFoundError when the file does not exist."""
        # Arrange
        # Act & Assert
        with pytest.raises(ConfigNotFoundError):
            await use_case.execute("/nonexistent/path.yaml")
