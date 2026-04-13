from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class PromptMessage(BaseModel):
    role: MessageRole
    content: str = Field(..., min_length=1)


class CreatePromptRequest(BaseModel):
    identifier: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    content: list[PromptMessage] = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    description: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None

    @model_validator(mode="after")
    def validate_content_roles(self) -> "CreatePromptRequest":
        roles = [msg.role for msg in self.content]
        if MessageRole.user not in roles and MessageRole.system not in roles:
            raise ValueError("content must contain at least one 'user' or 'system' message")
        return self

    @field_validator("content", mode="before")
    @classmethod
    def validate_message_format(cls, v: list) -> list:
        if not v:
            raise ValueError("content cannot be empty")
        for i, msg in enumerate(v):
            if isinstance(msg, dict):
                if "role" not in msg:
                    raise ValueError(f"message[{i}] missing 'role' field")
                if "content" not in msg:
                    raise ValueError(f"message[{i}] missing 'content' field")
        return v


class UpdatePromptRequest(BaseModel):
    content: list[PromptMessage] | None = None
    model_name: str | None = None
    description: str | None = None
    metadata: dict | None = None

    @field_validator("content", mode="before")
    @classmethod
    def validate_content_not_empty(cls, v: list | None) -> list | None:
        if v is not None and len(v) == 0:
            raise ValueError("content cannot be an empty list")
        return v
