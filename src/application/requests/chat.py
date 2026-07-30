from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from src.domain.entities.hitl_decision import HitlDecision


class ChatRequest(BaseModel):
    """Request body for sending a chat message or an HITL decision.

    Exactly one of the following must be provided:
        * ``message`` — a human message, or
        * ``decisions`` — a non-empty list of HITL decisions (new contract), or
        * ``tool_call_id`` + ``action`` — a single legacy HITL decision.
    """

    message: str | None = Field(default=None, min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)
    action: Literal["approve", "reject", "edit"] | None = None
    reason: str | None = None
    edits: dict | None = None
    decisions: list[HitlDecision] | None = None

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        has_message = self.message is not None
        has_hitl = self.tool_call_id is not None
        has_decisions = self.decisions is not None
        if has_message and (has_hitl or has_decisions):
            raise ValueError("Provide either 'message' or HITL fields (tool_call_id + action / decisions), not both.")
        if has_decisions and has_hitl:
            raise ValueError("'decisions' is mutually exclusive with legacy 'tool_call_id' + 'action'.")
        if not has_message and not has_decisions and not has_hitl:
            raise ValueError("Provide either 'message', 'decisions', or HITL fields (tool_call_id + action).")
        if has_decisions and len(self.decisions) == 0:  # type: ignore[arg-type]
            raise ValueError("'decisions' must be a non-empty list.")
        if has_hitl and self.action is None:
            raise ValueError("'action' is required for HITL decisions.")
        if self.action == "edit" and self.edits is None:
            raise ValueError("'edits' is required for action 'edit'.")
        return self


class CreateThreadRequest(BaseModel):
    """Request body for creating a new thread."""

    agent_name: str = Field(..., min_length=1)
