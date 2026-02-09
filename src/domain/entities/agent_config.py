from pydantic import BaseModel, Field, model_validator
from enum import StrEnum
from typing import Literal, Self

from src.domain.entities.mcp_server_config import McpServerConfig


class MiddlewareType(StrEnum):
    TODO_LIST = "todo_list"
    FILESYSTEM = "filesystem"
    SUB_AGENT = "sub_agent"


class BackendType(StrEnum):
    STATE = "state"
    STORE = "store"
    FILESYSTEM = "filesystem"
    COMPOSITE = "composite"


class BackendConfig(BaseModel):
    type: BackendType = BackendType.STATE
    root_dir: str | None = None


class InterruptRule(BaseModel):
    allowed_decisions: list[Literal["approve", "edit", "reject"]] = Field(
        default=["approve", "edit", "reject"]
    )


class HITLConfig(BaseModel):
    rules: dict[str, bool | InterruptRule] = Field(default_factory=dict)


class SubAgentConfig(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    instructions: str | None = None
    model: str | None = None
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)


class AgentConfig(BaseModel, frozen=True):
    """Schema principal de configuration d'un Deep Agent via YAML."""
    name: str = Field(..., min_length=1, max_length=100)
    model: str = Field(default="claude-sonnet-4-5-20250929")
    system_prompt: str | None = None
    system_prompt_file: str | None = None
    tools: list[str] = Field(default_factory=list)
    middleware: list[MiddlewareType] = Field(default_factory=list)
    backend: BackendConfig = Field(default_factory=BackendConfig)
    hitl: HITLConfig = Field(default_factory=HITLConfig)
    memory: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    subagents: list[SubAgentConfig] = Field(default_factory=list)
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    debug: bool = False

    @model_validator(mode="after")
    def check_prompt_exclusivity(self) -> Self:
        if self.system_prompt and self.system_prompt_file:
            raise ValueError("system_prompt et system_prompt_file sont mutuellement exclusifs")
        return self
