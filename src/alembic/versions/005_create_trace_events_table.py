"""Create trace_events table.

Revision ID: 005
Revises: 004
Create Date: 2026-07-20

Single source of truth for everything that happened during a conversation turn.
Indexes:
  - ix_trace_events_thread_turn   (thread_id, turn_id)        — list_by_turn
  - ix_trace_events_thread_type   (thread_id, type)           — list_messages
  - ix_trace_events_thread_ts     (thread_id, timestamp)      — list_by_thread ordering
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_events (
            id         VARCHAR(36)  PRIMARY KEY,
            thread_id  VARCHAR(36)  NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
            turn_id    VARCHAR(36)  NOT NULL,
            type       VARCHAR(30)  NOT NULL,
            source     VARCHAR(100),
            name       VARCHAR(200),
            content    TEXT,
            metadata   JSONB,
            timestamp  TIMESTAMPTZ  NOT NULL DEFAULT now(),
            sequence   INTEGER      NOT NULL DEFAULT 0
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_trace_events_thread_turn
        ON trace_events(thread_id, turn_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_trace_events_thread_type
        ON trace_events(thread_id, type);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_trace_events_thread_ts
        ON trace_events(thread_id, timestamp);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trace_events_thread_ts;")
    op.execute("DROP INDEX IF EXISTS ix_trace_events_thread_type;")
    op.execute("DROP INDEX IF EXISTS ix_trace_events_thread_turn;")
    op.execute("DROP TABLE IF EXISTS trace_events;")
