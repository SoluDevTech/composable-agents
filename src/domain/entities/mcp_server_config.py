import logging
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class McpTransportType(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


class McpServerConfig(BaseModel, frozen=True):
    """Configuration d'un serveur MCP."""

    name: str = Field(..., min_length=1)
    transport: McpTransportType
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    auth_token: str | None = None

    @model_validator(mode="after")
    def validate_transport_fields(self) -> Self:
        if self.transport == McpTransportType.STDIO and not self.command:
            logger.error("'command' is required for stdio transport")
            raise ValueError("'command' is required for stdio transport")
        if self.transport == McpTransportType.HTTP and not self.url:
            logger.error("'url' is required for http transport")
            raise ValueError("'url' is required for http transport")
        return self
