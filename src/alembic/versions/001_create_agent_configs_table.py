"""Create agent_configs table.

Revision ID: 001
Revises:
Create Date: 2026-04-05

Uses raw SQL with CREATE TABLE IF NOT EXISTS to handle cases where
the table already exists from the previous ensure_schema() approach.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_configs (
            name       VARCHAR(100) PRIMARY KEY,
            model      VARCHAR(200) NOT NULL,
            minio_path VARCHAR(500) NOT NULL,
            is_builtin BOOLEAN      NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.drop_table("agent_configs")
