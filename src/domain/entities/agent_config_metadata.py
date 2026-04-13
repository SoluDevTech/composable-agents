from datetime import datetime

from pydantic import BaseModel


class AgentConfigMetadata(BaseModel):
    """Metadata for a persisted agent configuration."""

    name: str
    model: str
    minio_path: str
    created_at: datetime
    updated_at: datetime
