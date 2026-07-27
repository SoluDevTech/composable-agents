"""Add user_id column to agent_configs, threads, trace_events.

Revision ID: 012
Revises: 011
Create Date: 2026-07-27

Adds a ``user_id`` column (``VARCHAR(255) NOT NULL DEFAULT ''``) to the
``agent_configs``, ``threads`` and ``trace_events`` tables so that Row-Level
Security policies can filter rows per authenticated user.

Existing rows become ``user_id = ''`` — they are invisible under RLS (the
policies added in migration 013 compare against
``current_setting('app.user_id', true)`` which is NULL for unauthenticated
sessions) but still visible in SQLite tests (no RLS policies).

An index is added on ``user_id`` for each table to keep the per-user filter
fast.

This migration is Postgres-only (raw SQL). In tests, migrations do not run —
the ``db_engine`` fixture uses ``Base.metadata.create_all`` which already
includes the ``user_id`` column on the ORM models.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # agent_configs
    op.execute("ALTER TABLE agent_configs ADD COLUMN IF NOT EXISTS user_id VARCHAR(255) NOT NULL DEFAULT '';")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_configs_user_id ON agent_configs (user_id);")

    # threads
    op.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS user_id VARCHAR(255) NOT NULL DEFAULT '';")
    op.execute("CREATE INDEX IF NOT EXISTS ix_threads_user_id ON threads (user_id);")

    # trace_events
    op.execute("ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS user_id VARCHAR(255) NOT NULL DEFAULT '';")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trace_events_user_id ON trace_events (user_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trace_events_user_id;")
    op.execute("ALTER TABLE trace_events DROP COLUMN IF EXISTS user_id;")
    op.execute("DROP INDEX IF EXISTS ix_threads_user_id;")
    op.execute("ALTER TABLE threads DROP COLUMN IF EXISTS user_id;")
    op.execute("DROP INDEX IF EXISTS ix_agent_configs_user_id;")
    op.execute("ALTER TABLE agent_configs DROP COLUMN IF EXISTS user_id;")
