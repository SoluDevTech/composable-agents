from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    """Request body for sending a chat message or an HITL decision."""

    message: str | None = Field(default=None, min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)
    action: Literal["approve", "reject", "edit"] | None = None
    reason: str | None = None
    edits: dict | None = None

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        has_message = self.message is not None
        has_hitl = self.tool_call_id is not None
        if has_message == has_hitl:
            raise ValueError("Provide either 'message' or HITL fields (tool_call_id + action), not both.")
        if has_hitl and self.action is None:
            raise ValueError("'action' is required for HITL decisions.")
        if self.action == "edit" and self.edits is None:
            raise ValueError("'edits' is required for action 'edit'.")
        return self


class CreateThreadRequest(BaseModel):
    """Request body for creating a new thread."""

    agent_name: str = Field(..., min_length=1)
