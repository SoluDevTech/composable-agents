"""SQLAlchemy ORM model for the ``user_llm_settings`` table.

Per-user LLM provider settings. The API key is stored encrypted (Fernet token)
in ``api_key_encrypted`` — never as plaintext. ``user_id`` is the primary key
(one configured provider per user).
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base


class UserLlmSettingModel(Base):
    """ORM model for a per-user LLM provider settings row.

    Attributes:
        user_id: Primary key — owner identifier.
        provider: Free-form provider label (display only).
        base_url: OpenAI-compatible base URL.
        api_key_encrypted: Fernet-encrypted API key token (Text).
        created_at: Creation timestamp (UTC, non-null).
        updated_at: Last update timestamp (UTC, non-null).
    """

    __tablename__ = "user_llm_settings"

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
