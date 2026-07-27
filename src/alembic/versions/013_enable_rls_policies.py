"""Enable RLS and create per-user policies on agent_configs, threads, trace_events, api_keys.

Revision ID: 013
Revises: 012
Create Date: 2026-07-27

Postgres-only migration (raw ``op.execute`` SQL). Enables Row-Level Security
and forces it on (so even the table owner is subject to the policies) on the
four per-user tables, then creates policies that filter rows by
``user_id = current_setting('app.user_id', true)``.

The ``app.user_id`` GUC is set transaction-scoped (LOCAL) by the SQLAlchemy
``before_cursor_execute`` listener (see
``src.infrastructure.database.rls_listener``) from the ``current_user_id``
contextvar, which is itself set by
``ComposableAgentsSecurity.verify_credentials`` after a successful JWT / API
key authentication.

For background jobs / migrations that must read across all users, the
``bypass_rls`` contextvar triggers ``SET LOCAL row_security = off`` in the
listener — the policies are bypassed for that transaction.

This migration does NOT run in tests (the ``db_engine`` fixture uses
``Base.metadata.create_all``, not Alembic). It is validated in QA against a
real PostgreSQL instance.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = ("agent_configs", "threads", "trace_events", "api_keys")


def upgrade() -> None:
    for table in _TABLES:
        # Enable RLS and force it on (even the table owner is subject to it).
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        # Per-user policy: a row is visible / insertable / updatable / deletable
        # only when its user_id matches the transaction-scoped app.user_id GUC.
        # current_setting(..., true) returns NULL when the GUC is unset, so an
        # unauthenticated session sees NO rows (defensive default).
        op.execute(
            f"""
            CREATE POLICY {table}_user_isolation
            ON {table}
            USING (user_id = current_setting('app.user_id', true))
            WITH CHECK (user_id = current_setting('app.user_id', true));
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_user_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
