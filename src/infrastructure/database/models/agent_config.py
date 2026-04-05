from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base


class AgentConfigModel(Base):
    __tablename__ = "agent_configs"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
