"""Add description column to agent_configs.

Revision ID: 010
Revises: 007
Create Date: 2026-07-25

Adds an optional ``description`` column (``VARCHAR(500) NULL``) to the
``agent_configs`` table so persisted agent metadata can carry a human-readable
description sourced from the YAML configuration.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "010"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_configs ADD COLUMN description VARCHAR(500);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_configs DROP COLUMN description;
        """
    )
