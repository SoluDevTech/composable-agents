"""Tests for Thread domain entity."""

from src.domain.entities.thread import Thread


class TestThread:
    """Tests for Thread."""

    def test_generates_an_id(self):
        """Should generate a non-None id."""
        # Arrange
        # Act
        thread = Thread(agent_name="test-agent")

        # Assert
        assert thread.id is not None

    def test_stores_agent_name(self):
        """Should store the provided agent_name."""
        # Arrange
        # Act
        thread = Thread(agent_name="test-agent")

        # Assert
        assert thread.agent_name == "test-agent"

    def test_defaults_to_empty_messages(self):
        """Should default messages to empty list."""
        # Arrange
        # Act
        thread = Thread(agent_name="test-agent")

        # Assert
        assert thread.messages == []
