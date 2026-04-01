"""Tests for Message domain entity."""

from src.domain.entities.message import Message, MessageRole


class TestMessage:
    def test_structured_response_none_by_default(self):
        msg = Message(role=MessageRole.AI, content="Hello")
        assert msg.structured_response is None

    def test_structured_response_with_dict(self):
        data = {"temperature": 22.5, "condition": "sunny"}
        msg = Message(role=MessageRole.AI, content="Weather report", structured_response=data)
        assert msg.structured_response == data
        assert msg.structured_response["temperature"] == 22.5
