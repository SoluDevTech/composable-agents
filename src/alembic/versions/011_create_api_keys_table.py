"""Create api_keys table.

Revision ID: 011
Revises: 010
Create Date: 2026-07-27

Creates the ``api_keys`` table that stores per-user API keys (SHA-256 hashed).
Indexes:

* ``ix_api_keys_user_id`` on ``user_id`` — speeds up ``list_by_user``.
* ``ix_api_keys_key_hash`` UNIQUE on ``key_hash`` — speeds up the auth hot-path
  lookup ``find_active_by_hash`` and guarantees no duplicate hashes.

This migration does NOT add Row-Level Security policies or a ``user_id`` column
to ``agent_configs`` / ``threads`` / ``trace_events`` — those belong to a
later RLS layer.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id           VARCHAR(36)   PRIMARY KEY,
            user_id      VARCHAR(255)  NOT NULL,
            name         VARCHAR(200)  NOT NULL,
            key_hash     VARCHAR(64)   NOT NULL,
            key_prefix   VARCHAR(12)   NOT NULL,
            revoked_at   TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ   NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_key_hash;")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_user_id;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
