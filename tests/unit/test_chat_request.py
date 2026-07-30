"""Tests for ChatRequest validation (HITL refactor — TDD red phase).

The request gains a ``decisions: list[HitlDecision] | None`` field for the new
multi-decision HITL resume path. Exactly one of ``message`` / ``decisions`` /
(``tool_call_id``+``action`` legacy) must be provided.
"""

import pytest
from pydantic import ValidationError

from src.application.requests.chat import ChatRequest
from src.domain.entities.hitl_decision import HitlDecision


class TestChatRequestDecisions:
    def test_decisions_only_is_valid(self):
        # Arrange / Act
        req = ChatRequest(decisions=[HitlDecision(tool_call_id="tc-1", action="approve")])

        # Assert
        assert req.decisions is not None
        assert len(req.decisions) == 1
        assert req.message is None
        assert req.tool_call_id is None

    def test_decisions_and_message_both_set_raises(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            ChatRequest(
                message="hi",
                decisions=[HitlDecision(tool_call_id="tc-1", action="approve")],
            )

    def test_decisions_and_tool_call_id_both_set_raises(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            ChatRequest(
                tool_call_id="tc-1",
                action="approve",
                decisions=[HitlDecision(tool_call_id="tc-1", action="approve")],
            )

    def test_legacy_tool_call_id_and_action_without_decisions_is_valid(self):
        # Arrange / Act
        req = ChatRequest(tool_call_id="tc-1", action="approve")

        # Assert
        assert req.tool_call_id == "tc-1"
        assert req.action == "approve"
        assert req.decisions is None
        assert req.message is None

    def test_decisions_must_be_non_empty_list(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            ChatRequest(decisions=[])

    def test_decisions_items_must_have_tool_call_id(self):
        # Arrange / Act / Assert — HitlDecision requires tool_call_id
        with pytest.raises(ValidationError):
            ChatRequest(decisions=[HitlDecision(action="approve")])  # type: ignore[call-arg]

    def test_decisions_action_must_be_in_approve_reject_edit(self):
        # Arrange / Act / Assert — invalid action value rejected
        with pytest.raises(ValidationError):
            ChatRequest(
                decisions=[
                    HitlDecision(tool_call_id="tc-1", action="bogus")  # type: ignore[arg-type]
                ]
            )

    def test_legacy_edit_requires_edits(self):
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            ChatRequest(tool_call_id="tc-1", action="edit")
