"""Create user_llm_settings table + enable RLS with a per-user policy.

Revision ID: 014
Revises: 013
Create Date: 2026-07-27

Creates the ``user_llm_settings`` table that stores per-user OpenAI-compatible
LLM provider settings (provider label, base URL, Fernet-encrypted API key).
``user_id`` is the primary key — one configured provider per user.

Enables Row-Level Security and forces it on (so even the table owner is subject
to the policy), then creates a per-user policy filtering rows by
``user_id = current_setting('app.user_id', true)``.

This migration is Postgres-only (raw ``op.execute`` SQL). In tests, migrations
do not run — the ``db_engine`` fixture uses ``Base.metadata.create_all`` which
already includes the ``UserLlmSettingModel``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "user_llm_settings"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            user_id            VARCHAR(255) PRIMARY KEY,
            provider           VARCHAR(100) NOT NULL,
            base_url           VARCHAR(500) NOT NULL,
            api_key_encrypted  TEXT         NOT NULL,
            created_at         TIMESTAMPTZ  NOT NULL,
            updated_at         TIMESTAMPTZ  NOT NULL
        );
        """
    )
    # Enable RLS and force it on (even the table owner is subject to it).
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;")
    # Per-user policy: a row is visible / insertable / updatable / deletable
    # only when its user_id matches the transaction-scoped app.user_id GUC.
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_user_isolation
        ON {_TABLE}
        USING (user_id = current_setting('app.user_id', true))
        WITH CHECK (user_id = current_setting('app.user_id', true));
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_user_isolation ON {_TABLE};")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;")
    op.execute(f"DROP TABLE IF EXISTS {_TABLE};")
