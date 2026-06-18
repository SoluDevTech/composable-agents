import logging
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.domain.logging.messages import LogMessage

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Request body for sending a chat message or an HITL decision."""

    message: str | None = Field(default=None, min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)
    action: Literal["approve", "reject", "edit"] | None = None
    reason: str | None = None
    edits: dict | None = None

    @model_validator(mode="after")
    def validate_input(self):
        has_message = self.message is not None
        has_hitl = self.tool_call_id is not None
        if has_message == has_hitl:
            logger.error(LogMessage.VALIDATION_MSG_AND_HITL_EXCLUSIVE)
            raise ValueError("Provide either 'message' or HITL fields (tool_call_id + action), not both.")
        if has_hitl and self.action is None:
            logger.error(LogMessage.VALIDATION_ACTION_REQUIRED)
            raise ValueError("'action' is required for HITL decisions.")
        if self.action == "edit" and self.edits is None:
            logger.error(LogMessage.VALIDATION_EDITS_REQUIRED)
            raise ValueError("'edits' is required for action 'edit'.")
        return self


class CreateThreadRequest(BaseModel):
    """Request body for creating a new thread."""

    agent_name: str = Field(..., min_length=1)
