from datetime import datetime

from pydantic import BaseModel


class AgentConfigMetadata(BaseModel):
    """Metadata for a persisted agent configuration."""

    name: str
    model: str
    minio_path: str
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    # Owner of the configuration — set by the repository from the
    # ``current_user_id`` contextvar on save. Defaults to ``""`` so existing
    # constructions (no auth context) keep working.
    user_id: str = ""
