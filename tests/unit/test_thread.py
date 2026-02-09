from src.domain.entities.thread import Thread


class TestThread:
    def test_creates_with_defaults(self):
        thread = Thread(agent_name="test-agent")
        assert thread.id is not None
        assert thread.agent_name == "test-agent"
        assert thread.messages == []
