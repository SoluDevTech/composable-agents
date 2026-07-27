from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base

if TYPE_CHECKING:
    from src.infrastructure.database.models.trace_event import TraceEventModel


class ThreadModel(Base):
    __tablename__ = "threads"
    __table_args__ = (Index("ix_threads_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Owner of the thread — NOT NULL with default '' so existing rows become
    # user_id='' (invisible under RLS but still visible in SQLite tests).
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, server_default="", default="")

    # lazy="raise" prevents silent N+1 queries. Always load trace_events
    # explicitly via trace_repo.list_by_thread(thread_id) or selectinload.
    trace_events: Mapped[list["TraceEventModel"]] = relationship(
        "TraceEventModel",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="TraceEventModel.timestamp",
        lazy="raise",
    )
