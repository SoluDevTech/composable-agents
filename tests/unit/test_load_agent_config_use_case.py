"""Tests for LoadAgentConfigUseCase.

Uses the real YamlAgentConfigLoader with tmp_path (internal component).
"""

import pytest

from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.domain.exceptions import ConfigNotFoundError
from src.infrastructure.yaml_config.adapter import YamlAgentConfigLoader


class TestLoadAgentConfigUseCase:
    @pytest.fixture
    def loader(self):
        return YamlAgentConfigLoader()

    def test_loads_existing_config(self, loader, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("name: test-agent")
        use_case = LoadAgentConfigUseCase(loader)

        result = use_case.execute(str(yaml_file))

        assert result.name == "test-agent"

    def test_raises_on_missing_config(self, loader):
        use_case = LoadAgentConfigUseCase(loader)

        with pytest.raises(ConfigNotFoundError):
            use_case.execute("/nonexistent/path.yaml")
