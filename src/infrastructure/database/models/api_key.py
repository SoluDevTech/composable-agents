"""SQLAlchemy ORM model for the ``api_keys`` table.

Per-user API keys are stored hashed (SHA-256 hex of the plaintext). The
``key_hash`` column is unique and indexed for fast lookup on the auth hot
path; ``user_id`` is indexed for the list-by-user query. ``revoked_at`` is
``NULL`` for an active key.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base


class ApiKeyModel(Base):
    """ORM model for a per-user API key row.

    Attributes:
        id: uuid hex primary key.
        user_id: Owner identifier (indexed).
        name: Human-readable label.
        key_hash: SHA-256 hex digest of the plaintext (unique, indexed).
        key_prefix: First 10 chars of the plaintext (for recognition).
        revoked_at: Revocation timestamp, or ``None`` if active.
        last_used_at: Last use timestamp, or ``None`` if never used.
        created_at: Creation timestamp (UTC, non-null).
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_user_id", "user_id"),
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
