"""Drop is_builtin column from agent_configs.

Revision ID: 003
Revises: 002
Create Date: 2026-04-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("agent_configs", "is_builtin")


def downgrade() -> None:
    op.add_column("agent_configs", "is_builtin", nullable=False, server_default="false")
