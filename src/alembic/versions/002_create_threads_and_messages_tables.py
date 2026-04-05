"""Create threads and messages tables.

Revision ID: 002
Revises: 001
Create Date: 2026-04-05

Flat normalized schema: threads + messages with FK cascade.
Messages store tool_calls and structured_response as JSONB columns.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id         VARCHAR(36)  PRIMARY KEY,
            agent_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id                  VARCHAR(36)  PRIMARY KEY,
            thread_id           VARCHAR(36)  NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            role                VARCHAR(20)  NOT NULL,
            content             TEXT,
            timestamp           TIMESTAMPTZ  NOT NULL DEFAULT now(),
            tool_calls          JSONB,
            status              VARCHAR(50),
            structured_response JSONB
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messages_thread_id ON messages(thread_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_messages_thread_id_timestamp ON messages(thread_id, timestamp);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_threads_agent_name ON threads(agent_name);
        """
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("threads")
