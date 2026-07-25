"""Create mcp_servers table.

Revision ID: 008
Revises: 007
Create Date: 2026-07-24

Stores registered MCP servers keyed by name. The ``headers``, ``env`` and
``auth_token`` columns store Fernet-encrypted ciphertext (the
:class:`PostgresMcpServerRegistryRepository` adapter encrypts on write and
decrypts on read).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_servers (
            name                  VARCHAR(100) PRIMARY KEY,
            transport             VARCHAR(20)  NOT NULL DEFAULT 'http',
            url                   VARCHAR(500) NOT NULL,
            headers_encrypted     TEXT         NOT NULL DEFAULT '{}',
            env_encrypted         TEXT         NOT NULL DEFAULT '{}',
            auth_token_encrypted  TEXT,
            tool_count            INTEGER      NOT NULL DEFAULT 0,
            created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.drop_table("mcp_servers")
