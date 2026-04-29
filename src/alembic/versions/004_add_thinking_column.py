"""Add thinking column to messages.

Revision ID: 004
Revises: 003
Create Date: 2026-04-29
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import Text
from sqlalchemy import Column as saColumn

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", saColumn("thinking", Text, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "thinking")
