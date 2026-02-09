from src.application.use_cases.load_agent_config import LoadAgentConfigUseCase
from src.domain.entities.agent_config import AgentConfig
from src.domain.exceptions import ConfigNotFoundError
from tests.doubles.fake_agent_config_loader import FakeAgentConfigLoader
import pytest


class TestLoadAgentConfigUseCase:
    def test_loads_existing_config(self):
        fake_loader = FakeAgentConfigLoader()
        config = AgentConfig(name="test-agent")
        fake_loader.add_config("agents/test.yaml", config)
        use_case = LoadAgentConfigUseCase(fake_loader)

        result = use_case.execute("agents/test.yaml")
        assert result.name == "test-agent"

    def test_raises_on_missing_config(self):
        fake_loader = FakeAgentConfigLoader()
        use_case = LoadAgentConfigUseCase(fake_loader)

        with pytest.raises(ConfigNotFoundError):
            use_case.execute("nonexistent.yaml")
