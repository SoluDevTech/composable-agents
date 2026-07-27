from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base


class AgentConfigModel(Base):
    __tablename__ = "agent_configs"
    __table_args__ = (Index("ix_agent_configs_user_id", "user_id"),)

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Owner of the configuration — NOT NULL with default '' (RLS plumbing).
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, server_default="", default="")
