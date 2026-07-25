"""Add source_type and openapi_url columns to mcp_servers.

Revision ID: 009
Revises: 008
Create Date: 2026-07-24

COM-24 extends the MCP registry so an MCP server can be created dynamically
from an OpenAPI spec via FastMCP and mounted in-process. Two new columns track
the origin of each server:

- ``source_type`` (``"external"`` default | ``"openapi"``)
- ``openapi_url`` (``VARCHAR(500)`` NULL — the URL the spec was fetched from)
"""

from collections.abc import Sequence

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mcp_servers
            ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'external',
            ADD COLUMN IF NOT EXISTS openapi_url VARCHAR(500) NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE mcp_servers
            DROP COLUMN IF EXISTS openapi_url,
            DROP COLUMN IF EXISTS source_type;
        """
    )
