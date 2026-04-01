from enum import StrEnum

from pydantic import BaseModel


class TracingProviderType(StrEnum):
    LANGFUSE = "langfuse"
    PHOENIX = "phoenix"
    LANGSMITH = "langsmith"
    NONE = "none"


class TracingConfig(BaseModel, frozen=True):
    provider: TracingProviderType = TracingProviderType.NONE
    enabled: bool = False
    endpoint: str | None = None
    project_name: str | None = None
