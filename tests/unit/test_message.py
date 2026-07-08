"""Tests for Message domain entity."""

from src.domain.entities.message import Message, MessageRole


class TestMessage:
    """Tests for Message."""

    def test_structured_response_is_none_by_default(self):
        """Should default structured_response to None."""
        # Arrange
        # Act
        msg = Message(role=MessageRole.AI, content="Hello")

        # Assert
        assert msg.structured_response is None

    def test_structured_response_stores_dict(self):
        """Should store the provided structured_response dict."""
        # Arrange
        data = {"temperature": 22.5, "condition": "sunny"}

        # Act
        msg = Message(
            role=MessageRole.AI,
            content="Weather report",
            structured_response=data,
        )

        # Assert
        assert msg.structured_response == data

    def test_structured_response_allows_key_access(self):
        """Should allow dict-style access to structured_response values."""
        # Arrange
        data = {"temperature": 22.5, "condition": "sunny"}
        msg = Message(
            role=MessageRole.AI,
            content="Weather report",
            structured_response=data,
        )

        # Act
        temperature = msg.structured_response["temperature"]

        # Assert
        assert temperature == 22.5
